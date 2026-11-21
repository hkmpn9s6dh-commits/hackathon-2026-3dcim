"""出图。所有数字读 results.json，不在这里手写任何结论值。"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyArrowPatch

matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False

C_INK = "#1c1c1e"
C_RED = "#b3261e"
C_BLUE = "#1d4e89"
C_GRAY = "#8a8a8e"
C_LIGHT = "#e8e4de"
C_GOLD = "#a9761f"


def _style(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(C_GRAY)
    ax.spines["bottom"].set_color(C_GRAY)
    ax.tick_params(colors=C_INK, labelsize=9)
    ax.grid(axis="y", color=C_LIGHT, lw=0.8)
    ax.set_axisbelow(True)


def fig_stack(res, out):
    """剖面示意：冷板 → 逻辑层 → 三层存算 → 可选容量层。标注放在右侧，不与图元相压。"""
    fig, ax = plt.subplots(figsize=(8.0, 4.6), dpi=200)
    ax.set_xlim(0.4, 8.7)
    ax.set_ylim(0.05, 6.45)
    ax.axis("off")

    w, h, gap = 4.6, 0.66, 0.26
    x0 = 2.6
    tiers = [("逻辑 / 互连层", "#e3cfc7"),
             ("存算层 1", "#c7d5e6"),
             ("存算层 2", "#c7d5e6"),
             ("存算层 3", "#c7d5e6"),
             ("容量 / 接口（可选）", "#e9e4da")]
    y = 0.85
    for label, color in tiers:
        ax.add_patch(Rectangle((x0, y), w, h, facecolor=color, edgecolor=C_INK, lw=1.0))
        ax.text(x0 + w / 2, y + h / 2, label, ha="center", va="center", fontsize=10, color=C_INK)
        y += h + gap
    top = y - gap

    # 混合键合面：只画在存算层之间
    for i in (2, 3):
        yy = 0.85 + i * (h + gap)
        ax.plot([x0, x0 + w], [yy, yy], color=C_GOLD, lw=3.0, alpha=0.9, solid_capstyle="butt")
    ax.annotate("混合键合面（2 µm 间距）\n两层之间只走这一条",
                xy=(x0 + w, 0.85 + 2 * (h + gap)), xytext=(x0 + w + 0.5, 4.05),
                fontsize=9, color=C_GOLD, va="center",
                arrowprops=dict(arrowstyle="-", color=C_GOLD, lw=1.0))

    # 供电 TSV：贯穿全栈
    for xf in (0.15, 0.42, 0.69, 0.96):
        xt = x0 + w * xf
        ax.plot([xt, xt], [0.42, top], color=C_RED, lw=1.8, alpha=0.85, zorder=5)
    ax.annotate("供电 TSV（背面供电）\n贯穿全栈，≥43 个/mm²",
                xy=(x0 + w * 0.96, 0.55), xytext=(x0 + w + 0.5, 0.95),
                fontsize=9, color=C_RED, va="center",
                arrowprops=dict(arrowstyle="-", color=C_RED, lw=1.0))

    # 冷板
    ax.add_patch(Rectangle((x0 - 0.3, 0.18), w + 0.6, 0.26, facecolor="#9fb7c9",
                           edgecolor=C_INK, lw=0.8))
    ax.text(x0 + w / 2, 0.31, "冷板 / 微流道（单面）", ha="center", va="center",
            fontsize=9, color="white")

    # 左侧高度标注
    ax.annotate("", xy=(x0 - 0.55, 0.85), xytext=(x0 - 0.55, top),
                arrowprops=dict(arrowstyle="<->", color=C_GRAY, lw=1.0))
    ax.text(x0 - 0.75, (0.85 + top) / 2, "4 层 · 200 µm", rotation=90, va="center",
            ha="center", fontsize=8.5, color=C_GRAY)

    ax.text(x0 - 0.3, 6.15, "足迹 24 mm²（5 × 4.8 mm）· 单层 50 µm · 标称 200 MHz",
            fontsize=9.5, color=C_INK)
    fig.tight_layout()
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def fig_scaling(res, out):
    fig, ax = plt.subplots(figsize=(7.2, 4.0), dpi=200)
    for key, label, color, ls in (("air", "风冷（单面）", C_RED, "-"),
                                  ("liquid", "冷板（单面）", C_BLUE, "-"),
                                  ("air_ds", "风冷（双面）", C_GOLD, "--")):
        rows = sorted(res["curves"][key], key=lambda r: r["n_cim"])
        xs = [r["n_cim"] for r in rows]
        ys = [r["tok_s_max"] for r in rows]
        ax.plot(xs, ys, ls, marker="o", ms=4.5, color=color, lw=1.8, label=label)
    target = res["params"]["workload"]["tok_s_target"]["value"]
    ax.axhline(target, color=C_GRAY, lw=1.0, ls=":")
    ax.text(7.6, target * 1.25, f"产品目标 {target:.0f} tok/s", fontsize=8.5, color=C_GRAY, ha="right")
    ax.set_yscale("log")
    ax.set_xlabel("存算层层数 N", fontsize=10)
    ax.set_ylabel("可持续吞吐 (tok/s，对数)", fontsize=10)
    ax.set_title("层数—吞吐：容量悬崖与热墙", fontsize=11.5, color=C_INK, pad=10)
    _style(ax)
    ax.legend(frameon=False, fontsize=9, loc="lower right")
    fig.tight_layout()
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def fig_energy(res, out):
    fig, ax = plt.subplots(figsize=(7.2, 3.6), dpi=200)
    rows = res["memory_strategies"]
    labels = [r["label"].split("（")[0] for r in rows]
    vals = [r["e_token_mj"] for r in rows]
    colors = ["#5b8c5a", C_BLUE, C_RED]
    bars = ax.bar(labels, vals, color=colors, width=0.55)
    ax.set_yscale("log")
    ax.set_ylabel("每 token 能量 (mJ，对数)", fontsize=10)
    ax.set_title("三种存储策略的能量账：差两个数量级", fontsize=11.5, color=C_INK, pad=10)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v * 1.25, f"{v:.2f} mJ", ha="center", fontsize=9.5)
    _style(ax)
    fig.tight_layout()
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def fig_thermal(res, out):
    """面热流密度 vs 层数：谁先撞到冷却的预算线。"""
    fig, ax = plt.subplots(figsize=(7.2, 3.8), dpi=200)
    for key, label, color in (("air", "风冷（单面）", C_RED), ("liquid", "冷板（单面）", C_BLUE)):
        rows = sorted(res["curves"][key], key=lambda r: r["n_cim"])
        xs = [r["n_cim"] for r in rows]
        ys = [r["w_mm2_max"] for r in rows]
        ax.plot(xs, ys, marker="o", ms=4.5, color=color, lw=1.8, label=label)
    ax.axhline(0.5, color=C_RED, ls=":", lw=1.0)
    ax.axhline(2.0, color=C_BLUE, ls=":", lw=1.0)
    ax.text(7.8, 0.56, "风冷预算 0.5 W/mm²", fontsize=8.5, color=C_RED, ha="right")
    ax.text(7.8, 2.12, "冷板预算 2.0 W/mm²", fontsize=8.5, color=C_BLUE, ha="right")
    ax.set_xlabel("存算层层数 N", fontsize=10)
    ax.set_ylabel("满速面热流密度 (W/mm²)", fontsize=10)
    ax.set_title("墙不在温度上，在足迹的热流密度上", fontsize=11.5, color=C_INK, pad=10)
    _style(ax)
    ax.legend(frameon=False, fontsize=9, loc="center right")
    fig.tight_layout()
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def fig_pdn(res, out):
    fig, ax = plt.subplots(figsize=(7.2, 3.6), dpi=200)
    rows = res["pdn_budget"]
    p = [r["power_w"] for r in rows]
    ir = [r["dv_total_mv"] for r in rows]
    need = [r["tsv_density_required"] for r in rows]
    ax.plot(p, ir, marker="o", ms=4, color=C_BLUE, lw=1.8, label="IR drop (mV)")
    ax.axhline(0.05 * 750, color=C_GRAY, ls=":", lw=1.0)
    ax.text(6, 40, "5% 预算 37.5 mV", fontsize=8.5, color=C_GRAY)
    ax.set_xlabel("单封装总功耗 (W)", fontsize=10)
    ax.set_ylabel("IR drop (mV)", fontsize=10)
    ax2 = ax.twinx()
    ax2.plot(p, need, marker="s", ms=4, color=C_RED, lw=1.6, ls="--", label="所需供电 TSV 密度")
    ax2.axhline(20, color=C_RED, ls=":", lw=1.0)
    ax2.set_ylabel("供电 TSV 密度 (个/mm²)", fontsize=10, color=C_RED)
    ax2.tick_params(axis="y", colors=C_RED, labelsize=9)
    ax.set_title("供电：IR 不是墙，单根 TSV 载流是", fontsize=11.5, color=C_INK, pad=10)
    _style(ax)
    fig.tight_layout()
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def fig_sensitivity(res, out):
    """单参数取区间两端时，设计点吞吐怎么动（对数横轴）。"""
    fig, ax = plt.subplots(figsize=(7.2, 3.8), dpi=200)
    rows = res["sensitivity"][:5]
    base = rows[0]["tok_base"]
    labels = [r["param"] for r in rows][::-1]
    for i, r in enumerate(rows[::-1]):
        ax.plot([r["tok_lo"], r["tok_hi"]], [i, i], color=C_GRAY, lw=1.2, zorder=1)
        ax.scatter([r["tok_lo"]], [i], color=C_BLUE, s=34, zorder=3)
        ax.scatter([r["tok_hi"]], [i], color=C_RED, s=34, zorder=3)
        ax.text(max(r["tok_lo"], r["tok_hi"]) * 1.15, i, f'{min(r["tok_lo"], r["tok_hi"]):,.0f}–{max(r["tok_lo"], r["tok_hi"]):,.0f}',
                va="center", fontsize=8, color=C_INK)
    ax.axvline(base, color=C_INK, lw=1.0, ls="--")
    ax.set_xscale("log")
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlabel("设计点可持续吞吐 (tok/s，对数)", fontsize=10)
    ax.set_title("敏感度：哪个参数能把结论推倒", fontsize=11.5, color=C_INK, pad=10)
    _style(ax)
    fig.tight_layout()
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def build_all(results_path, outdir):
    with open(results_path, encoding="utf-8") as f:
        res = json.load(f)
    os.makedirs(outdir, exist_ok=True)
    paths = dict(
        stack=os.path.join(outdir, "fig1-stack.png"),
        scaling=os.path.join(outdir, "fig2-scaling.png"),
        energy=os.path.join(outdir, "fig3-energy.png"),
        thermal=os.path.join(outdir, "fig4-thermal.png"),
        pdn=os.path.join(outdir, "fig5-pdn.png"),
        sensitivity=os.path.join(outdir, "fig6-sensitivity.png"),
    )
    fig_stack(res, paths["stack"])
    fig_scaling(res, paths["scaling"])
    fig_energy(res, paths["energy"])
    fig_thermal(res, paths["thermal"])
    fig_pdn(res, paths["pdn"])
    fig_sensitivity(res, paths["sensitivity"])
    return paths


if __name__ == "__main__":
    import sys
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    print(build_all(os.path.join(here, "out", "results.json"),
                    os.path.join(here, "out", "figures")))
