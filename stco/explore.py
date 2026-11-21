"""设计空间扫掠 + 层序优化 + 敏感度。build_results() 是 results.json 的唯一来源。"""
from itertools import permutations

from . import params as P
from . import design
from .thermal import ThermalStack
from . import pdn as PDN

N_RANGE = list(range(1, 9))


def sweep(n_range=None):
    rows = []
    for cooling in ("air", "liquid"):
        for ds in (False, True):
            for n in (N_RANGE if n_range is None else n_range):
                rows.append(design.evaluate(n, cooling=cooling, double_sided=ds))
    return rows


def capacity_plans():
    out = []
    for name, params, bits in (("1B@4bit", 1.0e9, 4), ("7B@4bit", 7.0e9, 4),
                               ("70B@4bit", 70.0e9, 4), ("70B@2bit", 70.0e9, 2),
                               ("7B@8bit", 7.0e9, 8)):
        n, need, per = design.plan_layers(params, bits)
        out.append(dict(model=name, model_mb=need, per_tier_mb=per, layers_needed=n,
                        footprint_mm2=P.CIM["tier_area"]["value"],
                        stack_height_um=n * P.STACK["die_thickness"]["value"] * 1e6))
    return out


def memory_strategies():
    led = design.energy_ledger()
    rows = []
    for key, label in (("resident_j", "全驻留（权重在存算阵列里）"),
                       ("near_j", "近存（层间键合读容量层）"),
                       ("hbm_j", "远存（外部 HBM）")):
        e = led[key]
        rows.append(dict(key=key, label=label, e_token_mj=e * 1e3,
                         power_at_50w=e * 50.0,
                         power_at_200w=e * 200.0))
    return rows


def placement(n_cim=3, cooling="liquid", double_sided=False, throughput=None,
              freq_scale=1.0):
    """穷举层序，按满速峰值结温排序（存算层同功耗 → 去重后 3!/... 种）。"""
    target = P.WORKLOAD["tok_s_target"]["value"] if throughput is None else throughput
    p_tier = P.cim_tier_power() * freq_scale
    roles = {"logic": (P.LAYERS["logic"]["p_dyn"], P.LAYERS["logic"]["area"]),
             "dram": (P.LAYERS["dram"]["p_dyn"], P.LAYERS["dram"]["area"])}
    for i in range(n_cim):
        roles[f"cim{i}"] = (p_tier, P.LAYERS["cim"]["area"])

    named = list(roles.items())
    seen, scored = set(), []
    for order in permutations(named):
        key = tuple("cim" if n.startswith("cim") else n for n, _ in order)
        if key in seen:
            continue
        seen.add(key)
        powers = [v[0] for _, v in order]
        areas = [v[1] for _, v in order]
        st = ThermalStack(powers, areas, cooling=cooling, double_sided=double_sided)
        T, _, _, _ = st.solve_with_leakage()
        scored.append((float(st.hot(T)), list(key)))
    scored.sort()
    return dict(best=dict(order=scored[0][1], t_hot_c=scored[0][0]),
                worst=dict(order=scored[-1][1], t_hot_c=scored[-1][0]),
                spread_k=scored[-1][0] - scored[0][0],
                n_perm=len(scored), all=[dict(order=o, t_hot_c=t) for t, o in scored])


def sensitivity(n_cim=None, cooling="liquid", double_sided=True, target=None):
    n_cim = design.plan_layers()[0] if n_cim is None else n_cim
    base = design.evaluate(n_cim, cooling=cooling, double_sided=double_sided, target=target)
    out = []
    knobs = [(P.CIM, "e_mac"), (P.CIM, "density"), (P.POWER, "leak_frac"),
             (P.WORKLOAD, "e_ext"), (P.STACK, "r_iface"), (P.CIM, "freq_nom")]
    for table, name in knobs:
        spec = table[name]
        if spec.get("lo") is None or spec.get("hi") is None:
            continue
        orig = spec["value"]
        row = dict(param=name, unit=spec["unit"], base=orig, lo=spec["lo"], hi=spec["hi"])
        for tag, val in (("lo", spec["lo"]), ("hi", spec["hi"])):
            spec["value"] = val
            r = design.evaluate(n_cim, cooling=cooling, double_sided=double_sided, target=target)
            row[f"value_{tag}"] = r["t_hot_max_c"]
            row[f"w_mm2_{tag}"] = r["w_mm2_max"]
            row[f"e_token_{tag}_mj"] = r["e_token_mj"]
            row[f"tok_{tag}"] = r["tok_s_max"]
        spec["value"] = orig
        row["value_base"] = base["t_hot_max_c"]
        row["w_mm2_base"] = base["w_mm2_max"]
        row["e_token_base_mj"] = base["e_token_mj"]
        row["t_swing_k"] = max(row["value_lo"], row["value_hi"]) - min(row["value_lo"], row["value_hi"])
        row["tok_base"] = base["tok_s_max"]
        row["tok_swing_ratio"] = (max(row["tok_lo"], row["tok_hi"])
                                  / max(1e-9, min(row["tok_lo"], row["tok_hi"])))
        out.append(row)
    out.sort(key=lambda r: -r["tok_swing_ratio"])
    return out


def pdn_budget():
    rows = []
    for p in (5, 10, 15, 20, 30, 40, 60, 80):
        r = PDN.evaluate(p)
        r["power_w"] = p
        rows.append(r)
    return rows


def build_results():
    rows = sweep()
    n_star = design.plan_layers()[0]
    design_point = design.evaluate(n_star, cooling="liquid", double_sided=False)
    air_point = design.evaluate(n_star, cooling="air", double_sided=False)
    liquid_ds = design.evaluate(n_star, cooling="liquid", double_sided=True)

    def pick(cooling, ds):
        return [r for r in rows if r["cooling"] == cooling and r["double_sided"] == ds]

    return dict(
        meta=dict(
            title="叠到第几层",
            subtitle="面向存内计算的 3D 异构集成架构与供电—热协同优化（STCO）",
            version="0.1.0",
            note="解析模型 + 数值求解。全部数字由本仓库复算，不是硅测量。",
        ),
        params=P.as_json(),
        capacity_plans=capacity_plans(),
        memory_strategies=memory_strategies(),
        n_star=dict(n=n_star, need_mb=design.model_mb(),
                    per_tier_mb=P.CIM["tier_area"]["value"] * P.CIM["density"]["value"]),
        design_point=design_point,
        air_point=air_point,
        liquid_double_sided=liquid_ds,
        sweep=rows,
        curves=dict(
            air=pick("air", False), liquid=pick("liquid", False),
            air_ds=pick("air", True), liquid_ds=pick("liquid", True),
        ),
        placement=placement(),
        sensitivity=sensitivity(),
        pdn_budget=pdn_budget(),
        digital_baseline=dict(e_token_j=design.digital_baseline(),
                              e_token_mj=design.digital_baseline() * 1e3),
    )
