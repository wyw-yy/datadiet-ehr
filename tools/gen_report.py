"""gen_report.py —— 汇总生成式评测：谁"写得对"，谁只是"选得对"。

读 results/gen/<tag>_<task>.csv，输出：
  results/gen/summary.csv        每个 arm 一行（准确率、格式、长度、红旗）
  results/gen/paired.csv         两两配对（McNemar 精确检验）
终端打印成表。

用法：
    .venv\\Scripts\\python.exe tools\\gen_report.py
    .venv\\Scripts\\python.exe tools\\gen_report.py --task medqa
"""

import argparse
import csv
import glob
import json
import math
import os
from collections import Counter

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # 让 tools/ 下的脚本也能 import 根目录的 config
import config as C


def binom_two_sided(b, c):
    """精确 McNemar：在 b+c 个"不一致对"里，b 服从 Binomial(b+c, 0.5)。"""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def read_csv(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", default="medmcqa")
    ap.add_argument("--gen-dir", default=os.path.join(C.RESULTS, "gen"))
    args = ap.parse_args()

    paths = sorted(glob.glob(os.path.join(args.gen_dir, f"*_{args.task}.csv")))
    if not paths:
        raise SystemExit(f"没找到 {args.gen_dir}/*_{args.task}.csv")

    per_arm = {}
    for p in paths:
        tag = os.path.basename(p)[: -len(f"_{args.task}.csv")]
        rows = read_csv(p)
        n = len(rows)
        acc = sum(int(r["correct"]) for r in rows) / n
        fmt = sum(int(r["format_ok"]) for r in rows) / n
        parsed = sum(1 for r in rows if r["pred"]) / n
        toks = sorted(int(r["n_tokens"]) for r in rows)
        flags = Counter()
        for r in rows:
            for f in filter(None, r["flags"].split(";")):
                flags[f] += 1
        per_arm[tag] = dict(rows=rows, n=n, acc=acc, fmt=fmt, parsed=parsed,
                            p50=toks[n // 2], mean_tok=sum(toks) / n, flags=flags)

    order = [t for t in ["base", "full_s1", "nait_r30_s1", "random_r30_s1",
                         "rand_len_r30_s1", "el2n_r30_s1"] if t in per_arm]
    order += [t for t in per_arm if t not in order]

    print(f"\n生成式评测（{args.task}，{per_arm[order[0]]['n']} 题，贪心解码）\n")
    head = f"{'arm':<18}{'acc':>7}{'格式合规':>10}{'能抽出':>8}{'中位token':>10}{'红旗':>6}"
    print(head)
    print("-" * len(head))
    for t in order:
        a = per_arm[t]
        print(f"{t:<18}{a['acc'] * 100:>6.1f}%{a['fmt'] * 100:>9.1f}%"
              f"{a['parsed'] * 100:>7.1f}%{a['p50']:>10}{sum(a['flags'].values()):>6}")

    # 配对对比：同一批题上，谁的答案不一样
    pairs = [("full_s1", "nait_r30_s1"), ("full_s1", "random_r30_s1"),
             ("nait_r30_s1", "random_r30_s1"), ("base", "full_s1"),
             ("nait_r30_s1", "rand_len_r30_s1")]
    print("\n配对比较（同一批题，只有两臂答案不同的题才有信息）\n")
    head2 = f"{'A vs B':<34}{'A-B':>8}{'A对B错':>8}{'B对A错':>8}{'p':>9}"
    print(head2)
    print("-" * len(head2))
    out_pairs = []
    for a_tag, b_tag in pairs:
        if a_tag not in per_arm or b_tag not in per_arm:
            continue
        ra = {r["item_id"]: int(r["correct"]) for r in per_arm[a_tag]["rows"]}
        rb = {r["item_id"]: int(r["correct"]) for r in per_arm[b_tag]["rows"]}
        ids = sorted(set(ra) & set(rb))
        b = sum(1 for i in ids if ra[i] == 1 and rb[i] == 0)
        c = sum(1 for i in ids if ra[i] == 0 and rb[i] == 1)
        diff = (b - c) / len(ids) * 100
        p = binom_two_sided(b, c)
        print(f"{a_tag + ' - ' + b_tag:<34}{diff:>+7.1f}{b:>8}{c:>8}{p:>9.4f}")
        out_pairs.append(dict(a=a_tag, b=b_tag, n=len(ids), diff_pp=round(diff, 2),
                              a_only=b, b_only=c, p=round(p, 4)))

    os.makedirs(args.gen_dir, exist_ok=True)
    with open(os.path.join(args.gen_dir, "summary.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["arm", "task", "n", "acc", "format_ok", "parse_rate",
                    "p50_tokens", "mean_tokens", "n_flagged"])
        for t in order:
            a = per_arm[t]
            w.writerow([t, args.task, a["n"], round(a["acc"], 4), round(a["fmt"], 4),
                        round(a["parsed"], 4), a["p50"], round(a["mean_tok"], 1),
                        sum(a["flags"].values())])
    with open(os.path.join(args.gen_dir, "paired.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out_pairs[0].keys()))
        w.writeheader()
        w.writerows(out_pairs)
    print(f"\n写出 {os.path.join(args.gen_dir, 'summary.csv')}")
    print(f"写出 {os.path.join(args.gen_dir, 'paired.csv')}")

    # 红旗逐条列出（有的话），方便人工过一遍
    for t in order:
        if per_arm[t]["flags"]:
            print(f"\n{t} 的危险表述：")
            for why, k in per_arm[t]["flags"].items():
                print(f"  {why}: {k} 条")


if __name__ == "__main__":
    main()
