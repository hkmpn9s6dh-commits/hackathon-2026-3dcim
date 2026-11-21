"""一条命令跑完整条链：模型 → results.json → 图 → 方案书 PDF → 作品页。

    py -3 run.py                # 全链
    py -3 run.py --only model   # 只出 results.json
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from stco import explore, figures, deck  # noqa: E402


def write_results(path):
    res = explore.build_results()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["model", "figures", "deck"], default=None)
    ap.add_argument("--out", default=os.path.join(HERE, "out"))
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    res_path = os.path.join(args.out, "results.json")

    if args.only in (None, "model"):
        res = write_results(res_path)
        print(f"[model] {res_path}  N*={res['n_star']['n']}  "
              f"tok/s={res['design_point']['tok_s_max']:.0f}")
    if args.only in (None, "figures"):
        paths = figures.build_all(res_path, os.path.join(args.out, "figures"))
        print("[figures]", *paths.values(), sep="\n  ")
    if args.only in (None, "deck"):
        with open(res_path, encoding="utf-8") as f:
            res = json.load(f)
        pdf = deck.build(res, args.out, os.path.join(HERE, "site"))
        print(f"[deck] {pdf}")


if __name__ == "__main__":
    main()
