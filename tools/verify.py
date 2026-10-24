"""verify.py - 给不懂技术的你用的"体检报告"。

它不训练、不改数据，只做一件事：把每一步应该成立的**硬事实**逐条核对，
打印 ✅ / ❌ 加一句人话解释。你不需要看懂过程，只需要看有没有红色的 ❌。

用法：
    .venv\\Scripts\\python.exe tools\\verify.py
"""
from __future__ import annotations

import gzip
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as C  # noqa: E402

# Windows 的 cmd 默认是 GBK，打 ✅ / 中文会 UnicodeEncodeError，强制走 UTF-8
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PASS, FAIL, SKIP = [], [], []


def ok(msg: str) -> None:
    PASS.append(msg)
    print(f"  \u2705 {msg}")


def bad(msg: str) -> None:
    FAIL.append(msg)
    print(f"  \u274c {msg}")


def skip(msg: str) -> None:
    SKIP.append(msg)
    print(f"  \u23ed  {msg}")


def count_lines(path: str) -> int:
    if not os.path.exists(path):
        return -1
    n = 0
    with open(path, "r", encoding="utf-8") as f:
        for _ in f:
            n += 1
    return n


def load_jsonl(path: str, limit: int | None = None) -> list[dict]:
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            out.append(json.loads(line))
            if limit and len(out) >= limit:
                break
    return out


def gz_rows(path: str) -> list[dict]:
    import csv

    with gzip.open(path, "rt", encoding="utf-8") as f:
        return list(csv.DictReader(f))


print("=" * 72)
print("DataDiet-EHR 体检报告")
print("=" * 72)

# ---------------------------------------------------------------- 1. 数据规模
print("\n[1] 数据规模：每个文件的行数对不对")
expect = {
    "train.jsonl": C.N_TRAIN,
    "probe.jsonl": C.N_PROBE,
    "medqa.jsonl": 1273,
    "medmcqa.jsonl": 4183,
}
for name, want in expect.items():
    path = os.path.join(C.PROC, name)
    got = count_lines(path)
    if got < 0:
        bad(f"{name} 不存在")
    elif got == want:
        ok(f"{name} = {got:,} 行（与预期一致）")
    else:
        bad(f"{name} = {got:,} 行，预期 {want:,} 行")

# ------------------------------------------------------- 2. 训练/评测集不串味
print("\n[2] 防泄漏：训练集和评测集不能是同一批题")
try:
    train_ids = {r["id"] for r in load_jsonl(os.path.join(C.PROC, "train.jsonl"))}
    probe_ids = {r["id"] for r in load_jsonl(os.path.join(C.PROC, "probe.jsonl"))}
    medqa_ids = {r["id"] for r in load_jsonl(os.path.join(C.PROC, "medqa.jsonl"))}
    medmcqa_ids = {r["id"] for r in load_jsonl(os.path.join(C.PROC, "medmcqa.jsonl"))}
    if train_ids & probe_ids:
        bad(f"train 与 probe 有 {len(train_ids & probe_ids)} 个重复 id")
    else:
        ok("train 与 probe 完全不相交")
    if train_ids & (medqa_ids | medmcqa_ids):
        bad(f"train 与评测集有 {len(train_ids & (medqa_ids | medmcqa_ids))} 个重复 id")
    else:
        ok("train 与两个评测集完全不相交")
    if len(train_ids) != len(load_jsonl(os.path.join(C.PROC, "train.jsonl"))):
        bad("train.jsonl 内部有重复 id")
    else:
        ok("train.jsonl 内部无重复 id")
except FileNotFoundError as e:
    bad(f"读取失败：{e}")

# ---------------------------------------------------- 3. 评测集答案不能偏科
print("\n[3] 评测集答案分布：四个选项该差不多各占 25%")
for name in ("medqa.jsonl", "medmcqa.jsonl"):
    path = os.path.join(C.PROC, name)
    if not os.path.exists(path):
        skip(f"{name} 不存在")
        continue
    ans = Counter(int(r["answer"]) for r in load_jsonl(path))
    total = sum(ans.values())
    shares = {k: ans.get(k, 0) / total for k in range(4)}
    worst = max(shares.values()) - min(shares.values())
    txt = " ".join(f"{'ABCD'[k]}={shares[k]:.0%}" for k in range(4))
    if worst <= 0.15:
        ok(f"{name}: {txt}（均衡，说明没有系统性偏差）")
    else:
        bad(f"{name}: {txt}（偏得太厉害，题目或解析可能有问题）")

# --------------------------------------------------------- 4. 子集是不是真子集
print("\n[4] 子集选择：数量对不对、是不是都来自训练池")
sub_path = os.path.join(C.SUBSETS, "subsets.json")
if not os.path.exists(sub_path):
    skip("subsets.json 还不存在（第 8 步激活采集还没跑完）")
else:
    subs = json.load(open(sub_path, "r", encoding="utf-8"))
    for method, per_ratio in subs.items():
        for ratio_key, ids in per_ratio.items():
            want = int(round(float(ratio_key) / 100.0 * len(train_ids)))
            n = len(set(ids))
            tag = f"{method}@{ratio_key}%"
            if n != want:
                bad(f"{tag}: 取了 {n:,} 条，应为 {want:,} 条")
            elif not set(ids) <= train_ids:
                bad(f"{tag}: 有 {len(set(ids) - train_ids)} 条不在训练池里")
            else:
                ok(f"{tag}: {n:,} 条 = {ratio_key}% × {len(train_ids):,}，且都来自训练池")

# ------------------------------------------------- 5. 评测结果与原始预测一致
print("\n[5] 结果自洽：表里的准确率能不能由逐题预测复算出来")
pred_dir = C.PREDS
metrics_path = os.path.join(C.RESULTS, "metrics_long.csv")
if not os.path.exists(metrics_path):
    skip("metrics_long.csv 还不存在")
else:
    import csv

    with open(metrics_path, "r", encoding="utf-8") as f:
        metrics = list(csv.DictReader(f))
    checked = 0
    for row in metrics:
        eid, task = row["exp_id"], row["task"]
        path = os.path.join(pred_dir, f"{eid}_{task}.csv.gz")
        if not os.path.exists(path):
            bad(f"{eid}/{task}: 表里有记录但逐题文件缺失")
            continue
        rows = gz_rows(path)
        real = sum(int(r["correct"]) for r in rows) / max(1, len(rows))
        if abs(real - float(row["value"])) < 1e-6 and len(rows) == int(row["n_items"]):
            checked += 1
        else:
            bad(f"{eid}/{task}: 表里 {row['value']}，逐题复算是 {real:.4f}（{len(rows)} 题）")
    if checked:
        ok(f"{checked} 条记录全部可由逐题预测复算（数字没被手改过）")

# --------------------------------------------- 6. 分数是不是"人类常识范围"
print("\n[6] 分数常识：选择题四选一，瞎猜是 25%")
if os.path.exists(metrics_path):
    for row in metrics:
        v = float(row["value"])
        tag = f"{row['exp_id']}/{row['task']}"
        if v > 0.90:
            bad(f"{tag} = {v:.1%} 高得可疑（可能是答案泄漏）")
        elif v < 0.25:
            bad(f"{tag} = {v:.1%} 低于瞎猜（可能解析或对齐有 bug）")
        else:
            ok(f"{tag} = {v:.1%}（在 25%–90% 的合理区间）")

# ---------------------------------------------------- 7. 算力账：跑了几次、多久
print("\n[7] 训练记录：每次跑的样本数与耗时")
run_dir = C.RUNS
if not os.path.isdir(run_dir):
    skip("还没有训练记录")
else:
    files = [f for f in os.listdir(run_dir) if f.endswith(".json")]
    if not files:
        skip("还没有训练记录")
    for fn in sorted(files):
        rec = json.load(open(os.path.join(run_dir, fn), "r", encoding="utf-8"))
        n = rec.get("n_samples", 0)
        sec = rec.get("train_seconds", 0)
        rate = n / sec if sec else 0
        print(f"  \u2139  {fn[:-5]:<24} {n:>6,} 样本  {sec/60:>5.1f} 分钟  {rate:>5.2f} 样本/秒")
    if all(json.load(open(os.path.join(run_dir, fn), "r", encoding="utf-8")).get("n_samples", 0) > 0 for fn in files):
        ok(f"{len(files)} 次训练都有样本数和耗时记录（算力可以复算）")

# ------------------------------------------------------------------ 汇总
print("\n" + "=" * 72)
print(f"汇总：{len(PASS)} 项通过，{len(FAIL)} 项失败，{len(SKIP)} 项还没有数据")
print("=" * 72)
if FAIL:
    print("\n需要处理的失败项：")
    for m in FAIL:
        print(f"  \u274c {m}")
    sys.exit(1)
print("\n没有发现硬伤。这不等于结论正确，但等于：数据没串、数字没编、账目对得上。")
