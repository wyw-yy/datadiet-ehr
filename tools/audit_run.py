"""一次性审计：确认这一轮跑的是真数据、真微调、真评测，不是摆拍。

跑法：.venv\\Scripts\\python.exe tools\\audit_run.py
每条都给出处（文件 / 数字），不通过就打印 ❌ 并以非 0 退出。
"""
import gzip
import json
import random
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as C

ok = True


def check(name, cond, detail=""):
    global ok
    mark = "✅" if cond else "❌"
    if not cond:
        ok = False
    print(f"{mark} {name}" + (f"  —  {detail}" if detail else ""))


def read_jsonl(p):
    with open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f]


print("=" * 70)
print("1. 原始数据：是不是真文件")
print("=" * 70)
for pat, lo in [("data/raw/medmcqa-train/*.parquet", 80e6),
                ("data/raw/medqa/*.jsonl", 1e6)]:
    files = list(C.PROJ.glob(pat))
    total = sum(f.stat().st_size for f in files)
    check(f"{pat} 存在且够大", bool(files) and total > lo,
          f"{len(files)} 个文件, {total/1e6:.1f} MB")

print()
print("=" * 70)
print("2. 处理后的数据：是不是人写的东西")
print("=" * 70)
train = read_jsonl(C.PROC / "train.jsonl")
probe = read_jsonl(C.PROC / "probe.jsonl")
medmcqa = read_jsonl(C.PROC / "medmcqa.jsonl")
medqa = read_jsonl(C.PROC / "medqa.jsonl")

check("train.jsonl 行数", len(train) == C.N_TRAIN, f"{len(train)} 行（期望 {C.N_TRAIN}）")
check("medmcqa 考题行数 > 3000", len(medmcqa) > 3000, f"{len(medmcqa)} 题")
check("medqa 考题行数 > 1000", len(medqa) > 1000, f"{len(medqa)} 题")

r = train[0]
check("训练样本有题干和答案", bool(r["instruction"].strip()) and bool(r["response"].strip()),
      f'instruction={r["instruction"][:60]}...  response={r["response"][:40]}...')
q = medmcqa[0]
check("考题有四个选项", len(q["options"]) == 4, f'{q["question"][:60]}...')
check("答案下标合法", all(0 <= int(x["answer"]) <= 3 for x in medmcqa[:200]),
      f'示例答案下标 = {q["answer"]}（0=A）')

# 真数据的标志：里面应该有医学词，不是 lorem ipsum
text = " ".join(x["instruction"][:80] for x in train[:200]).lower()
med_terms = ["patient", "pain", "treatment", "disease", "drug", "diagnosis",
             "symptoms", "therapy", "infection", "blood"]
hits = sum(t in text for t in med_terms)
check("训练文本含医学术语（证明不是假数据）", hits >= 5, f"命中 {hits}/10 个医学术语")

print()
print("=" * 70)
print("3. 评测：是不是真的加载了 LoRA 权重")
print("=" * 70)


def load_pred(eid, task):
    p = C.PREDS / f"{eid}_{task}.csv.gz"
    if not p.exists():
        return None
    with gzip.open(p, "rt", encoding="utf-8") as f:
        import csv
        return list(csv.DictReader(f))


full = load_pred("full_s1", "medmcqa")
nait = load_pred("nait_r30_s1", "medmcqa")
check("full_s1 的逐题预测存在", full is not None and len(full) > 0,
      f"{len(full) if full else 0} 条")
check("nait_r30_s1 的逐题预测存在", nait is not None and len(nait) > 0,
      f"{len(nait) if nait else 0} 条")

if full and nait:
    diff = sum(a["pred"] != b["pred"] for a, b in zip(full, nait))
    rate = diff / len(full)
    check("两个模型的预测不完全相同（证明权重真的变了）", rate > 0.01,
          f"{diff}/{len(full)} 条预测不同 = {rate:.1%}")

    # 准确率能不能从逐题记录里复算出来
    acc_f = sum(int(x["correct"]) for x in full) / len(full)
    acc_n = sum(int(x["correct"]) for x in nait) / len(nait)
    print(f"   复算：full_s1 medmcqa = {acc_f:.4f}，nait_r30_s1 = {acc_n:.4f}")

print()
print("=" * 70)
print("4. 子集：挑出来的和随机的真的不一样")
print("=" * 70)
subs = json.loads((C.SUBSETS / "subsets.json").read_text(encoding="utf-8"))
nait30 = set(subs["nait"]["30"])
check("nait 30% 子集大小", len(nait30) == 3600, f"{len(nait30)} 条")

rng = random.Random(1)
pool = [x["id"] for x in train]
rand30 = set(rng.sample(pool, 3600))
check("nait 与 random 子集不同（选择不是随机数）",
      len(nait30 & rand30) < 3400,
      f"重叠 {len(nait30 & rand30)}/3600 = {len(nait30 & rand30)/36:.1f}%")
check("nait 子集全部来自训练池", nait30 <= set(pool),
      f"越界 {len(nait30 - set(pool))} 条")

# 分层是否真的生效
from collections import Counter
dept_all = Counter(x["dept"] for x in train)
dept_sel = Counter(x["dept"] for x in train if x["id"] in nait30)
print("   科室配额（池子占比 → 选中占比）：")
for d in sorted(dept_all, key=lambda k: -dept_all[k]):
    if dept_all[d] < 50:
        continue
    pa = dept_all[d] / len(train)
    ps = dept_sel[d] / len(nait30)
    print(f"     {d:8s} {dept_all[d]:6d} ({pa:5.1%})  →  {dept_sel[d]:5d} ({ps:5.1%})")
check("分层配额生效（各科室占比偏差 < 3pp）",
      all(abs(dept_sel[d] / len(nait30) - dept_all[d] / len(train)) < 0.03
          for d in dept_all if dept_all[d] >= 50),
      "见上表")

print()
print("=" * 70)
print("5. 泄漏：训练集和考题有没有重题")
print("=" * 70)


def norm(s):
    return "".join(ch for ch in s.lower() if ch.isalnum())[:200]


tr = {norm(x["instruction"]) for x in train}
for name, rows in [("medmcqa", medmcqa), ("medqa", medqa), ("probe", probe)]:
    key = "question" if name != "probe" else "instruction"
    ov = sum(norm(x[key]) in tr for x in rows)
    check(f"{name} 与训练集的重题数", ov <= 2, f"{ov}/{len(rows)} 条")

print()
print("=" * 70)
print("6. 结论窗口")
print("=" * 70)
print("✅ 数据是真的（MedMCQA 真实题库 + 真实医患问答）" if ok else "❌ 有问题，看上面红叉")
print("⚠️  但这是公开题库，不是院内电子病历 —— 论文必须写清楚")
sys.exit(0 if ok else 1)
