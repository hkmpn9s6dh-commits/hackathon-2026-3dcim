"""供电：电流、TSV 载流、IR drop。

本模型最重要的作用是**证伪**「供电是 3D 堆叠的墙」这个常见说法：
在 24 mm² 足迹、20 个/mm² 供电 TSV 的设定下，IR drop 只有毫伏级；
真正的墙是足迹上的面功率密度。这条否定结果写进报告，不藏。
"""
from . import params as P


def evaluate(power_total_w, area_mm2=None):
    vdd = P.PDN["vdd"]["value"]
    area = P.CIM["tier_area"]["value"] if area_mm2 is None else area_mm2
    i_total = power_total_w / vdd

    n_tsv = P.PDN["tsv_density"]["value"] * area
    i_per_tsv = i_total / n_tsv
    i_max = P.PDN["tsv_i_max"]["value"]

    a_tsv = 3.141592653589793 * (P.PDN["tsv_d"]["value"] / 2) ** 2
    r_tsv_bundle = (P.PDN["rho_cu"]["value"] * P.PDN["tsv_len"]["value"]
                    / (n_tsv * a_tsv))
    dv_tsv = i_total * r_tsv_bundle
    dv_pkg = i_total * P.PDN["r_pkg"]["value"]
    dv_total = dv_tsv + dv_pkg
    limit = P.PDN["ir_limit"]["value"] * vdd

    return dict(
        i_total_a=i_total,
        n_tsv=n_tsv,
        i_per_tsv_ma=i_per_tsv * 1e3,
        tsv_current_ok=bool(i_per_tsv <= i_max),
        tsv_utilization=i_per_tsv / i_max,
        r_tsv_bundle_ohm=r_tsv_bundle,
        dv_tsv_mv=dv_tsv * 1e3,
        dv_pkg_mv=dv_pkg * 1e3,
        dv_total_mv=dv_total * 1e3,
        ir_limit_mv=limit * 1e3,
        ir_ok=bool(dv_total <= limit),
        ir_margin=1.0 - dv_total / limit,
        tsv_density_required=max(1e-9, i_total / (i_max * area)),
        tsv_density_ok=bool(P.PDN["tsv_density"]["value"] >= i_total / (i_max * area)),
        tsv_area_overhead_pct=(max(P.PDN["tsv_density"]["value"],
                                   i_total / (i_max * area))
                               * area * 3.141592653589793
                               * (P.PDN["tsv_d"]["value"] * 1e3 / 2) ** 2
                               / (area * 1e6) * 100.0),
    )


def min_tsv_density_for(power_total_w, area_mm2=None):
    """使单根 TSV 不超载所需的最小供电 TSV 面密度。"""
    vdd = P.PDN["vdd"]["value"]
    area = P.CIM["tier_area"]["value"] if area_mm2 is None else area_mm2
    i_total = power_total_w / vdd
    return i_total / (P.PDN["tsv_i_max"]["value"] * area)
