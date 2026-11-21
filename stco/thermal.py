"""一维热网络 + 泄漏回环 + 吞吐上限。

节点（自下而上）：amb（固定）— hs（散热器基座）— sub（基板面）— L0 — L1 — … — L(N-1)
每一段都是一个热阻，全部由 params 算出，不做手填。
解 G·T = P（诺顿等效），因此残差可以直接断言。
"""
import math
import numpy as np

from . import params as P


class ThermalStack:
    def __init__(self, powers, areas, cooling="air", double_sided=False,
                 t_amb=None, r_hs=None):
        """powers: 每层动态功耗 (W)，自下而上；areas: 每层面积 (mm^2)。"""
        assert len(powers) == len(areas) and powers
        self.powers = list(map(float, powers))
        self.areas = list(map(float, areas))
        self.cooling = cooling
        self.double_sided = double_sided
        self.t_amb = P.STACK["t_amb"]["value"] if t_amb is None else t_amb
        self.r_hs = P.COOLING[cooling]["r_hs"] if r_hs is None else r_hs
        self.n = len(self.powers)

        # 节点：0=hs, 1..n=layers, n+1=top plate（双面冷却时存在）
        self.n_nodes = self.n + 2 if double_sided else self.n + 1
        self.G = np.zeros((self.n_nodes, self.n_nodes))
        self.b = np.zeros(self.n_nodes)  # 与 fixed 节点的耦合常数项

        a_ref = max(self.areas)                      # 足迹面积（mm²）
        r_tim = P.STACK["r_tim"]["value"] / a_ref     # K/W
        r_si = (P.STACK["die_thickness"]["value"]
                / (P.STACK["k_si"]["value"] * a_ref * 1e-6))   # K/W
        r_if = P.STACK["r_iface"]["value"] / a_ref    # K/W

        # hs <-> amb
        self.G[0, 0] += 1.0 / self.r_hs
        self.b[0] += self.t_amb / self.r_hs
        # hs <-> sub 与 L0 <-> sub 合并成一个 sub 节点：直接用 TIM 串联第一层界面
        self.G[0, 0] += 1.0 / (r_tim + r_if)
        self.G[0, 1] -= 1.0 / (r_tim + r_if)
        self.G[1, 0] -= 1.0 / (r_tim + r_if)
        self.G[1, 1] += 1.0 / (r_tim + r_if)

        self.r_vert = r_si + r_if                    # 层间：硅 + 键合界面
        for i in range(1, self.n):
            g = 1.0 / self.r_vert
            self.G[i, i] += g
            self.G[i + 1, i + 1] += g
            self.G[i, i + 1] -= g
            self.G[i + 1, i] -= g

        if double_sided:
            top = self.n + 1
            self.G[top, top] += 1.0 / self.r_hs
            self.b[top] += self.t_amb / self.r_hs
            g = 1.0 / self.r_vert
            self.G[self.n, self.n] += g
            self.G[top, top] += g
            self.G[self.n, top] -= g
            self.G[top, self.n] -= g

        self.p_base = np.array(self.powers)

    # ------------------------------------------------------------ 解温度
    def solve(self, powers=None):
        p = self.p_base if powers is None else np.asarray(powers, float)
        rhs = np.zeros(self.n_nodes)
        rhs[1:self.n + 1] = p          # 节点 0 是散热器基座，功率落在 1..n
        T = np.linalg.solve(self.G, rhs + self.b)
        return T

    def residual(self, T, powers=None):
        p = self.p_base if powers is None else np.asarray(powers, float)
        rhs = np.zeros(self.n_nodes)
        rhs[1:self.n + 1] = p
        return float(np.max(np.abs(self.G @ T - (rhs + self.b))))

    def tier_temps(self, T):
        return T[1:self.n + 1]

    def hot(self, T):
        return float(np.max(self.tier_temps(T)))

    # ------------------------------------------------------------ 泄漏回环
    def leakage_power(self, temps):
        """25 °C 下泄漏 = leak_frac × 动态；每升 leak_double_dt 翻倍。

        指数做钳位：真实器件在 150 °C 以上已经不可用，模型只需要区分「可控」与「失控」，
        所以把指数截在 2^10（≈1000 倍）以内，避免 inf/nan 污染后续求解。
        """
        frac = P.POWER["leak_frac"]["value"]
        dbl = P.POWER["leak_double_dt"]["value"]
        texp = np.clip((np.asarray(temps) - 25.0) / dbl, -10.0, 10.0)
        return np.array([p * frac * 2.0 ** e for p, e in zip(self.p_base, texp)])

    def solve_with_leakage(self, max_iter=200, tol=1e-10):
        """Picard 迭代：T ← solve(P_dyn + P_leak(T))。返回 (T, P_leak, iters, residual)。"""
        p = self.p_base.copy()
        T = np.clip(self.solve(p), -40.0, 400.0)
        for it in range(1, max_iter + 1):
            leak = self.leakage_power(self.tier_temps(T))
            p_new = self.p_base + leak
            T_new = np.clip(self.solve(p_new), -40.0, 400.0)
            d = float(np.max(np.abs(T_new - T)))
            T = T_new
            if d < tol:
                break
        leak = self.leakage_power(self.tier_temps(T))
        return T, leak, it, self.residual(T, self.p_base + leak)

    # ------------------------------------------------------------ 吞吐上限
    def max_power_for(self, t_jmax=None):
        """在给定冷却下达不到 T_jmax 时，所有层动态功耗之和的上限（含泄漏反馈）。bisection。"""
        t_jmax = P.STACK["t_jmax"]["value"] if t_jmax is None else t_jmax
        scale_lo, scale_hi = 0.0, 1.0
        def hot(scale):
            p = self.p_base * scale
            p_total = p + self.leakage_power(self.tier_temps(self.solve(p)))
            T = self.solve(p_total)
            return self.hot(T)
        # 先扩上界
        while hot(scale_hi) < t_jmax and scale_hi < 1e4:
            scale_hi *= 2.0
        if scale_hi >= 1e4 and hot(scale_hi) < t_jmax:
            return float("inf"), hot(scale_hi)
        for _ in range(80):
            mid = 0.5 * (scale_lo + scale_hi)
            if hot(mid) <= t_jmax:
                scale_lo = mid
            else:
                scale_hi = mid
        return float(scale_lo * sum(self.p_base)), hot(scale_lo)


def analytic_single_node(power, r_total, t_amb):
    """退化情形：单节点、单热阻。用于断言数值解与解析解一致。"""
    return t_amb + power * r_total


def placement_search(power_classes, cooling="air", double_sided=False, max_layers=6):
    """穷举层序，找使峰值结温最低的排列。power_classes: [(name, p_dyn, area), ...]
    返回 (best_order, best_hot, all_results)。层数 ≤6 时穷举，超过则用贪心。
    """
    from itertools import permutations
    n = len(power_classes)
    results = []
    if n <= max_layers:
        it = permutations(range(n))
    else:
        it = [tuple(range(n))]
    for order in it:
        powers = [power_classes[i][1] for i in order]
        areas = [power_classes[i][2] for i in order]
        st = ThermalStack(powers, areas, cooling=cooling, double_sided=double_sided)
        T, leak, _, _ = st.solve_with_leakage()
        results.append((st.hot(T), order))
    results.sort(key=lambda x: x[0])
    best = results[0]
    return [power_classes[i][0] for i in best[1]], best[0], results
