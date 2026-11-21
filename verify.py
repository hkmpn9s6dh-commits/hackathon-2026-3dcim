"""断言。跑法：py -3 verify.py  → 全过 EXIT=0，任一失败 EXIT=1。

分七组：参数 / 容量 / 能量 / 热 / 吞吐 / 供电 / 产物与确定性。
每一条都对应报告里的一个说法；报错信息说明「哪条结论会因此站不住」。
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from stco import params as P           # noqa: E402
from stco import design, explore, thermal  # noqa: E402
from stco.thermal import ThermalStack  # noqa: E402

OK, FAIL = [], []


def check(name, cond, note=""):
    (OK if cond else FAIL).append(name if not note else f"{name} — {note}")


def close(a, b, rel=1e-9, abs_=1e-12):
    return abs(a - b) <= max(abs_, rel * max(abs(a), abs(b)))


def main():
    # ---------------------------------------------------------------- 参数
    spec_tables = dict(CIM=P.CIM, STACK=P.STACK, POWER=P.POWER,
                       WORKLOAD=P.WORKLOAD, PDN=P.PDN)
    n_param = 0
    for tname, table in spec_tables.items():
        for key, spec in table.items():
            n_param += 1
            check(f"param:{tname}.{key}.fields",
                  {"value", "unit", "kind", "note"} <= set(spec),
                  "缺字段，报告里就无法复算")
            check(f"param:{tname}.{key}.kind", spec["kind"] in ("pub", "est", "derived"),
                  f"kind={spec.get('kind')}")
            if spec.get("lo") is not None and spec.get("hi") is not None:
                check(f"param:{tname}.{key}.range",
                      spec["lo"] <= spec["value"] <= spec["hi"],
                      f"{spec['lo']} <= {spec['value']} <= {spec['hi']}")
    check("params:count", n_param >= 30, f"只有 {n_param} 个参数")
    for k, v in P.COOLING.items():
        check(f"cooling:{k}.budget", v["q_max"] > 0 and v["r_hs"] > 0)

    # ---------------------------------------------------------------- 容量
    n_star, need, per = design.plan_layers()
    check("capacity:formula",
          close(design.capacity_mb(4), 4 * P.CIM["tier_area"]["value"] * P.CIM["density"]["value"]))
    check("capacity:n_star_is_3", n_star == 3, f"得到 {n_star}")
    check("capacity:3_fits", design.capacity_mb(3) >= need,
          f"{design.capacity_mb(3):.1f} < {need:.1f}")
    check("capacity:2_does_not_fit", design.capacity_mb(2) < need)
    check("capacity:monotone_in_params",
          design.plan_layers(7e9, 4)[0] > design.plan_layers(1e9, 4)[0],
          "参数量 7 倍，层数应当不降")
    check("capacity:bits_matter",
          design.plan_layers(7e9, 8)[0] > design.plan_layers(7e9, 4)[0])

    # ---------------------------------------------------------------- 能量
    led = design.energy_ledger()
    check("energy:compute_floor",
          close(led["compute_j"], P.WORKLOAD["params"]["value"] * P.CIM["e_mac"]["value"]))
    check("energy:resident_is_compute_plus_act",
          close(led["resident_j"], led["compute_j"] + led["act_j"]))
    check("energy:near_adds_hb",
          close(led["near_j"], led["resident_j"]
                + P.model_bytes() * 8 * P.WORKLOAD["e_hb"]["value"]))
    check("energy:hbm_adds_ext",
          close(led["hbm_j"], led["resident_j"]
                + P.model_bytes() * 8 * P.WORKLOAD["e_ext"]["value"]))
    check("energy:order", led["resident_j"] < led["near_j"] < led["hbm_j"])
    check("energy:ratio_equals_bit_energy_ratio",
          close((led["hbm_j"] - led["resident_j"]) / (led["near_j"] - led["resident_j"]),
                P.WORKLOAD["e_ext"]["value"] / P.WORKLOAD["e_hb"]["value"], rel=1e-9),
          "搬运部分的比值应当只由每 bit 能量决定")
    check("energy:digital_worse_than_cim",
          design.digital_baseline() > led["resident_j"])
    dp = design.evaluate(n_star, "liquid")
    check("energy:no_spill_at_n_star", close(dp["spill_mb"], 0.0))
    check("energy:spill_at_2",
          close(design.evaluate(2, "liquid")["spill_mb"], need - design.capacity_mb(2)))

    # ---------------------------------------------------------------- 热
    area = P.CIM["tier_area"]["value"]
    r_total = (P.COOLING["air"]["r_hs"] + P.STACK["r_tim"]["value"] / area
               + P.STACK["r_iface"]["value"] / area)
    st1 = ThermalStack([10.0], [area], cooling="air")
    T1, _, _, _ = st1.solve_with_leakage()
    r_with_leak = (T1[1] - P.STACK["t_amb"]["value"]) / 10.0
    P.POWER["leak_frac"]["value"] = 0.0          # 临时关泄漏，做解析对齐
    T1_nl, _, _, _ = st1.solve_with_leakage()
    P.POWER["leak_frac"]["value"] = 0.08
    check("thermal:analytic_single_layer",
          close(T1_nl[1], thermal.analytic_single_node(10.0, r_total, P.STACK["t_amb"]["value"]), rel=1e-9),
          "一维热网络的单层解与解析式不一致")
    check("thermal:zero_power_is_ambient",
          np.allclose(ThermalStack([0.0, 0.0, 0.0], [area] * 3).solve(), P.STACK["t_amb"]["value"]))
    check("thermal:symmetry", np.allclose(st1.G, st1.G.T), "热导矩阵不对称")
    check("thermal:interior_column_sum",
          abs(st1.G[1, 0] + st1.G[1, 1]) < 1e-9, "内部节点热流不守恒")
    check("thermal:residual_design", dp["thermal_residual"] < 1e-8,
          f"残差 {dp['thermal_residual']:.2e}")
    check("thermal:leakage_doubles_per_dt",
          close(float(ThermalStack([10.0], [area]).leakage_power([25.0 + P.POWER["leak_double_dt"]["value"]])[0]),
                2 * float(ThermalStack([10.0], [area]).leakage_power([25.0])[0]), rel=1e-9))
    check("thermal:leakage_at_85",
          close(float(ThermalStack([10.0], [area]).leakage_power([85.0])[0]),
                10.0 * 0.08 * 2 ** ((85 - 25) / 20), rel=1e-9))
    st3 = ThermalStack([10.0, 10.0, 10.0], [area] * 3, cooling="air")
    Ta, _, _, _ = st3.solve_with_leakage()
    Tb, _, _, _ = st3.solve_with_leakage(max_iter=400)
    check("thermal:fixed_point_stable", np.allclose(Ta, Tb, atol=1e-8),
          "迭代次数加倍后解变了，说明没收敛")
    check("thermal:monotone_in_power",
          ThermalStack([20.0], [area]).solve()[1] > ThermalStack([10.0], [area]).solve()[1])
    # 泄漏关掉时应当是线性的
    P.POWER["leak_frac"]["value"] = 0.0
    t_1x = ThermalStack([10.0, 10.0], [area] * 2).solve()
    t_2x = ThermalStack([20.0, 20.0], [area] * 2).solve()
    P.POWER["leak_frac"]["value"] = 0.08
    d1 = t_1x - P.STACK["t_amb"]["value"]
    d2 = t_2x - P.STACK["t_amb"]["value"]
    check("thermal:linear_without_leakage", np.allclose(d2, 2 * d1, rtol=1e-9))

    # ---------------------------------------------------------------- 吞吐
    rows = explore.sweep([1, 2, 3, 4, 5, 6, 7, 8])
    air = {r["n_cim"]: r for r in rows if r["cooling"] == "air" and not r["double_sided"]}
    liq = {r["n_cim"]: r for r in rows if r["cooling"] == "liquid" and not r["double_sided"]}
    for n, r in list(air.items()) + list(liq.items()):
        check(f"throughput:cap_ceiling_n{n}",
              r["tok_s_max"] <= r["tok_s_ceiling"] * (1 + 1e-12),
              "吞吐超过算力上限")
        check(f"throughput:flux_budget_n{n}_{r['cooling']}",
              r["w_mm2_max"] <= r["q_max_w_mm2"] * (1 + 1e-9),
              f"{r['w_mm2_max']:.3f} > {r['q_max_w_mm2']}")
        check(f"throughput:constraint_label_n{n}_{r['cooling']}",
              r["binding_constraint"] in ("compute", "thermal", "flux"))
    check("throughput:cliff_air", air[3]["tok_s_max"] / air[2]["tok_s_max"] > 10,
          f"悬崖倍数只有 {air[3]['tok_s_max'] / air[2]['tok_s_max']:.1f}")
    check("throughput:plateau_air", abs(air[8]["tok_s_max"] / air[4]["tok_s_max"] - 1) < 0.01,
          "风冷 4→8 层吞吐应当持平")
    check("throughput:plateau_liquid", abs(liq[8]["tok_s_max"] / liq[5]["tok_s_max"] - 1) < 0.01,
          "冷板 5→8 层吞吐应当持平")
    check("throughput:peak_within_4_tiers",
          max(liq.values(), key=lambda r: r["tok_s_max"])["n_cim"] <= 4,
          "冷板峰值不该出现在 5 层以后")
    check("throughput:design_is_flux_bound", dp["binding_constraint"] == "flux",
          f"设计点受限项应为热流密度，实际 {dp['binding_constraint']}")
    check("throughput:compute_headroom_left", dp["tok_s_ceiling"] > dp["tok_s_max"],
          "算力上限应当还没被用满，否则第 8 页的说法不成立")
    check("throughput:design_above_target",
          dp["tok_s_max"] > P.WORKLOAD["tok_s_target"]["value"])
    check("throughput:target_not_reached_at_2_air",
          air[2]["tok_s_max"] < P.WORKLOAD["tok_s_target"]["value"],
          "2 层就已经够目标，容量悬崖的故事不成立")

    # ---------------------------------------------------------------- 供电
    pd = dp["pdn_max"]
    check("pdn:current", close(pd["i_total_a"], dp["p_max_w"] / P.PDN["vdd"]["value"]))
    check("pdn:tsv_count", close(pd["n_tsv"], P.PDN["tsv_density"]["value"] * P.CIM["tier_area"]["value"]))
    check("pdn:per_tsv", close(pd["i_per_tsv_ma"], pd["i_total_a"] / pd["n_tsv"] * 1e3))
    check("pdn:ir_sum", close(pd["dv_total_mv"], pd["dv_tsv_mv"] + pd["dv_pkg_mv"], rel=1e-9))
    check("pdn:pkg_ir", close(pd["dv_pkg_mv"], pd["i_total_a"] * P.PDN["r_pkg"]["value"] * 1e3, rel=1e-9))
    check("pdn:ir_ok_flag", pd["ir_ok"] == (pd["dv_total_mv"] <= pd["ir_limit_mv"]))
    check("pdn:density_required",
          close(pd["tsv_density_required"],
                pd["i_total_a"] / (P.PDN["tsv_i_max"]["value"] * P.CIM["tier_area"]["value"]), rel=1e-9))
    check("pdn:density_not_ok_at_default", not pd["tsv_density_ok"],
          "默认 20 个/mm² 竟然够用，第 10 页的规格要改写")
    lo_d = P.PDN["tsv_density"]["value"]
    hi_d = pd["tsv_density_required"]
    P.PDN["tsv_density"]["value"] = hi_d
    dv_hi = __import__("stco.pdn", fromlist=["evaluate"]).evaluate(dp["p_max_w"])["dv_tsv_mv"]
    P.PDN["tsv_density"]["value"] = lo_d
    check("pdn:ir_drops_with_density", dv_hi < pd["dv_tsv_mv"])

    # ---------------------------------------------------------------- 确定性 / 产物
    r1 = json.dumps(explore.build_results(), ensure_ascii=False, sort_keys=True)
    r2 = json.dumps(explore.build_results(), ensure_ascii=False, sort_keys=True)
    check("determinism:two_runs_identical", r1 == r2, "两次运行结果不同，报告不可复现")
    check("json:no_nan", "NaN" not in r1 and "Infinity" not in r1)
    res_path = os.path.join(HERE, "out", "results.json")
    if os.path.exists(res_path):
        with open(res_path, encoding="utf-8") as f:
            on_disk = json.load(f)
        check("json:on_disk_matches",
              json.dumps(on_disk, ensure_ascii=False, sort_keys=True) == r1,
              "磁盘上的 results.json 不是最新模型跑出来的")

    pdf = os.path.join(HERE, "out", "3D-CIM-STCO-v1.0.pdf")
    check("artifact:pdf_exists", os.path.exists(pdf) and os.path.getsize(pdf) > 200_000)
    if os.path.exists(pdf):
        import fitz
        doc = fitz.open(pdf)
        check("artifact:pdf_pages", doc.page_count == 14, f"页数 {doc.page_count}")
        text = "".join(p.get_text() for p in doc)
        need_air = f"{air[3]['tok_s_max']:,.0f}"
        need_liq = f"{dp['tok_s_max']:,.0f}"
        for needle in (need_air, need_liq, "叠到第几层", "不是硅测量"):
            check(f"artifact:pdf_text:{needle}", needle in text, "报告里没出现这个关键数字")

    figs = os.path.join(HERE, "out", "figures")
    for name in ("fig1-stack.png", "fig2-scaling.png", "fig3-energy.png",
                 "fig4-thermal.png", "fig5-pdn.png", "fig6-sensitivity.png"):
        p_ = os.path.join(figs, name)
        check(f"artifact:fig:{name}", os.path.exists(p_) and os.path.getsize(p_) > 20_000)
    site = os.path.join(HERE, "site", "index.html")
    check("artifact:site", os.path.exists(site) and os.path.getsize(site) > 20_000)
    if os.path.exists(site):
        with open(site, encoding="utf-8") as f:
            html = f.read()
        check("artifact:site_numbers",
              f"{air[3]['tok_s_max']:,.0f}" in html and f"{dp['tok_s_max']:,.0f}" in html)

    # ---------------------------------------------------------------- 汇总
    total = len(OK) + len(FAIL)
    print(f"PASS {len(OK)} / {total}")
    if FAIL:
        print("\nFAILED:")
        for f in FAIL:
            print("  ✗", f)
        return 1
    print("EXIT=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
