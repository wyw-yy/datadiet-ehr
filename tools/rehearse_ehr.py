"""端到端演练：合成"假病历" → 跑 prepare_mimic → 六组硬检查。

目的：真数据（MIMIC / 院内 EMR）到手那天，只需要换 `--src`，
不用现场改代码、不用现场想"怎么验证切分对不对"。

用法：
    .venv\\Scripts\\python.exe tools\\rehearse_ehr.py          # 全流程 + 检查
    .venv\\Scripts\\python.exe tools\\rehearse_ehr.py --keep    # 保留中间产物

检查项：
  A. 输入产物齐全（5 个原始表 + 3 个 JSONL + 切分清单）
  B. 病人级切分：同一个人不跨 train/probe/eval
  C. 答案不泄漏：住院经过里不该出现其它章节（用药/诊断/处置）
  D. 去标识化：正文里不该有 [**...**] 占位符
  E. 科室映射：六个桶都在用，other 不超过 90%（全 other 说明映射写错）
  F. 契约：id 前缀与桶一致、id 全局唯一、正文长度 ≥200

退出码 0 = 全绿。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PY = ROOT / ".venv" / "Scripts" / "python.exe"
FAKE = ROOT / "data" / "raw" / "_fake_ehr"
OUT = ROOT / "data" / "processed_mimic_fake"
BUCKETS = {"train": "train.jsonl", "probe": "probe.jsonl", "eval": "mimic_eval.jsonl"}
DEPTS = {"cardio", "onco", "neuro", "resp", "endo", "other"}


def run(cmd: list[str]) -> int:
    print("$", " ".join(str(c) for c in cmd[1:]))
    return subprocess.call([str(c) for c in cmd])


def load() -> dict:
    data = {}
    for bucket, name in BUCKETS.items():
        p = OUT / name
        data[bucket] = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    return data


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true", help="保留 _fake_ehr 与 processed_mimic_fake")
    ap.add_argument("--n-subject", type=int, default=150)
    a = ap.parse_args()

    fails = []
    warns = []

    print("=" * 74)
    print("步骤 1/2：造合成病历（假的，只用来演练）")
    print("=" * 74)
    if run([PY, ROOT / "tools" / "make_fake_ehr.py", "--out", FAKE,
            "--n-subject", str(a.n_subject)]) != 0:
        print("❌ 合成数据生成失败")
        sys.exit(1)

    print()
    print("=" * 74)
    print("步骤 2/2：跑真实流水线 prepare_mimic.py")
    print("=" * 74)
    if run([PY, ROOT / "prepare_mimic.py", "--src", FAKE, "--out", OUT,
            "--n-probe", "25", "--n-eval", "25"]) != 0:
        print("❌ prepare_mimic 失败")
        sys.exit(1)

    print()
    print("=" * 74)
    print("检查 A：产物齐全")
    print("=" * 74)
    need = [FAKE / "hosp" / f for f in
            ("patients.csv.gz", "admissions.csv.gz", "diagnoses_icd.csv.gz", "d_icd_diagnoses.csv.gz")]
    need.append(FAKE / "note" / "discharge.csv.gz")
    need += [OUT / n for n in BUCKETS.values()]
    need.append(OUT / "mimic_split.json")
    for p in need:
        ok = p.exists() and p.stat().st_size > 0
        print(f"{'✅' if ok else '❌'} {p.relative_to(ROOT)}  {p.stat().st_size if p.exists() else 0} B")
        if not ok:
            fails.append(f"缺文件 {p.name}")

    man = json.loads((OUT / "mimic_split.json").read_text(encoding="utf-8"))
    rows = load()

    print()
    print("=" * 74)
    print("检查 B：病人级切分（同一个病人不许跨集合）")
    print("=" * 74)
    sets = {k: set(v) for k, v in man["splits"].items()}
    inter = (sets["train"] & sets["probe"]) | (sets["train"] & sets["eval"]) | (sets["probe"] & sets["eval"])
    print(f"{'✅' if not inter else '❌'} 三个集合的病人互不重叠  "
          f"train {len(sets['train'])} / probe {len(sets['probe'])} / eval {len(sets['eval'])} 人")
    if inter:
        fails.append(f"病人跨集合: {sorted(inter)[:5]}")

    subj_bucket: dict[str, set] = {}
    for bucket, pairs in man["row_subject"].items():
        for rid, sid in pairs:
            subj_bucket.setdefault(sid, set()).add(bucket)
    crossed = {s: b for s, b in subj_bucket.items() if len(b) > 1}
    print(f"{'✅' if not crossed else '❌'} 逐条样本反查：同一个病人的多条记录都在同一个集合  "
          f"{len(subj_bucket)} 个病人")
    if crossed:
        fails.append(f"同一病人记录跨集合: {list(crossed)[:3]}")

    n_multi = sum(1 for s in subj_bucket if
                  sum(1 for b in man["row_subject"] for rid, sid in man["row_subject"][b] if sid == s) > 1)
    if n_multi == 0:
        warns.append("这批合成数据里没有'同一病人多次住院'，B 项的检验力不足")
    else:
        print(f"       （其中 {n_multi} 个病人有多次住院，真正的检验对象）")

    print()
    print("=" * 74)
    print("检查 C：答案不泄漏（正文里不该夹带用药/诊断/处置章节）")
    print("=" * 74)
    leaks = 0
    for bucket, items in rows.items():
        for r in items:
            t = r["response"]
            for bad in ("Discharge Medications", "Discharge Diagnosis", "Discharge Disposition",
                        "History of Present Illness", "Chief Complaint"):
                if bad.lower() in t.lower():
                    leaks += 1
                    break
    print(f"{'✅' if leaks == 0 else '❌'} 没有样本把其它章节带进答案  泄漏 {leaks} 条")
    if leaks:
        fails.append(f"答案夹带其它章节 {leaks} 条")

    print()
    print("=" * 74)
    print("检查 D：去标识化占位符")
    print("=" * 74)
    ph = sum(1 for items in rows.values() for r in items if "[**" in r["response"])
    print(f"{'✅' if ph == 0 else '❌'} 正文里的 [**...**] 已清除  残留 {ph} 条")
    if ph:
        fails.append(f"残留 de-id 占位符 {ph} 条")

    print()
    print("=" * 74)
    print("检查 E：科室映射")
    print("=" * 74)
    dist: dict[str, int] = {}
    for items in rows.values():
        for r in items:
            dist[r["dept"]] = dist.get(r["dept"], 0) + 1
    total = sum(dist.values()) or 1
    print("      分布:", ", ".join(f"{k} {v}" for k, v in sorted(dist.items(), key=lambda kv: -kv[1])))
    unknown = set(dist) - DEPTS
    other_pct = 100.0 * dist.get("other", 0) / total
    print(f"{'✅' if not unknown else '❌'} 科室名都在六桶内  {sorted(unknown) if unknown else 'ok'}")
    print(f"{'✅' if other_pct < 90 else '❌'} other 占比 {other_pct:.1f}% < 90%")
    if unknown:
        fails.append(f"未知科室 {unknown}")
    if other_pct >= 90:
        fails.append("other 占比过高，ICD 映射可能写错")

    print()
    print("=" * 74)
    print("检查 F：JSONL 契约")
    print("=" * 74)
    ids = []
    bad_prefix = 0
    short = 0
    for bucket, items in rows.items():
        pref = "m" + bucket[0]
        for r in items:
            ids.append(r["id"])
            if not r["id"].startswith(pref):
                bad_prefix += 1
            if len(r["response"]) < 200:
                short += 1
            for k in ("id", "dept", "instruction", "response"):
                if k not in r:
                    fails.append(f"{bucket} 缺字段 {k}")
    dup = len(ids) - len(set(ids))
    print(f"{'✅' if bad_prefix == 0 else '❌'} id 前缀与桶一致  {bad_prefix} 处不符")
    print(f"{'✅' if dup == 0 else '❌'} id 全局唯一  {len(ids)} 条 / {dup} 个重复")
    print(f"{'✅' if short == 0 else '❌'} 正文长度 ≥200  {short} 条过短")
    if bad_prefix:
        fails.append(f"id 前缀不符 {bad_prefix}")
    if dup:
        fails.append(f"id 重复 {dup}")
    if short:
        fails.append(f"正文过短 {short}")

    print()
    print("=" * 74)
    if warns:
        for w in warns:
            print("⚠️ ", w)
    if fails:
        print(f"❌ 演练失败 {len(fails)} 项：")
        for f in fails:
            print("   -", f)
        sys.exit(1)
    print("✅ 演练全部通过。真数据到手后，只需：")
    print("   .venv\\Scripts\\python.exe prepare_mimic.py --check --src data\\raw\\mimic")
    print("   .venv\\Scripts\\python.exe prepare_mimic.py --src data\\raw\\mimic --out data\\processed_mimic")
    if not a.keep:
        import shutil
        shutil.rmtree(FAKE, ignore_errors=True)
        shutil.rmtree(OUT, ignore_errors=True)
        print("   （已清理合成数据；加 --keep 可保留）")


if __name__ == "__main__":
    main()
