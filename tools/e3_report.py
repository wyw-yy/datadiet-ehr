"""e3_report.py —— 3-epoch 那一轮的对比表（读 preds，配对检验）。

只回答一个问题：**把训练拉长到 3 个 epoch 之后，nait 与 random 的差距会出现吗？**

输出：
  results/e3_summary.csv    每个 arm x 任务的准确率、相对 full_s1_e3 的掉点与 CI
  results/e3_paired.csv     nait vs random 的逐题配对检验
终端打印成表。
"""

import argparse
import csv
import glob
import gzip
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as C

TAG = "e3"


def mcnemar_p(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def boot_ci(x, B=2000, alpha=0.05, seed=7):
    import random
    rnd = random.Random(seed)
    n = len(x)
    means = []
    for _ in range(B):
        means.append(sum(x[rnd.randrange(n)] for _ in range(n)) / n)
    means.sort()
    return means[int(alpha / 2 * B)], means[int((1 - alpha / 2) * B) - 1]


def load_preds(task):
    """{(exp_id, task): {item_id: correct}}"""
    out = {}
    for p in glob.glob(os.path.join(C.PREDS, f"*_{task}.csv.gz")):
        eid = os.path.basename(p)[: -len(f"_{task}.csv.gz")]
        if not eid.endswith(f"_{TAG}"):
            continue
        with gzip.open(p, "rt", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        out[eid] = {r["item_id"]: int(r["correct"]) for r in rows}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="额外写一份 json 摘要")
    args = ap.parse_args()

    tasks = ["medqa", "medmcqa"]
    all_rows, paired_rows = [], []

    for task in tasks:
        preds = load_preds(task)
        if not preds:
            print(f"[{task}] 还没有 3-epoch 的 preds")
            continue
        base = preds.get(f"full_s1_{TAG}")
        if base is None:
            print(f"[{task}] 缺 full_s1_{TAG}，无法算掉点")
            continue

        print(f"\n=== {task}（对照 full_s1_{TAG}，n={len(base)} 题）===")
        print(f"{'arm':<22}{'acc':>8}{'Δ vs full':>12}{'95% CI':>20}{'p':>9}")
        arms = sorted(preds)
        for eid in arms:
            d = preds[eid]
            ids = sorted(set(base) & set(d))
            acc = sum(d[i] for i in ids) / len(ids)
            base_acc = sum(base[i] for i in ids) / len(ids)
            diff = [d[i] - base[i] for i in ids]
            lo, hi = boot_ci(diff)
            b = sum(1 for i in ids if d[i] == 1 and base[i] == 0)
            c = sum(1 for i in ids if d[i] == 0 and base[i] == 1)
            p = mcnemar_p(b, c)
            print(f"{eid:<22}{acc * 100:>7.2f}%{(acc - base_acc) * 100:>+11.2f}"
                  f"{f'[{lo * 100:+.2f}, {hi * 100:+.2f}]':>20}{p:>9.3f}")
            all_rows.append(dict(task=task, arm=eid, n=len(ids), acc=round(acc, 4),
                                 delta_pp=round((acc - base_acc) * 100, 2),
                                 ci_lo_pp=round(lo * 100, 2), ci_hi_pp=round(hi * 100, 2),
                                 p=round(p, 4)))

        # 关键对照：nait vs random（同种子配对）
        for s in (1, 2, 3):
            a = preds.get(f"nait_r30_s{s}_{TAG}")
            b_ = preds.get(f"random_r30_s{s}_{TAG}")
            if not a or not b_:
                continue
            ids = sorted(set(a) & set(b_))
            b = sum(1 for i in ids if a[i] == 1 and b_[i] == 0)
            c = sum(1 for i in ids if a[i] == 0 and b_[i] == 1)
            d = (b - c) / len(ids) * 100
            p = mcnemar_p(b, c)
            print(f"  seed{s}: nait − random = {d:+.2f} pp  (仅A对 {b} / 仅B对 {c})  p={p:.3f}")
            paired_rows.append(dict(task=task, seed=s, n=len(ids), diff_pp=round(d, 2),
                                    a_only=b, b_only=c, p=round(p, 4)))

    if all_rows:
        with open(os.path.join(C.RESULTS, "e3_summary.csv"), "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
            w.writeheader()
            w.writerows(all_rows)
        print(f"\n写出 {os.path.join(C.RESULTS, 'e3_summary.csv')}")
    if paired_rows:
        with open(os.path.join(C.RESULTS, "e3_paired.csv"), "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(paired_rows[0].keys()))
            w.writeheader()
            w.writerows(paired_rows)
        print(f"写出 {os.path.join(C.RESULTS, 'e3_paired.csv')}")


if __name__ == "__main__":
    main()
