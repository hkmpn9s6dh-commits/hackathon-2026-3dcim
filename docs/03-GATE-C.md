# 闸 C：全新 clone 从零复现

## 判据

把仓库 clone 到干净目录，只照 README 的两条命令跑，要求：

1. `py -3 run.py` 退出码 0，产出 `out/results.json`、六张图、14 页 PDF、`site/index.html`；
2. `out/results.json` 与主目录 **sha256 逐字节一致**（模型无随机性、JSON 排序固定）；
3. `py -3 verify.py` → PASS 190 / 190、EXIT=0。

## 结果

见 `docs/05-LESSONS.md` 末尾记录（命令与耗时）。**未通过项如实写在票面**，不在这里美化。
