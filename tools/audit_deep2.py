"""第三遍审计：统计口径 + 陈旧产物 + 关键对比（nait vs random）。"""
import csv
import gzip
import json
import sys
from collections import Counter
from math import comb
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
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def mcnemar_exact(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)


train = read_jsonl(C.PROC / "train.jsonl")
by_id = {r["id"]: r for r in train}

print("=" * 72)
print("G. 陈旧产物检查：results/ 里哪些文件不是这批数据生成的")
print("=" * 72)
sp = C.RESULTS / "sample_stats.csv"
if sp.exists():
    with open(sp, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    ids = {r["id"] for r in rows}
    inter = len(ids & set(by_id))
    verdict = "✅ 对得上" if inter == len(ids) else f"❌ 只有 {inter}/{len(ids)} 条在当前训练池里 → 这是旧池子的产物"
    print(f"  sample_stats.csv  {len(rows)} 行  {verdict}")
    print(f"     样例 id: {list(ids)[:3]}")

print()
print("=" * 72)
print("H. 关键对比：nait vs random（论文真正要主张的那一条）")
print("=" * 72)
print("  每个种子单独检验，再看方向是否一致；跨种子不能合并计数。")
for task in ["medmcqa", "medqa"]:
    print(f"  {task}:")
    ds, ps = [], []
    for s in [1, 2, 3]:
        n = load_pred(f"nait_r30_s{s}", task)
        r = load_pred(f"random_r30_s{s}", task)
        if not (n and r):
            continue
        b = sum(1 for x, y in zip(n, r) if int(x["correct"]) == 1 and int(y["correct"]) == 0)
        c = sum(1 for x, y in zip(n, r) if int(x["correct"]) == 0 and int(y["correct"]) == 1)
        d = (b - c) / len(n) * 100
        p = mcnemar_exact(b, c)
        ds.append(d)
        ps.append(p)
        print(f"     seed {s}: nait 多对 {b:3d} / random 多对 {c:3d} → 差 {d:+.2f}pp  p={p:.3f}")
    if ds:
        print(f"     3 种子平均 {np.mean(ds):+.2f}pp，范围 [{min(ds):+.2f}, {max(ds):+.2f}]")
        print(f"     方向一致？{'是' if all(x > 0 for x in ds) or all(x < 0 for x in ds) else '否（符号翻转）'}")

print()
print("=" * 72)
print("I. 长度混杂（用当前池子重算）")
print("=" * 72)
subs = json.loads((C.SUBSETS / "subsets.json").read_text(encoding="utf-8"))
sel30 = set(subs["nait"]["30"])
lens = np.array([len(by_id[r["id"]]["instruction"]) for r in train])
is_sel = np.array([r["id"] in sel30 for r in train])
print(f"  选中   n={is_sel.sum():5d}  平均长度 {lens[is_sel].mean():7.1f} 字符  中位 {np.median(lens[is_sel]):.0f}")
print(f"  未选中 n={(~is_sel).sum():5d}  平均长度 {lens[~is_sel].mean():7.1f} 字符  中位 {np.median(lens[~is_sel]):.0f}")
diff = abs(lens[is_sel].mean() - lens[~is_sel].mean()) / lens.mean() * 100
print(f"  差异 {diff:.1f}%  → {'长度不是混杂因素' if diff < 5 else '⚠️ 选择与长度相关，需要在论文里讨论'}")

rng = np.random.default_rng(1)
rand_idx = rng.choice(len(train), len(sel30), replace=False)
is_rand = np.zeros(len(train), bool)
is_rand[rand_idx] = True
print(f"  对照：随机子集平均长度 {lens[is_rand].mean():7.1f} 字符")

print()
print("=" * 72)
print("J. 评测集内部重复（影响 CI 宽度）")
print("=" * 72)
medmcqa = read_jsonl(C.PROC / "medmcqa.jsonl")


def norm(s):
    return "".join(ch for ch in s.lower() if ch.isalnum())


c = Counter(norm(r["question"]) for r in medmcqa)
dups = {k: v for k, v in c.items() if v > 1}
print(f"  medmcqa 4,183 题里有 {len(dups)} 组重复题干，涉及 {sum(dups.values())} 题（{sum(dups.values())/len(medmcqa):.2%}）")
print(f"  → 重复题会让 CI 略微偏窄，但占比 {sum(dups.values())/len(medmcqa):.1%} 可忽略")

print()
print("=" * 72)
print("K. 结论")
print("=" * 72)
print("  1) nait vs random：三个种子方向是否一致，见 H 段 → 决定能不能主张'优于随机'")
print("  2) 跨种子合并 MCnemar 的 p 值不成立（同一批题数了 3 遍），eq_table 里的 p 只能当参考")
print("  3) sample_stats.csv 若标 ❌，说明是旧池子的残留产物，必须重新导")
