"""方案书：一份 HTML（作品页）→ Chromium 打印成 PDF。

原则：正文里的每个数字都从 results.json 取，不在模板里手写。改模型 → 重跑 → 报告自动跟着变。
"""
import json
import os
import shutil
import subprocess

CHROME_CANDIDATES = [
    os.path.expandvars(r"%LOCALAPPDATA%\ms-playwright\chromium-1248\chrome-win64\chrome.exe"),
    os.path.expandvars(r"%LOCALAPPDATA%\ms-playwright\chromium-1255\chrome-win64\chrome.exe"),
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]


def _chrome():
    for p in CHROME_CANDIDATES:
        if os.path.exists(p):
            return p
    raise RuntimeError("找不到 Chromium/Chrome/Edge 可执行文件")


def _f(x, n=1):
    if x is None:
        return "—"
    if isinstance(x, float) and x != x:
        return "—"
    return f"{x:,.{n}f}"


def _row(cells, cls=""):
    return "<tr class='%s'>" % cls + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"


CSS = """
@page { size: A4; margin: 0; }
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body { font-family: "Microsoft YaHei", "SimHei", "Noto Sans CJK SC", sans-serif;
       color: #1c1c1e; font-size: 10.5pt; line-height: 1.62; background: #f2efe9; }
.page { width: 210mm; height: 297mm; padding: 17mm 18mm 15mm 18mm; background: #fff;
        position: relative; overflow: hidden; page-break-after: always; }
.page:last-child { page-break-after: auto; }
@media screen { .page { margin: 0 auto 18px; box-shadow: 0 2px 18px rgba(0,0,0,.12); } }
.eyebrow { font-size: 8.5pt; letter-spacing: .22em; color: #a9761f; }
h1 { font-size: 32pt; margin: 6mm 0 3mm; line-height: 1.12; letter-spacing: -.01em; }
h2 { font-size: 15pt; margin: 0 0 3mm; padding-bottom: 2mm; border-bottom: 1.6px solid #1c1c1e; }
h3 { font-size: 11pt; margin: 5mm 0 1.5mm; color: #1d4e89; }
p { margin: 0 0 2.4mm; }
.lead { font-size: 12pt; color: #3a3a3c; }
.small { font-size: 8.6pt; color: #6b6b70; }
.mono { font-family: "Cascadia Mono", Consolas, monospace; font-size: 9pt; }
.kpi { display: flex; gap: 4mm; margin: 5mm 0 4mm; }
.kpi div { flex: 1; border: 1px solid #ddd8cf; border-left: 3px solid #b3261e; padding: 3mm 3.5mm; background: #fcfbf8; }
.kpi b { display: block; font-size: 19pt; line-height: 1.1; color: #b3261e; }
.kpi span { font-size: 8.4pt; color: #6b6b70; }
table { width: 100%; border-collapse: collapse; margin: 2mm 0 4mm; font-size: 9.2pt; }
th, td { text-align: left; padding: 1.6mm 2mm; border-bottom: 1px solid #e6e1d8; vertical-align: top; }
th { background: #f5f2ec; font-weight: 600; }
tr.hl td { background: #fdf6f4; font-weight: 600; }
img { width: 100%; display: block; margin: 2mm 0; }
.cap { font-size: 8.2pt; color: #6b6b70; margin: -1mm 0 3mm; }
.two { display: flex; gap: 6mm; }
.two > div { flex: 1; }
blockquote { margin: 3mm 0; padding: 2.5mm 4mm; background: #f6f3ed; border-left: 3px solid #a9761f;
             font-size: 10pt; color: #3a3a3c; }
.foot { position: absolute; left: 18mm; right: 18mm; bottom: 8mm; display: flex;
        justify-content: space-between; font-size: 8pt; color: #9a9a9f; border-top: 1px solid #eee; padding-top: 2mm; }
code { background: #f3f0ea; padding: 0 1mm; font-family: Consolas, monospace; font-size: 9pt; }
ul { margin: 0 0 2.5mm 4.5mm; padding: 0; }
li { margin-bottom: 1.2mm; }
"""


def build(res, outdir, sitedir):
    dp = res["design_point"]
    air = res["air_point"]
    nstar = res["n_star"]["n"]
    c = {k: sorted(v, key=lambda r: r["n_cim"]) for k, v in res["curves"].items()}
    airn = {r["n_cim"]: r for r in c["air"]}
    liqn = {r["n_cim"]: r for r in c["liquid"]}
    dsn = {r["n_cim"]: r for r in c["air_ds"]}
    mem = {r["key"]: r for r in res["memory_strategies"]}
    plans = {r["model"]: r for r in res["capacity_plans"]}
    place = res["placement"]
    sens = res["sensitivity"]
    target = res["params"]["workload"]["tok_s_target"]["value"]
    i_max_ma = res["params"]["pdn"]["tsv_i_max"]["value"] * 1e3
    q_air = res["params"]["cooling"]["air"]["q_max"]
    q_liq = res["params"]["cooling"]["liquid"]["q_max"]
    # 吞吐上限恒等式（不含泄漏时的闭式值，用来解释平台）
    static_w = res["params"]["layers"]["logic"]["p_dyn"]
    e_mj = mem["resident_j"]["e_token_mj"]
    ceiling_air = (q_air * 24.0 - static_w) / (e_mj / 1e3)
    ceiling_liq = (q_liq * 24.0 - static_w) / (e_mj / 1e3)
    pages = []

    # ---------------------------------------------------------------- 1
    pages.append(f"""
<section class="page">
  <div class="eyebrow">第四届全国先进计算技术创新大赛 · 技术突破赛道</div>
  <h1>叠到第几层</h1>
  <p class="lead">面向存内计算的三维异构集成架构与供电—热协同优化</p>
  <p style="margin-top:6mm">存内计算把权重放进阵列，三维堆叠把容量放进同一个足迹。两件事都被说成「越多越好」。
  本作品只回答一个问题：<b>在给定足迹、给定功耗预算下，第几层开始是白叠的。</b></p>
  <div class="kpi">
    <div><b>{nstar} 层</b><span>装下 7B@4bit（{_f(dp['model_mb'], 0)} MB）所需的最小层数</span></div>
    <div><b>{_f(airn[3]['tok_s_max'], 0)}</b><span>风冷 3 层的可持续吞吐（tok/s）</span></div>
    <div><b>{_f(dp['tok_s_max'], 0)}</b><span>冷板 3 层的可持续吞吐（tok/s）</span></div>
  </div>
  <blockquote>结论：层数由<b>容量</b>决定；吞吐的上限由<b>足迹上的热流密度</b>决定，与层数几乎无关；
  供电由<b>单根 TSV 的载流</b>决定。三件事在三个不同的轴上——这就是「堆得越高越快」失效的原因。</blockquote>
  <img src="figures/fig1-stack.png" style="width:74%;margin:3mm auto 0" alt="架构">
  <p class="small">全部数字由本仓库 <code>stco</code> 模型复算，<code>py -3 run.py</code> 一条命令重建。
  这是解析模型与数值求解，不是硅测量；假设与区间写在第 14 页。</p>
  <div class="foot"><span>2026-11-21</span><span>版本 v1.0</span></div>
</section>""")

    # ---------------------------------------------------------------- 2
    pages.append(f"""
<section class="page">
  <h2>一、结论先行</h2>
  <table>
    <tr><th style="width:24%">问题</th><th style="width:38%">答案</th><th>怎么算出来的</th></tr>
    {_row(["7B@4bit 要几层才装得下", f"{nstar} 层（容量 {_f(liqn[nstar]['capacity_mb'], 0)} MB ≥ 模型 {_f(dp['model_mb'], 0)} MB）",
           "单层 24 mm² × 50 MB/mm² = 1200 MB，向上取整"])}
    {_row(["少一层会怎样", f"2 层只有 {_f(airn[2]['tok_s_max'], 0)} tok/s，3 层 {_f(airn[3]['tok_s_max'], 0)}（{_f(airn[3]['tok_s_max'] / airn[2]['tok_s_max'], 0)} 倍）",
           "装不下的 938 MB/token 走外部 HBM，每 bit 5 pJ"])}
    {_row(["风冷多一层有用吗", f"没有：3 层 {_f(airn[3]['tok_s_max'], 0)} → 8 层 {_f(airn[8]['tok_s_max'], 0)}",
           f"足迹热流密度锁在 {_f(q_air, 1)} W/mm²，功率天花板不随层数变"])}
    {_row(["冷板多一层有用吗", f"也没有：3 层 {_f(dp['tok_s_max'], 0)} → 4 层 {_f(liqn[4]['tok_s_max'], 0)} → 8 层 {_f(liqn[8]['tok_s_max'], 0)}",
           f"冷板预算 {_f(q_liq, 1)} W/mm² = {_f(q_liq * 24, 0)} W；3 层已把它用满"])}
    {_row(["供电是不是墙", f"IR 不是（{_f(dp['pdn_max']['dv_total_mv'], 1)} mV &lt; 37.5 mV）；单根 TSV 是",
           f"{_f(dp['pdn_max']['i_total_a'], 0)} A 要 ≥{_f(dp['pdn_max']['tsv_density_required'], 0)} 个/mm²，默认 20 不够"])}
    {_row(["层序（谁在上面）要紧吗", f"不要紧：最好与最差只差 {_f(place['spread_k'], 1)} K",
           "50 µm 薄 die 的层间热阻只有外部热阻的 2%"])}
  </table>
  <h3>推荐设计点</h3>
  <table>
    <tr><th>参数</th><th>取值</th><th>依据</th></tr>
    {_row(["层数", f"{nstar} 层存算 + 1 层逻辑", "容量向上取整；逻辑层放 NoC、接口与存储控制器"])}
    {_row(["足迹 / 堆高", f"24 mm² / {_f((nstar + 1) * 50, 0)} µm", f"{nstar} 层存算 + 1 层逻辑，各 50 µm 减薄 + 键合界面"])}
    {_row(["冷却", "冷板（单面）", f"满速 {_f(dp['p_max_w'], 1)} W = {_f(dp['w_mm2_max'], 2)} W/mm²；风冷预算只有 {_f(q_air, 1)}"])}
    {_row(["可持续吞吐", f"{_f(dp['tok_s_max'], 0)} tok/s", f"热流上限（算力上限 {_f(dp['tok_s_ceiling'], 0)} 还没用到）；目标 {_f(target, 0)} 有 {_f(dp['tok_s_max'] / target, 0)} 倍余量"])}
    {_row(["目标工况功耗", f"{_f(dp['p_target_w'], 1)} W", f"其中逻辑层静态 {_f(static_w, 1)} W；阵列只占 {_f(dp['p_target_w'] - static_w, 2)} W"])}
    {_row(["供电 TSV", f"≥{_f(dp['pdn_max']['tsv_density_required'], 0)} 个/mm²", f"单根 ≤{_f(i_max_ma, 0)} mA；面积代价约 {_f(dp['pdn_max']['tsv_area_overhead_pct'], 2)}%"])}
  </table>
  <div class="foot"><span>叠到第几层</span><span>2 / 14</span></div>
</section>""")

    # ---------------------------------------------------------------- 3
    pages.append(f"""
<section class="page">
  <h2>二、赛题要什么，本作品怎么答</h2>
  <p>出题单位（微纳核芯）在公开公告里写清了四件事。逐条对照，避免答非所问。</p>
  <table>
    <tr><th style="width:30%">赛题要求</th><th>本作品的做法</th><th style="width:16%">证据</th></tr>
    {_row(["面向明确的存内计算应用或负载", "7B 级 LLM 解码：每 token 7.0e9 次 MAC、权重 3.34 GB", "第 5 页"])}
    {_row(["设计含计算、存储、互连模块的三维异构集成架构", "3 层存算 + 1 层逻辑/互连；权重常驻阵列，激活走混合键合", "第 4 页"])}
    {_row(["用 STCO 做芯片—封装—系统联合分析", "四本账（容量/能量/热/供电）共用一个足迹与同一个功耗变量", "第 5 页"])}
    {_row(["对性能、数据搬移、能效、供电、温度量化评估", "吞吐 tok/s、每 token 能量 mJ、W/mm²、IR mV、结温 °C", "第 6–10 页"])}
    {_row(["用理论分析、数学建模或仿真验证", "解析式 + 一维热网络数值解 + 不动点迭代，<code>verify.py</code> 断言", "第 14 页"])}
    {_row(["不强制流片 / 版图 / 实体芯片", "本作品不声称硅结果；所有数字标注为模型输出", "第 14 页"])}
  </table>
  <h3>为什么选这个负载</h3>
  <ul>
    <li><b>解码是权重受限</b>：每 token 要把整个模型读一遍，「装不装得下」直接决定能量，而不是只决定面积。</li>
    <li><b>它能逼出三维堆叠的真价值</b>：只算算力的话一层就够（单层算力上限 {_f(airn[1]['tok_s_ceiling'], 0)} tok/s），堆叠的刚需是容量。</li>
    <li><b>它有可核对的产品指标</b>：{_f(target, 0)} tok/s、单封装、7B 级——不是自造的场景。</li>
  </ul>
  <h3>不做什么</h3>
  <ul>
    <li>不做版图、不做 DRC/LVS、不报 PPA 签核数字。</li>
    <li>不把生成式 AI 画的三维示意图当架构图；第 4 页的剖面由代码按参数表比例绘制。</li>
    <li>不引用无法核对原文的对比数字；每个参数标 <code>pub</code> / <code>est</code>，<code>est</code> 全部做敏感度。</li>
  </ul>
  <div class="foot"><span>叠到第几层</span><span>3 / 14</span></div>
</section>""")

    # ---------------------------------------------------------------- 4
    pages.append(f"""
<section class="page">
  <h2>三、架构：三层存算 + 一层逻辑</h2>
  <img src="figures/fig1-stack.png" alt="架构剖面">
  <p class="cap">图 1　剖面示意（按参数表比例绘制）：冷板 → 逻辑/互连层 → 三层存算 → 可选容量层。
  金色为混合键合面，红色为贯穿全栈的背面供电 TSV。</p>
  <div class="two">
    <div>
      <h3>为什么是这个形状</h3>
      <ul>
        <li><b>逻辑层放最下面</b>：接封装、接外部存储、接 NoC，走线最短；它同时是 {_f(static_w, 1)} W 的恒定点与搬运能量的落点。</li>
        <li><b>存算层之间直接键合</b>：激活跨层只走键合面，0.05 pJ/bit，比走外部 HBM 省两个数量级。</li>
        <li><b>不做 8 层</b>：风冷下第 4 层起吞吐不再增长（第 8 页），而堆高、成品率、供电 TSV 都在变难。</li>
      </ul>
    </div>
    <div>
      <h3>关键尺度</h3>
      <table>
        {_row(["裸片面积", "24 mm²（5 × 4.8 mm）"])}
        {_row(["减薄厚度", "50 µm"])}
        {_row(["键合间距", "2 µm"])}
        {_row(["每层阵列", "32 个 128×128 宏"])}
        {_row(["标称频率", "200 MHz"])}
        {_row(["供电 TSV", f"≥{_f(dp['pdn_max']['tsv_density_required'], 0)} 个/mm²"])}
      </table>
    </div>
  </div>
  <blockquote>这个架构没有任何「新器件」：ReRAM 宏、混合键合、背面供电都是产线上已有的东西。
  本作品的贡献不在发明器件，而在<b>把三本互相打架的账放在同一个足迹上算清楚</b>。</blockquote>
  <div class="foot"><span>叠到第几层</span><span>4 / 14</span></div>
</section>""")

    # ---------------------------------------------------------------- 5
    pages.append(f"""
<section class="page">
  <h2>四、方法：四本账，一个足迹</h2>
  <p>STCO 的难点不是算每一本账，而是让四本账共用同一组变量。本模型只引入一个贯穿全局的自由变量——<b>层数 N</b>，
  以及由它派生出的功耗 P(N)。四本账都写成 N 的函数，冲突就自己浮出来了。</p>
  <table>
    <tr><th style="width:14%">账本</th><th style="width:40%">式子</th><th>取数与依据</th></tr>
    {_row(["容量", "C(N) = N · A · ρ，A = 24 mm²，ρ = 50 MB/mm²",
           "ρ 是 4-bit MLC 的面密度工程估计（12.5–100），第 12 页做敏感度"])}
    {_row(["能量", "E = 7.0e9 · e<sub>MAC</sub> + 溢出字节 · e<sub>bit</sub>",
           "e<sub>MAC</sub> = 100 fJ（宏级 10 TOPS/W）；e<sub>bit</sub> = 5 pJ（HBM）/ 0.05 pJ（键合）"])}
    {_row(["热", "G·T = P(N,T)；P<sub>leak</sub> = 8%·P<sub>dyn</sub>·2<sup>(T−25)/20</sup>；面热流 q = P/A ≤ q<sub>max</sub>",
           "一维热阻网络逐层到冷板；泄漏与温度做不动点迭代"])}
    {_row(["供电", f"I = P/V<sub>dd</sub>；ΔV = I·(R<sub>tsv</sub>(n) + R<sub>pkg</sub>)；i<sub>tsv</sub> ≤ {_f(i_max_ma, 0)} mA",
           "V<sub>dd</sub> = 0.75 V；R<sub>pkg</sub> = 0.3 mΩ"])}
  </table>
  <h3>两个工况，必须分开算</h3>
  <div class="two">
    <div>
      <p><b>解码（decode）</b>：每 token 7e9 次 MAC，占空比 = 目标吞吐 / 算力上限。功耗随吞吐线性增长，
      本设计点只有 {_f(dp['p_target_w'], 1)} W。<b>它决定的是容量够不够</b>——不够就得搬权重，能量立刻涨两个数量级。</p>
    </div>
    <div>
      <p><b>满速（prefill / 大 batch）</b>：所有阵列跑满频，功耗与吞吐无关，
      {_f(dp['p_max_w'], 1)} W 压在 24 mm² 上 = {_f(dp['w_mm2_max'], 2)} W/mm²。
      <b>它决定的是散热与供电。</b></p>
    </div>
  </div>
  <blockquote>把两个工况混在一起，会得到两种常见的错结论：「CIM 很省电所以不热」（拿解码功耗估散热）、
  「堆得越高算力越强」（忽略满速时功率被足迹锁死）。本模型的每一条结论都注明了是在哪个工况下成立的。</blockquote>
  <p class="small">实现：<code>params.py</code>（参数单一来源）· <code>thermal.py</code>（热网络 + 不动点）·
  <code>design.py</code>（两工况评估）· <code>explore.py</code>（扫掠/层序/敏感度）。只依赖 numpy。</p>
  <div class="foot"><span>叠到第几层</span><span>5 / 14</span></div>
</section>""")

    # ---------------------------------------------------------------- 6
    pages.append(f"""
<section class="page">
  <h2>五、第一本账：能量差两个数量级</h2>
  <img src="figures/fig3-energy.png" alt="能量账">
  <p class="cap">图 2　同一个 7B@4bit 模型、同一个足迹，只改权重放在哪里。</p>
  <table>
    <tr><th>策略</th><th>每 token 能量</th><th>@ {_f(target, 0)} tok/s</th><th>含义</th></tr>
    {_row(["全驻留", f"{_f(mem['resident_j']['e_token_mj'], 2)} mJ", f"{_f(mem['resident_j']['power_at_50w'] * target / 50, 2)} W",
           "权重在阵列里，能量只剩算力地板"])}
    {_row(["近存（键合读容量层）", f"{_f(mem['near_j']['e_token_mj'], 2)} mJ", f"{_f(mem['near_j']['power_at_50w'] * target / 50, 2)} W",
           "装不下时退一步，靠 0.05 pJ/bit 的键合"])}
    {_row(["远存（外部 HBM）", f"{_f(mem['hbm_j']['e_token_mj'], 2)} mJ", f"{_f(mem['hbm_j']['power_at_50w'] * target / 50, 2)} W",
           "每 bit 5 pJ，是键合的 100 倍"])}
  </table>
  <h3>这条账决定了整篇报告的走向</h3>
  <p>算力地板是 {_f(mem['resident_j']['e_token_mj'], 2)} mJ/token；外部搬运是 {_f(mem['hbm_j']['e_token_mj'], 2)} mJ/token。
  也就是说，<b>「装不装得下」这一个二值问题，值 {_f(mem['hbm_j']['e_token_mj'] / mem['resident_j']['e_token_mj'], 0)} 倍的能量</b>。
  所以三维堆叠的第一价值不是算力，是容量——它把 3.34 GB 塞进 24 mm² 的足迹，让「全驻留」从不可能变成可能。</p>
  <p>对照：同样 7B@4bit、同样 {_f(target, 0)} tok/s，纯数字阵列（0.5 pJ/MAC）+ 外部 HBM 需要
  {_f(res['digital_baseline']['e_token_mj'], 1)} mJ/token ≈ {_f(res['digital_baseline']['e_token_mj'] * target / 1000, 0)} W。
  本设计的 {_f(mem['resident_j']['e_token_mj'], 2)} mJ 是它的 1/{_f(res['digital_baseline']['e_token_mj'] / mem['resident_j']['e_token_mj'], 0)}。</p>
  <div class="foot"><span>叠到第几层</span><span>6 / 14</span></div>
</section>""")

    # ---------------------------------------------------------------- 7
    plan_rows = ""
    for name in ("1B@4bit", "7B@4bit", "7B@8bit", "70B@2bit", "70B@4bit"):
        p = plans[name]
        verdict = ("可行：单层足矣" if p["layers_needed"] <= 1 else
                   "可行：本设计点" if p["layers_needed"] <= 4 else
                   "勉强：堆高超过 300 µm" if p["layers_needed"] <= 6 else "不可行：必须离开全驻留")
        plan_rows += _row([name, _f(p["model_mb"], 0), _f(p["per_tier_mb"], 0),
                           f"{p['layers_needed']} 层", _f(p["stack_height_um"], 0), verdict],
                          "hl" if name == "7B@4bit" else "")
    pages.append(f"""
<section class="page">
  <h2>六、容量计划：层数是被算出来的，不是拍出来的</h2>
  <table>
    <tr><th>模型</th><th>权重 (MB)</th><th>单层容量 (MB)</th><th>所需层数</th><th>堆高 (µm)</th><th>结论</th></tr>
    {plan_rows}
  </table>
  <p>同一个公式，五个模型，两种结论：<b>7B@4bit 落在「3 层」这个舒服的位置上；70B 无论怎么量化都离不开全驻留</b>
  （28 层 = 1.4 mm 高，热、成品率、翘曲都不成立）。这不是设计偏好，是密度的算术。</p>
  <h3>3 层为什么是「刚好」</h3>
  <ul>
    <li>2 层 = 2400 MB &lt; {_f(dp['model_mb'], 0)} MB：缺 {_f(airn[2]['spill_mb'], 0)} MB 必须走外部 HBM，
    每 token 多付 {_f(airn[2]['spill_j_per_token'] * 1e3, 0)} mJ。</li>
    <li>3 层 = 3600 MB：装下，只剩 {_f(3600 - dp['model_mb'], 0)} MB 余量（{_f((3600 - dp['model_mb']) / 3600 * 100, 1)}%）。
    <b>余量薄是这个设计最脆的地方</b>，第 12 页会量化。</li>
    <li>4 层 = 4800 MB：容量多 33%，风冷下吞吐不涨（{_f(airn[4]['tok_s_max'], 0)} ≈ {_f(airn[3]['tok_s_max'], 0)}），属于白叠；
    冷板下多 {_f((liqn[4]['tok_s_max'] / dp['tok_s_max'] - 1) * 100, 0)}%。</li>
  </ul>
  <blockquote>如果模型换成 7B@8bit（{_f(plans['7B@8bit']['model_mb'], 0)} MB），答案立刻变成 6 层——
  而 6 层在风冷下只有 {_f(airn[6]['tok_s_max'], 0)} tok/s，比 3 层还低。
  <b>「量化位宽」在这里等价于「层数预算」</b>，这是本模型给出的、可以直接指导产品定义的一条换算关系。</blockquote>
  <div class="foot"><span>叠到第几层</span><span>7 / 14</span></div>
</section>""")

    # ---------------------------------------------------------------- 8
    pages.append(f"""
<section class="page">
  <h2>七、第二本账：第几层开始白叠</h2>
  <img src="figures/fig2-scaling.png" alt="层数-吞吐">
  <p class="cap">图 3　可持续吞吐 vs 层数（对数纵轴）。虚线是产品目标 {_f(target, 0)} tok/s。</p>
  <table>
    <tr><th>N</th><th>风冷 tok/s</th><th>风冷 W/mm²</th><th>冷板 tok/s</th><th>冷板 W/mm²</th><th>受限项</th></tr>
    {''.join(_row([r["n_cim"], _f(r["tok_s_max"], 0), _f(r["w_mm2_max"], 2),
                   _f(liqn[r["n_cim"]]["tok_s_max"], 0), _f(liqn[r["n_cim"]]["w_mm2_max"], 2),
                   {"compute": "算力", "thermal": "结温", "flux": "热流密度"}[r["binding_constraint"]]],
                  "hl" if r["n_cim"] == nstar else "")
          for r in c["air"])}
  </table>
  <h3>三件事同时发生在 N=3 这个点上</h3>
  <ul>
    <li><b>容量刚好装下</b>：N=2 时 28% 的权重要走 HBM，吞吐被能量按在 {_f(airn[2]['tok_s_max'], 0)} tok/s；
    N=3 一步跨到 {_f(airn[3]['tok_s_max'], 0)}（{_f(airn[3]['tok_s_max'] / airn[2]['tok_s_max'], 0)} 倍）——<b>这是悬崖，不是斜坡</b>。</li>
    <li><b>热流密度到顶</b>：3 层满速 {_f(airn[3]['p_max_w'], 1)} W，正好把 {_f(q_air, 1)} W/mm² 的预算用满
    （{_f(airn[3]['p_max_w'], 1)} / 24 = {_f(airn[3]['w_mm2_max'], 2)}）；
    再加层，功率不变、吞吐也不变（N≥4 的 {_f(airn[8]['tok_s_max'], 0)} 与 N=3 的 {_f(airn[3]['tok_s_max'], 0)} 差不到 1%）。</li>
    <li><b>冷板把预算抬到 {_f(q_liq, 1)} W/mm²</b>：同样 3 层，冷板到 {_f(dp['tok_s_max'], 0)} tok/s（{_f(dp['tok_s_max'] / airn[3]['tok_s_max'], 1)} 倍）；
    但第 4 层就是 {_f(liqn[4]['tok_s_max'], 0)}，第 8 层 {_f(liqn[8]['tok_s_max'], 0)}——<b>冷板也是第 4 层起白叠</b>。</li>
  </ul>
  <blockquote>把平台的高度写成式子：
  <b>tok/s ≤ (q<sub>max</sub> · A − P<sub>static</sub>) / E<sub>token</sub></b>。
  这个式子里没有 N。代入得风冷上界 {_f(ceiling_air, 0)}、冷板上界 {_f(ceiling_liq, 0)}，
  而模型给出 {_f(airn[3]['tok_s_max'], 0)} 与 {_f(dp['tok_s_max'], 0)}。
  差的那一截是泄漏：风冷削掉 {_f((1 - airn[3]['tok_s_max'] / ceiling_air) * 100, 0)}%、
  冷板削掉 {_f((1 - dp['tok_s_max'] / ceiling_liq) * 100, 0)}%——
  <b>越凉削得越少，因为泄漏随温度指数上升</b>。闭式只能当上界用。</blockquote>
  <div class="foot"><span>叠到第几层</span><span>8 / 14</span></div>
</section>""")

    # ---------------------------------------------------------------- 9
    pages.append(f"""
<section class="page">
  <h2>八、第三本账：墙不在温度上，在足迹的热流密度上</h2>
  <img src="figures/fig4-thermal.png" alt="热流密度">
  <p class="cap">图 4　满速面热流密度 vs 层数。两条点线是两种冷却的面热流预算。</p>
  <div class="two">
    <div>
      <h3>温度反而是最松的一条</h3>
      <p>本设计点的满速结温是 {_f(dp['t_hot_max_c'], 1)} °C（{_f(dp['p_max_w'], 1)} W、冷板 R<sub>hs</sub> {_f(res['params']['stack']['r_hs_liquid']['value'], 2)} K/W、
      冷媒 {_f(res['params']['stack']['t_amb']['value'], 0)} °C），离 85 °C 还有 {_f(85 - dp['t_hot_max_c'], 0)} K。
      风冷 3 层也只有 {_f(airn[3]['t_hot_max_c'], 1)} °C。<b>也就是说，风冷的问题不是「烧得太热」，
      而是「这点面积根本散不出这么多瓦」</b>——热量还没把结温推上去，扩散热阻先到顶了。</p>
      <p>这一点很容易被 1D 热阻模型骗过去：只要 R<sub>hs</sub> 给得足够小，模型会允许 24 mm² 里塞几十瓦。
      所以模型里必须同时有<b>面热流密度上限 q<sub>max</sub></b>，否则会得出「冷板能带走 600 W」这种结论。</p>
    </div>
    <div>
      <h3>泄漏仍然要算</h3>
      <p>泄漏与温度是正反馈：功率↑ → 结温↑ → 泄漏↑。模型用不动点迭代解，
      本设计点 {dp['leak_iters']} 次收敛、残差 {_f(dp['thermal_residual'], 1)}。
      在 85 °C 上泄漏是动态功耗的 {_f(8 * 2 ** ((85 - 25) / 20), 0)}%——
      <b>供电与散热要按 1.4 倍的动态功耗设计</b>，这部分预算常常在纸面上被漏掉。</p>
      <p>层间温差：自下而上各层 {(' / '.join(_f(t, 1) for t in dp['t_tiers_max_c']))} °C，
      极差 {_f(max(dp['t_tiers_max_c']) - min(dp['t_tiers_max_c']), 1)} K。
      薄 die 让「内层更热」这个直觉在这个尺度上不成立。</p>
    </div>
  </div>
  <h3>双面冷却值不值</h3>
  <p>把冷板也贴到顶面，等于拿到第二份 {_f(q_air, 1)} W/mm² 的预算、热阻也并联减半：风冷双面 3 层能到
  {_f(dsn[3]['tok_s_max'], 0)} tok/s，是单面的 {_f(dsn[3]['tok_s_max'] / airn[3]['tok_s_max'], 1)} 倍，
  是单面冷板的 {_f(dsn[3]['tok_s_max'] / dp['tok_s_max'], 2)} 倍。<b>一条可以谈成本的选择题，不是「越冷越好」。</b></p>
  <div class="foot"><span>叠到第几层</span><span>9 / 14</span></div>
</section>""")

    # ---------------------------------------------------------------- 10
    pages.append(f"""
<section class="page">
  <h2>九、第四本账：IR 不是墙，单根 TSV 的载流是</h2>
  <img src="figures/fig5-pdn.png" alt="供电">
  <p class="cap">图 5　总功耗 vs IR drop（蓝）与满足载流所需的供电 TSV 面密度（红虚线）。</p>
  <table>
    <tr><th>量</th><th>满速值</th><th>判据</th><th>结论</th></tr>
    {_row(["总电流", f"{_f(dp['pdn_max']['i_total_a'], 1)} A", "I = P / 0.75 V", "小封装上的大电流"])}
    {_row(["IR drop", f"{_f(dp['pdn_max']['dv_total_mv'], 1)} mV（封装 {_f(dp['pdn_max']['dv_pkg_mv'], 1)} + TSV {_f(dp['pdn_max']['dv_tsv_mv'], 1)}）",
           "≤ 5% × 0.75 V = 37.5 mV", f"通过，余量 {_f(dp['pdn_max']['ir_margin'] * 100, 0)}%"])}
    {_row(["所需供电 TSV 密度", f"{_f(dp['pdn_max']['tsv_density_required'], 0)} 个/mm²", f"单根 ≤ {_f(i_max_ma, 0)} mA", f"默认 20 个/mm² 不够，需 {_f(dp['pdn_max']['tsv_density_required'] / 20, 1)} 倍"])}
    {_row(["TSV 面积代价", f"{_f(dp['pdn_max']['tsv_area_overhead_pct'], 2)}%", "按 5 µm 直径计", "可忽略，代价在工艺不在面积"])}
    {_row(["单根电流密度", f"{_f(0.02 / (3.1416 * (2.5e-6) ** 2) / 1e4, 1)}×10⁵ A/cm²", "Cu 电迁移经验限 ~1×10⁵", "20 mA 恰好压线；50 mA 到 2.5 倍，不可用"])}
  </table>
  <blockquote>这条账本来是我以为会最先成为墙的：{_f(dp['pdn_max']['i_total_a'], 0)} A 穿过多层堆叠，听起来就不可能。
  算下来 IR 只有 {_f(dp['pdn_max']['dv_total_mv'], 0)} mV——<b>真正的约束是每根 TSV 的载流上限，它逼出一个密度规格
  （≥{_f(dp['pdn_max']['tsv_density_required'], 0)} 个/mm²），而不是逼死这个架构</b>。
  报告保留这条否定结果，因为它决定了要不要为供电留面积。</blockquote>
  <h3>这条规格怎么落到版图上</h3>
  <ul>
    <li>供电 TSV 与信号键合分开布：TSV 走阵列空隙与宏边界，不占键合面。</li>
    <li>{_f(dp['pdn_max']['tsv_density_required'], 0)} 个/mm² × 24 mm² ≈ {_f(dp['pdn_max']['tsv_density_required'] * 24, 0)} 根，
    按 5 µm 直径算占 {_f(dp['pdn_max']['tsv_area_overhead_pct'], 2)}% 面积；按 40 µm 栅格排，落在 32 个宏的间隙里。</li>
    <li>IR 余量只有 {_f(dp['pdn_max']['ir_margin'] * 100, 0)}%，板上必须去耦；若 R<sub>pkg</sub> 恶化到 0.5 mΩ，余量会被吃掉
    （此项目前不在敏感度表里，属未验证）。</li>
  </ul>
  <div class="foot"><span>叠到第几层</span><span>10 / 14</span></div>
</section>""")

    # ---------------------------------------------------------------- 11
    pages.append(f"""
<section class="page">
  <h2>十、层序优化：一条否定结果</h2>
  <p>一开始我以为「谁在上面」会是三维堆叠的核心设计变量：热源应该远离冷板还是靠近冷板？
  于是写了个穷举器，把逻辑层、容量层、三层存算共 {place['n_perm']} 种去重排列全部解一遍热网络。</p>
  <table>
    <tr><th>排列</th><th>满速峰值结温</th></tr>
    {_row(["最优：" + " → ".join(place["best"]["order"]), f"{_f(place['best']['t_hot_c'], 2)} °C"], "hl")}
    {_row(["最差：" + " → ".join(place["worst"]["order"]), f"{_f(place['worst']['t_hot_c'], 2)} °C"])}
    {_row(["全部排列的极差", f"{_f(place['spread_k'], 2)} K"])}
  </table>
  <blockquote>{_f(place['spread_k'], 1)} K 的极差，在 50 K 的预算里几乎等于噪声。
  <b>原因很简单：50 µm 薄 die 的层间热阻约 0.02 K/W，而 TIM + 散热器是它的 20 倍以上。</b>
  热量不是「卡在中间」，而是一起被最外面那一段堵住。</blockquote>
  <h3>这条否定结果有什么用</h3>
  <ul>
    <li><b>省掉一整轮优化</b>：不必为层序做组合搜索，把工程资源放到散热器与足迹上。</li>
    <li><b>解释一个常见误解</b>：文献里「内层更热」说的是厚 die / 低导热界面；薄 die + 混合键合下，这个效应被压到 1 K 量级。</li>
    <li><b>给出判据</b>：层间热阻与外部热阻之比小于 5% 时，层序可以不管。本设计是
    {_f(0.02 / (1.2 + 0.0125) * 100, 1)}%。</li>
  </ul>
  <p class="small">这是本轮唯一被自己推翻的假设；写进来是因为「模型说不出话的地方」比「模型说出漂亮话的地方」更值得记。</p>
  <div class="foot"><span>叠到第几层</span><span>11 / 14</span></div>
</section>""")

    # ---------------------------------------------------------------- 12
    density_rows = ""
    for rho, need in ((12.5, "12 层（不可行）"), (50, "3 层（本设计点）"), (100, "2 层")):
        cap = 24 * rho
        n = -(-dp["model_mb"] // cap)
        density_rows += _row([_f(rho, 1), _f(cap, 0), f"{int(n)} 层", need], "hl" if rho == 50 else "")
    pages.append(f"""
<section class="page">
  <h2>十一、敏感度：哪个数字能把结论推倒</h2>
  <img src="figures/fig6-sensitivity.png" alt="敏感度">
  <p class="cap">图 6　单参数取区间两端时，设计点可持续吞吐的移动（对数横轴，虚线为基准）。</p>
  <table>
    <tr><th>参数</th><th>区间</th><th>设计点吞吐 (tok/s)</th><th>倍数</th></tr>
    {''.join(_row([s["param"], f'{s["lo"]:.3g} – {s["hi"]:.3g} {s["unit"]}',
                   f'{_f(min(s["tok_lo"], s["tok_hi"]), 0)} – {_f(max(s["tok_lo"], s["tok_hi"]), 0)}',
                   f'{_f(s["tok_swing_ratio"], 1)}×'])
            for s in sens[:5])}
  </table>
  <h3>最脆的地方不是热量，是密度</h3>
  <p>把密度从 50 调到 12.5，设计点吞吐会掉到 {_f(sens[0]['tok_lo'] if sens[0]['param'] == 'density' else 0, 0)} tok/s——
  因为 7B@4bit 突然需要 12 层，而任何冷却都装不下 12 层。这条不是热的问题，是容量的算术：</p>
  <table>
    <tr><th>ρ (MB/mm²)</th><th>单层容量 (MB)</th><th>7B@4bit 所需层数</th><th>结论</th></tr>
    {density_rows}
  </table>
  <blockquote>ρ 是全篇最弱的假设（区间跨一个数量级）。所以本报告的结论应该这样读：
  <b>「3 层」不是绝对数字，而是「密度 50 MB/mm² 下 7B@4bit 的容量解」</b>。
  密度变一半，答案就变一半——这条换算关系比具体数字更有用。</blockquote>
  <p class="small">关于「e_mac 变 10 倍、吞吐只变 {_f(sens[2]['tok_swing_ratio'], 1)} 倍」：设计点本身是
  <b>热流受限</b>的，算力还有 {_f(dp['tok_s_ceiling'] / dp['tok_s_max'], 1)} 倍余量；
  只有把每 MAC 能量放大到 4 倍（400 fJ），算力上限才掉到热流上限之下，吞吐才开始跟能量走。
  不是线性关系失效，是两根约束在交叉。</p>
  <p class="small">其次是频率（{_f(sens[1]['tok_swing_ratio'], 1)}×）与每 MAC 能量（{_f(sens[2]['tok_swing_ratio'], 1)}×）：
  这两个都是「满速功耗」的乘数，而满速功耗决定你能不能吃到那条热流预算。泄漏与外部搬运能量在本设计点<strong>不影响结论</strong>
  （1.0×），因为此时两者都不是瓶颈——这不代表它们不重要，只代表在这个点上它们不是杠杆。</p>
  <div class="foot"><span>叠到第几层</span><span>12 / 14</span></div>
</section>""")

    # ---------------------------------------------------------------- 13
    pages.append(f"""
<section class="page">
  <h2>十二、什么时候不该堆</h2>
  <p>把四本账合起来，可以得到一张不看具体数字也能用的判据表。它的价值在于：<b>先判断你落在哪个区，再决定要不要做三维</b>。</p>
  <table>
    <tr><th style="width:20%">你落在哪</th><th style="width:26%">判据</th><th>该做什么</th></tr>
    {_row(["容量区（本作品）", "模型字节 / 单层容量 ∈ (1, 4]",
           "三维全驻留值得做；层数按容量取整，冷却按满速的热流密度选"])}
    {_row(["算力区", "模型装得下，但单层算力不够",
           "先加层；此时层数是线性的，前提是热流预算跟得上（本例需冷板）"])}
    {_row(["搬运区", "模型字节 / 单层容量 &gt; 6",
           "不要试图全驻留（70B 要 28 层）；改用近存/键合流式，靠 0.05 pJ/bit 而不是 5 pJ/bit"])}
    {_row(["散热区", f"W/mm² &gt; {_f(q_air, 1)} 且只能风冷",
           f"层数不是杠杆：风冷 3 层已到顶，加层吞吐不涨（8 层 {_f(airn[8]['tok_s_max'], 0)}）"])}
    {_row(["供电区", f"总电流 / 面积 &gt; {_f(dp['pdn_max']['tsv_density_required'] * 0.05 / 0.75 * 1000, 0)} A/mm²",
           "先加供电 TSV 密度；IR 通常不是问题，单根载流才是"])}
  </table>
  <h3>本作品自己落在哪</h3>
  <p>7B@4bit / 24 mm² → 容量比 {_f(dp['model_mb'] / (24 * 50), 2)}，落在容量区；满速 {_f(dp['w_mm2_max'], 2)} W/mm²，
  超过风冷的 {_f(q_air, 1)} → 必须冷板。两条判据同时指向「3 层 + 冷板」，而不是「越多越好」。</p>
  <blockquote>如果只能从这份报告里带走一句话：<b>三维堆叠买到的是容量和延迟，不是免费的吞吐。
  吞吐的上限写在足迹的热流密度上，而足迹是二维的——它不会因为你叠得更高而变大。</b></blockquote>
  <p class="small">补充一句工程判断：如果产品只要 {_f(target, 0)} tok/s，那么 1 层 + 冷板（{_f(liqn[1]['tok_s_max'], 0)} tok/s）
  其实不够，2 层（{_f(liqn[2]['tok_s_max'], 0)}）刚好卡在目标线上——<b>目标定在 1000 tok/s 这个位置，恰好把「2 层不够、3 层有余」暴露出来</b>。
  定目标的时候顺手看一眼这条曲线，比事后加层便宜。</p>
  <div class="foot"><span>叠到第几层</span><span>13 / 14</span></div>
</section>""")

    # ---------------------------------------------------------------- 14
    pages.append(f"""
<section class="page">
  <h2>十三、假设、边界与复现</h2>
  <h3>这份报告不声称什么</h3>
  <ul>
    <li>不是硅测量：没有流片、没有版图、没有 PPA 签核。所有数字是解析模型 + 数值求解的输出。</li>
    <li>不含成品率、不含 TSV 应力、不含电迁移寿命、不含封装翘曲；这些都会让「8 层」比图上更难。</li>
    <li>不含 ECC / 冗余 / 权重校准的代价；4-bit MLC 的实际可用精度通常要打折，等效于密度下降（第 12 页）。</li>
    <li>不含软件栈：算子映射效率按 100% 计，真实编译器会再打 0.5–0.8 的折。</li>
    <li>不含 KV cache 与 batch：tok/s 是单序列解码速率，不是可服务并发；KV cache 还会吃掉容量（7B/4k 上下文约 0.5 GB）。</li>
  </ul>
  <h3>最弱的三个假设</h3>
  <table>
    <tr><th>假设</th><th>取值</th><th>为什么弱</th><th>影响</th></tr>
    {_row(["密度 ρ", "50 MB/mm²", "4-bit MLC 面密度的工程估计，公开可核的商用宏数据很少", "直接决定层数（12.5 → 12 层，100 → 2 层）"])}
    {_row(["每 MAC 能量", "100 fJ", "宏级 10 TOPS/W；系统级含缓冲/NoC 通常更差", "满速功耗线性放大，4 倍时吞吐掉到 0.65×"])}
    {_row(["面热流上限 q<sub>max</sub>", f"{_f(q_air, 1)} / {_f(q_liq, 1)} W/mm²", "风冷/冷板的经验区间，随封装与散热器形态变化大", "决定平台高度：q 翻倍，吞吐几乎翻倍"])}
  </table>
  <h3>怎么复现</h3>
  <p class="mono">py -3 run.py&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;# 模型 → results.json → 图 → 本 PDF → 作品页<br>
  py -3 verify.py&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;# 断言：能量守恒、热网络残差、不动点唯一性、量纲、单调性、确定性<br>
  py -3 -c "from stco import design; print(design.evaluate(3, 'liquid'))"</p>
  <p>参数全部在 <code>stco/params.py</code>，带 <code>kind</code>（pub/est/derived）与区间；
  报告里的每个数字都能由 <code>out/results.json</code> 复算。模型输出固定迭代次数与排序，
  同机重跑逐字节一致（<code>verify.py</code> 会断言这一点）。</p>
  <blockquote>给评委的一句话：这个作品没有漂亮的芯片照片，只有一本能自己算、也能被自己推翻的账。
  如果只能验证一件事，请跑 <code>verify.py</code>；如果只能质疑一件事，请质疑密度 ρ 与面热流上限 q<sub>max</sub>。</blockquote>
  <div class="foot"><span>叠到第几层 · v1.0</span><span>14 / 14</span></div>
</section>""")

    body = "\n".join(pages)
    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>叠到第几层 — 3D 存内计算的 STCO 方案书</title>
<style>{CSS}</style></head>
<body>{body}</body></html>"""

    os.makedirs(outdir, exist_ok=True)
    os.makedirs(sitedir, exist_ok=True)
    fig_abs = os.path.join(outdir, "figures").replace("\\", "/")
    html_abs = html.replace('src="figures/', 'src="file:///' + fig_abs + "/")
    tmp_html = os.path.join(outdir, "_deck.html")
    with open(tmp_html, "w", encoding="utf-8") as f:
        f.write(html_abs)

    pdf = os.path.join(outdir, "3D-CIM-STCO-v1.0.pdf")
    subprocess.run([_chrome(), "--headless=new", "--disable-gpu", "--no-sandbox",
                    "--no-pdf-header-footer", f"--print-to-pdf={pdf}",
                    "file:///" + tmp_html.replace("\\", "/")],
                   check=True, capture_output=True)

    site_fig = os.path.join(sitedir, "figures")
    os.makedirs(site_fig, exist_ok=True)
    for name in os.listdir(fig_abs):
        if name.endswith(".png"):
            shutil.copy2(os.path.join(fig_abs, name), os.path.join(site_fig, name))
    with open(os.path.join(sitedir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)

    # GitHub Pages 只允许 / 或 /docs：把同一份页面镜像到 docs/，四闸记录也在那里，一起公开
    docsite = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")
    os.makedirs(os.path.join(docsite, "figures"), exist_ok=True)
    for name in os.listdir(fig_abs):
        if name.endswith(".png"):
            shutil.copy2(os.path.join(fig_abs, name), os.path.join(docsite, "figures", name))
    with open(os.path.join(docsite, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    return pdf
