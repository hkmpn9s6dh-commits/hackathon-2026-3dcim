"""单个设计的评估：容量 → 能量 → 两工况的功耗 → 温度 → 供电。

一致性要求（这是第一版最容易被自己骗过去的地方）：
  **所有能量都必须落到某一个层上**。搬运权重的能量不是凭空消失的，它烧在逻辑层的
  存储接口 / PHY 上。所以热网络里必须包含「搬运功耗」，否则「容量不够」这件事在温度上
  看不出来，模型就会给出「2 层也能跑 900 tok/s」这种自相矛盾的答案。
"""
import math

from . import params as P
from .thermal import ThermalStack
from . import pdn as PDN

MB = 1024.0 * 1024.0


def _clamp_temp(t):
    return min(max(t, -50.0), 400.0)


def model_mb(params=None, bits=None):
    p = P.WORKLOAD["params"]["value"] if params is None else params
    b = P.WORKLOAD["bits"]["value"] if bits is None else bits
    return p * b / 8.0 / MB


def capacity_mb(n_cim):
    return n_cim * P.CIM["tier_area"]["value"] * P.CIM["density"]["value"]


def plan_layers(params=None, bits=None):
    """装下模型所需的最小层数（向上取整）。"""
    need = model_mb(params, bits)
    per = P.CIM["tier_area"]["value"] * P.CIM["density"]["value"]
    return max(1, int(math.ceil(need / per))), need, per


def energy_ledger():
    """三种存储策略的每 token 能量（J）。"""
    e_mac = P.CIM["e_mac"]["value"]
    macs = P.WORKLOAD["params"]["value"]
    bits_total = P.model_bytes() * 8.0
    e_compute = macs * e_mac
    e_act = P.WORKLOAD["act_bytes_per_token"]["value"] * 8.0 * P.WORKLOAD["e_hb"]["value"]
    return dict(compute_j=e_compute, act_j=e_act,
                resident_j=e_compute + e_act,
                near_j=e_compute + e_act + bits_total * P.WORKLOAD["e_hb"]["value"],
                hbm_j=e_compute + e_act + bits_total * P.WORKLOAD["e_ext"]["value"])


def evaluate(n_cim, cooling="air", double_sided=False, target=None, has_dram=False):
    target = P.WORKLOAD["tok_s_target"]["value"] if target is None else target
    p_tier = P.cim_tier_power()
    macs = P.WORKLOAD["params"]["value"]
    led = energy_ledger()

    cap = capacity_mb(n_cim)
    need = model_mb()
    resident = min(1.0, cap / need)
    spill_mb = max(0.0, need - cap)
    spill_j_per_token = spill_mb * MB * 8.0 * P.WORKLOAD["e_ext"]["value"]

    e_token = led["resident_j"] + spill_j_per_token
    e_token_near = led["resident_j"] + spill_mb * MB * 8.0 * P.WORKLOAD["e_hb"]["value"]

    roles = [("logic", P.LAYERS["logic"]["p_dyn"], P.LAYERS["logic"]["area"])]
    roles += [(f"cim{i}", 0.0, P.LAYERS["cim"]["area"]) for i in range(n_cim)]
    if has_dram:
        roles.append(("dram", P.LAYERS["dram"]["p_dyn"], P.LAYERS["dram"]["area"]))
    areas = [a for _, _, a in roles]
    footprint = P.CIM["tier_area"]["value"]

    tok_ceiling = n_cim * (P.CIM["array_rows"]["value"] * P.CIM["array_cols"]["value"]
                           * P.CIM["tiles_per_tier"]["value"] * P.CIM["freq_nom"]["value"]) / macs

    # 双面冷却：同一份热量走两条并联路径，等效 R 减半、面热流预算翻倍
    r_hs_eff = P.COOLING[cooling]["r_hs"] / (2.0 if double_sided else 1.0)

    tok_per_tier = (P.CIM["array_rows"]["value"] * P.CIM["array_cols"]["value"]
                    * P.CIM["tiles_per_tier"]["value"] * P.CIM["freq_nom"]["value"]) / macs

    def powers_at(s):
        """给定吞吐 s，把能量分配到层上：每层按同一占空比跑，搬运能量落在逻辑层。"""
        duty = min(1.0, s / tok_ceiling)
        out = []
        for name, p, _ in roles:
            if name.startswith("cim"):
                out.append(p_tier * duty)
            elif name == "logic":
                out.append(p + s * spill_j_per_token)   # 存储接口烧掉搬运能量
            else:
                out.append(p)
        return out

    def solve_at(s):
        st = ThermalStack(powers_at(s), areas, cooling=cooling, double_sided=double_sided,
                          r_hs=r_hs_eff)
        T, leak, it, res = st.solve_with_leakage()
        tiers = [float(_clamp_temp(v)) for v in st.tier_temps(T)]
        return st, tiers, leak, it, res

    t_lim = P.STACK["t_jmax"]["value"]

    q_max = P.COOLING[cooling]["q_max"] * (2.0 if double_sided else 1.0)  # 双面 = 两个面各有一份热流预算

    def ok(s):
        """两道硬约束：结温 ≤ 上限；面热流密度 ≤ q_max。"""
        _, tiers, leak, _, _ = solve_at(s)
        p_total = float(sum(powers_at(s)) + sum(leak))
        return (max(tiers) <= t_lim) and (p_total / footprint <= q_max)

    def hot(s):
        _, tiers, *_ = solve_at(s)
        return max(tiers)

    # 可持续吞吐：二分（先看是不是算力本身就不够）
    lo, hi = 0.0, tok_ceiling
    if ok(hi):
        s_max, binding = hi, "compute"
    else:
        for _ in range(70):
            mid = 0.5 * (lo + hi)
            if ok(mid):
                lo = mid
            else:
                hi = mid
        s_max = lo
        _, tiers_m, leak_m, _, _ = solve_at(s_max)
        p_m = float(sum(powers_at(s_max)) + sum(leak_m))
        binding = "flux" if p_m / footprint > q_max - 1e-9 else "thermal"

    s_use = min(target, s_max)
    st_t, tiers_t, leak_t, it_t, res_t = solve_at(s_use)
    p_target = float(sum(powers_at(s_use)) + sum(leak_t))

    st_r, tiers_r, leak_r, it_r, res_r = solve_at(s_max)
    p_max = float(sum(powers_at(s_max)) + sum(leak_r))
    p_dyn_max = float(sum(powers_at(s_max)))

    return dict(
        n_cim=n_cim,
        n_layers=len(roles),
        cooling=cooling,
        double_sided=bool(double_sided),
        capacity_mb=cap,
        model_mb=need,
        resident_frac=resident,
        spill_mb=spill_mb,
        spill_j_per_token=spill_j_per_token,
        e_token_j=e_token,
        e_token_mj=e_token * 1e3,
        e_token_near_mj=e_token_near * 1e3,
        e_token_hbm_mj=led["hbm_j"] * 1e3,
        e_compute_mj=led["compute_j"] * 1e3,
        tok_s_target=target,
        tok_s_at_target=s_use,
        tok_s_max=s_max,
        tok_s_ceiling=tok_ceiling,
        binding_constraint=binding,
        q_max_w_mm2=q_max,
        headroom_vs_target=s_max / target,
        p_target_w=p_target,
        p_max_w=p_max,
        p_dyn_max_w=p_dyn_max,
        p_leak_max_w=float(sum(leak_r)),
        w_mm2_target=p_target / footprint,
        w_mm2_max=p_max / footprint,
        t_tiers_target_c=tiers_t,
        t_tiers_max_c=tiers_r,
        t_hot_target_c=max(tiers_t),
        t_hot_max_c=max(tiers_r),
        thermal_residual=res_r,
        leak_iters=it_r,
        pdn_target=PDN.evaluate(p_target),
        pdn_max=PDN.evaluate(p_max),
    )


def digital_baseline(e_mac_digital=0.5e-12):
    return (P.WORKLOAD["params"]["value"] * e_mac_digital
            + P.model_bytes() * 8.0 * P.WORKLOAD["e_ext"]["value"])
