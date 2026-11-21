"""单一来源：所有参数、单位、来源与区间。

规矩（沿用 2026-11-21 的教训）：
  1. 报告里出现的每一个数字都必须能从 params + results 复算出来；
  2. 参数必须写清「来源类型」——pub(可核对公开数据) / est(工程估计) / derived(由前者算出)；
  3. 任何 est 参数都要在探索里做敏感度，结论若随它翻转，必须在报告里写出来。
"""
from dataclasses import dataclass, field, asdict


def _p(value, unit, kind, note, lo=None, hi=None):
    return dict(value=value, unit=unit, kind=kind, note=note, lo=lo, hi=hi)


# ---------------------------------------------------------------- 器件与阵列
CIM = dict(
    array_rows=_p(128, "cells", "pub", "典型 ReRAM 宏 128×128 交叉阵列"),
    array_cols=_p(128, "cells", "pub", "同上"),
    weight_bits=_p(4, "bit", "pub", "4-bit 权重（16 电平 MLC），CIM 主流精度档"),
    adc_bits=_p(8, "bit", "pub", "8-bit ADC，CIM 宏常见"),
    freq_nom=_p(200e6, "Hz", "pub", "ReRAM 宏 100–300 MHz，取 200", 100e6, 300e6),
    e_mac=_p(100e-15, "J/MAC", "pub",
             "10 TOPS/W @4b ≈ 100 fJ/MAC；文献 4-bit CIM 宏 5–50 TOPS/W → 40–400 fJ",
             40e-15, 400e-15),
    tiles_per_tier=_p(32, "tiles", "est", "每层 32 个宏，占 24 mm² 的一半左右（含 ADC/缓冲/布线）"),
    tier_area=_p(24.0, "mm^2", "est", "单层裸片面积，5×4.8 mm；堆叠足迹不随层数变"),
    density=_p(50.0, "MB/mm^2", "est",
               "4-bit MLC ReRAM 面密度：按 6F² 单元 + 4bit 的理论上限打折，取 50（=400 Mb/mm²）",
               12.5, 100.0),
)

# ---------------------------------------------------------------- 堆叠与封装
STACK = dict(
    die_thickness=_p(50e-6, "m", "pub", "混合键合前的减薄厚度 50 µm"),
    k_si=_p(120.0, "W/(m*K)", "pub", "硅热导率 100–150，取 120"),
    r_iface=_p(0.1, "K*mm^2/W", "pub", "混合键合界面热阻 0.05–0.2", 0.05, 0.2),
    r_tim=_p(0.3, "K*mm^2/W", "pub", "TIM 0.1–0.5", 0.1, 0.5),
    r_hs_air=_p(1.2, "K/W", "est", "小尺寸被动/低速风冷散热器，1.0–2.0", 1.0, 2.0),
    r_hs_liquid=_p(0.08, "K/W", "est", "冷板/微流道，0.05–0.15", 0.05, 0.15),
    t_amb=_p(35.0, "degC", "est", "边缘机房/户外机箱环境温度"),
    t_jmax=_p(85.0, "degC", "pub", "结温上限，商用档 85/105，取 85"),
)

# ---------------------------------------------------------------- 泄漏与 DVFS
POWER = dict(
    leak_frac=_p(0.08, "1", "est", "25 °C 下泄漏占动态功耗比例（先进节点 5–15%）", 0.05, 0.15),
    leak_double_dt=_p(20.0, "K", "pub", "泄漏每升高 20 K 翻倍（ Arrhenius 近似）"),
    dvfs_exponent=_p(3.0, "1", "pub", "V∝f 时动态功耗 ∝ f³（近阈值区 2–3）", 2.0, 3.0),
)

# ---------------------------------------------------------------- 工作负载
WORKLOAD = dict(
    params=_p(7.0e9, "params", "pub", "7B 级 LLM（Llama-2-7B 量级）"),
    bits=_p(4.0, "bit", "pub", "4-bit 量化权重"),
    e_ext=_p(5e-12, "J/bit", "pub", "外部 HBM3e 读能量 3–7 pJ/bit", 3e-12, 7e-12),
    e_hb=_p(0.05e-12, "J/bit", "pub", "混合键合层间链路 0.03–0.1 pJ/bit", 0.03e-12, 0.1e-12),
    act_bytes_per_token=_p(0.5e6, "B", "derived", "激活流量：2×d×L×batch ≈ 0.5 MB/token（可忽略）"),
    tok_s_target=_p(1000.0, "tok/s", "est", "产品目标：单封装 1000 tok/s 解码（7B@4bit，多路会话）"),
)

# ---------------------------------------------------------------- 供电
PDN = dict(
    vdd=_p(0.75, "V", "pub", "近阈值/低电压档 0.6–0.9，取 0.75"),
    r_pkg=_p(0.3e-3, "ohm", "est", "封装+基板供电路径（含板上去耦）0.2–0.5 mΩ", 0.2e-3, 0.5e-3),
    tsv_density=_p(20.0, "1/mm^2", "est", "供电 TSV 面密度（远低于信号键合密度）", 8.0, 40.0),
    tsv_i_max=_p(50e-3, "A", "pub", "5 µm Cu TSV 载流上限约 50 mA"),
    tsv_d=_p(5e-6, "m", "pub", "供电 TSV 直径 5 µm"),
    tsv_len=_p(200e-6, "m", "est", "贯穿 4 层的供电通路长度"),
    rho_cu=_p(1.7e-8, "ohm*m", "pub", "铜电阻率"),
    ir_limit=_p(0.05, "1", "pub", "IR drop 上限取 Vdd 的 5%"),
)

# ---------------------------------------------------------------- 冷却档位
# q_max：允许的面热流密度（W/mm²）。小足迹上真正卡人的是它，不是 R_hs：
# 热量从 24 mm² 的 die 摊到散热器上，扩散热阻决定了「一个平方毫米最多能出多少瓦」。
COOLING = {
    "air": dict(label="风冷（被动/低速风扇）", r_hs=STACK["r_hs_air"]["value"], q_max=0.5),
    "liquid": dict(label="冷板/微流道", r_hs=STACK["r_hs_liquid"]["value"], q_max=2.0),
}

# ---------------------------------------------------------------- 层角色
# 每层：role, 动态功耗(W) @ 标称频率, 面积(mm^2)
LAYERS = {
    "logic": dict(label="逻辑/互连层", p_dyn=3.0, area=24.0, kind="est"),
    "cim": dict(label="存算层", p_dyn=None, area=24.0, kind="derived"),
    "dram": dict(label="容量层（eDRAM/权重复制）", p_dyn=4.0, area=24.0, kind="est"),
}


def cim_tier_power(freq=None):
    """单个存算层的动态功耗（W）：每周期 16384 次 MAC，功耗 = MAC 数 × 每 MAC 能量 × 频率。"""
    f = CIM["freq_nom"]["value"] if freq is None else freq
    macs_per_cycle = CIM["array_rows"]["value"] * CIM["array_cols"]["value"]
    per_tile = macs_per_cycle * CIM["e_mac"]["value"] * f
    return per_tile * CIM["tiles_per_tier"]["value"]


def tier_throughput_mac_s(freq=None):
    f = CIM["freq_nom"]["value"] if freq is None else freq
    return (CIM["array_rows"]["value"] * CIM["array_cols"]["value"]
            * CIM["tiles_per_tier"]["value"] * f)


def model_bytes():
    return WORKLOAD["params"]["value"] * WORKLOAD["bits"]["value"] / 8.0


def as_json():
    return dict(cim=CIM, stack=STACK, power=POWER, workload=WORKLOAD, pdn=PDN,
                cooling={k: dict(label=v["label"], r_hs=v["r_hs"], q_max=v["q_max"]) for k, v in COOLING.items()},
                layers=LAYERS,
                derived=dict(
                    cim_tier_power_w=cim_tier_power(),
                    tier_throughput_macs=tier_throughput_mac_s(),
                    model_bytes=model_bytes(),
                    capacity_per_tier_mb=CIM["tier_area"]["value"] * CIM["density"]["value"],
                ))
