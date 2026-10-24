"""第二轮审计：专门找"结果可能不成立"的地方。

上一轮 audit_run.py 查的是"东西是不是真的"；这一轮查的是
"这个结论站不站得住"——统计口径、混杂因素、重复计算。

跑法：.venv\\Scripts\\python.exe tools\\audit_deep.py
"""
import gzip
import json
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as C

import numpy as np


def read_jsonl(p):
    with open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def load_pred(eid, task):
    p = C.PREDS / f"{eid}_{task}.csv.gz"
    if not p.exists():
        return None
    import csv
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def mcnemar_exact(b, c):
    """two-sided exact binomial test on discordant pairs"""
    from math import comb
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


train = read_jsonl(C.PROC / "train.jsonl")
medmcqa = read_jsonl(C.PROC / "medmcqa.jsonl")
medqa = read_jsonl(C.PROC / "medqa.jsonl")

print("=" * 72)
print("A. 考题答案分布（如果严重偏斜，'全选A'就是强基线）")
print("=" * 72)
for name, rows in [("medmcqa", medmcqa), ("medqa", medqa)]:
    c = Counter(int(r["answer"]) for r in rows)
    tot = sum(c.values())
    dist = "  ".join(f"{'ABCD'[k]}={c.get(k,0)} ({c.get(k,0)/tot:.1%})" for k in range(4))
    maj = max(c.values()) / tot
    print(f"  {name:8s} n={tot:5d}  {dist}   多数类={maj:.1%}")
print("  → 多数类越接近 25% 越好；若某个任务 40% 都是 B，基线就有偏。")

print()
print("=" * 72)
print("B. 种子之间到底差多少（3 seeds 的 30% 档）")
print("=" * 72)
for task in ["medmcqa", "medqa"]:
    print(f"  {task}:")
    for m in ["full", "nait", "random"]:
        accs = []
        for s in [1, 2, 3]:
            eid = f"full_s{s}" if m == "full" else f"{m}_r30_s{s}"
            pr = load_pred(eid, task)
            if pr:
                accs.append(sum(int(x["correct"]) for x in pr) / len(pr))
        if accs:
            print(f"    {m:7s} " + "  ".join(f"s{s+1}={a:.4f}" for s, a in enumerate(accs))
                  + f"   极差={max(accs)-min(accs)*1:.4f}" if len(accs) > 1 else "")

print()
print("=" * 72)
print("C. 统计口径问题：跨种子合并 McNemar 会不会虚高显著性？")
print("=" * 72)
print("  做法对比：把 3 个种子当独立样本合并（=现在 R 的做法）vs 每个种子单独算")
for task in ["medmcqa", "medqa"]:
    pooled_b = pooled_c = 0
    per_seed = []
    for s in [1, 2, 3]:
        f = load_pred(f"full_s{s}", task)
        n = load_pred(f"nait_r30_s{s}", task)
        if not (f and n):
            continue
        b = sum(1 for x, y in zip(f, n) if int(x["correct"]) == 1 and int(y["correct"]) == 0)
        c = sum(1 for x, y in zip(f, n) if int(x["correct"]) == 0 and int(y["correct"]) == 1)
        pooled_b += b
        pooled_c += c
        per_seed.append((s, b, c, mcnemar_exact(b, c)))
    if per_seed:
        print(f"  {task}:")
        for s, b, c, p in per_seed:
            print(f"     seed {s}: 只全量对 {b:4d} / 只子集对 {c:4d}  p={p:.3f}")
        print(f"     合并   : {pooled_b:4d} / {pooled_c:4d}  p={mcnemar_exact(pooled_b, pooled_c):.4f}"
              f"   ← 合并把同一批题数了 3 遍，p 会偏小")

print()
print("=" * 72)
print("D. 混杂检查：激活得分是不是只是在挑'长文本'？")
print("=" * 72)
stats_path = C.RESULTS / "sample_stats.csv"
if stats_path.exists():
    import csv
    with open(stats_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    score = np.array([float(r["act_score"]) for r in rows])
    length = np.array([len(r["id"]) for r in rows])  # id 长度无关，改用下面的文本长度
    # 用训练文本真实长度重算
    id2len = {r["id"]: len(r["instruction"]) for r in train}
    L = np.array([id2len.get(r["id"], 0) for r in rows])
    if L.std() > 0:
        rho = np.corrcoef(score, L)[0, 1]
        print(f"  act_score 与 instruction 字符数相关：r = {rho:+.3f}")
        print(f"  长度分布：p10={np.percentile(L,10):.0f}  p50={np.percentile(L,50):.0f}  p90={np.percentile(L,90):.0f}")
    sel = np.array([r["nait_30"] == "1" for r in rows])
    print(f"  被选中样本的平均长度 {L[sel].mean():7.1f} 字符；未选中 {L[~sel].mean():7.1f} 字符")
    print(f"  → 若两者差 <5%，长度不是混杂因素；若差很多，'激活选择'实际在挑长短")
else:
    print(f"  缺失 {stats_path}")

print()
print("=" * 72)
print("E. 更严格的重题检查（上一轮把题干截到 200 字符，可能漏）")
print("=" * 72)


def norm(s):
    return "".join(ch for ch in s.lower() if ch.isalnum())


tr = {norm(x["instruction"]) for x in train}
for name, rows in [("medmcqa", medmcqa), ("medqa", medqa)]:
    ov = sum(norm(r["question"]) in tr for r in rows)
    dup_in_eval = len(rows) - len({norm(r["question"]) for r in rows})
    print(f"  {name}: 与训练集重题 {ov}/{len(rows)}；评测集内部重复题干 {dup_in_eval}")

print()
print("=" * 72)
print("F. 评测集科室分布 vs 训练池科室分布")
print("=" * 72)
tr_dept = Counter(x["dept"] for x in train)
ev_dept = Counter(x["dept"] for x in medmcqa)
for d in sorted(tr_dept, key=lambda k: -tr_dept[k]):
    print(f"  {d:8s} 训练 {tr_dept[d]/len(train):6.1%}   评测 {ev_dept.get(d,0)/len(medmcqa):6.1%}")
print("  → 若评测集某科室占比远高于训练池，那里的掉点可能来自'训得少'而非'选得差'")
