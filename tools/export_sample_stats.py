"""export_sample_stats.py - 导出"每样本一行"的激活统计表（提案 02③ 要求的字段）。

提案原文：关键字段 = 样本激活统计 / 被选子集 / 训练数据量 / 下游任务表现 / 训练算力。
本脚本产出第一项：每条训练样本的激活得分、全池名次、以及是否被某个子集选中。

用法：
    .venv\\Scripts\\python.exe tools\\export_sample_stats.py
输出：
    results/sample_stats.csv
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import config as C  # noqa: E402
import select_subset as S  # noqa: E402


def main() -> None:
    ids, tr = S.load_acts("train")
    _, pr = S.load_acts("probe")
    ids = list(ids)[: C.N_POOL]
    tr = tr[: C.N_POOL]

    scores, _ = S.nait_scores(tr, pr)          # 与 select_subset.py 完全同一条路径
    scores = np.asarray(scores).ravel()
    n = len(ids)

    order = np.argsort(-scores)
    rank = np.empty(n, dtype=int)
    rank[order] = np.arange(1, n + 1)

    # 科室标签
    dept_of = {}
    with open(os.path.join(C.PROC, "train.jsonl"), encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            dept_of[r["id"]] = r["dept"]

    # 子集名单
    with open(os.path.join(C.SUBSETS, "subsets.json"), encoding="utf-8") as f:
        subs = json.load(f)

    cols, id_sets = [], {}
    for method in ("nait", "nait_dedup"):
        if method not in subs:
            continue
        for pct in ("10", "20", "30", "50", "70"):
            key = f"{method}_{pct}"
            blk = subs[method].get(pct, {})
            id_sets[key] = set(blk.get("ids", []) if isinstance(blk, dict) else blk)
            cols.append(key)

    out = os.path.join(C.RESULTS, "sample_stats.csv")
    with open(out, "w", encoding="utf-8", newline="") as f:
        f.write(",".join(["id", "dept", "act_score", "act_rank", "pct_rank"] + cols) + "\n")
        for i, sid in enumerate(ids):
            line = [
                sid, dept_of.get(sid, "other"), f"{float(scores[i]):.6f}",
                str(int(rank[i])), f"{100.0 * rank[i] / n:.2f}",
            ]
            line += ["1" if sid in id_sets[k] else "0" for k in cols]
            f.write(",".join(line) + "\n")

    print(f"wrote {out}")
    print(f"rows={n}  columns={5 + len(cols)}")
    print("cols:", ",".join(["id", "dept", "act_score", "act_rank", "pct_rank"] + cols))
    if "nait_30" in id_sets:
        print("sanity: nait_30 selected =", sum(1 for s in ids if s in id_sets["nait_30"]))
    print("sanity: score p50={:.4f}  p99={:.4f}".format(
        float(np.percentile(scores, 50)), float(np.percentile(scores, 99))))


if __name__ == "__main__":
    main()
