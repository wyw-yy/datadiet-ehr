"""把 MIMIC-IV + MIMIC-IV-Note 转成本项目的 JSONL 契约。

现在还**没有**数据，所以这个脚本只能做两件事：
  1) `--check`   ：检查目录结构与必需列，告诉你缺什么
  2) `--selftest`：用合成文本跑一遍全部纯函数，验证切分/映射逻辑没写错

有数据之后再跑 `--src ... --out ...` 真正生成：
    data/processed/train.jsonl / probe.jsonl / mimic_eval.jsonl

任务定义（写进 PROTOCOL 之前先定在这里）：
    instruction = 患者背景（年龄/性别/主诉/主要诊断章节）+ "写出住院经过这一节"
    response    = 出院小结里 "Brief Hospital Course" / "Hospital Course" 的原文
    dept        = 主诊断 ICD-10 章节 → 六个科室桶
    切分        = **按 subject_id**，同一个人绝不跨集合（防止同一病人的多次住院泄漏）
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------- 纯函数

# MIMIC 出院小结的章节标题五花八门，按常见写法 + 变体匹配
SECTION_HEADERS = {
    "hospital_course": [
        r"brief hospital course", r"hospital course", r"hospital stay",
        r"clinical course", r"course in hospital",
    ],
    "discharge_diagnosis": [r"discharge diagnosis", r"final diagnosis", r"diagnoses"],
    "chief_complaint": [r"chief complaint", r"reason for admission", r"cc:"],
}

# ICD-10 首字母 → 科室桶（与公开题库的六个桶保持一致）
ICD_CHAPTER_DEPT = {
    "A": "other", "B": "other",           # 感染
    "C": "onco", "D": "onco",             # 肿瘤/血液
    "E": "endo",                          # 内分泌/代谢
    "F": "neuro",                         # 精神（归到 neuro 桶避免新增类别）
    "G": "neuro",                         # 神经
    "H": "other", "I": "cardio",          # 眼耳 / 循环
    "J": "resp",                          # 呼吸
    "K": "other",                         # 消化
    "L": "other",                         # 皮肤
    "M": "other",                         # 肌肉骨骼
    "N": "other",                         # 泌尿
    "O": "other",                         # 产科
    "P": "other", "Q": "other",           # 围产/先天
    "R": "other", "S": "other", "T": "other",  # 症状/外伤
    "V": "other", "W": "other", "X": "other",
    "Y": "other", "Z": "other",
}


def icd_to_dept(code: str) -> str:
    """ICD-10 编码 → 科室桶。空/非法一律 other。"""
    if not code:
        return "other"
    c = str(code).strip().upper()
    if not c:
        return "other"
    return ICD_CHAPTER_DEPT.get(c[0], "other")


def extract_section(text: str, kind: str = "hospital_course") -> str:
    """从出院小结里抠出指定章节的正文。

    做法：找所有"标题行"，正文取到下一个标题行之前。标题行判定 = 整行较短（<=60 字符）、
    命中白名单、且不是以句号结尾的普通句。
    """
    if not text:
        return ""
    pats = SECTION_HEADERS[kind]
    lines = text.splitlines()
    start = -1
    for i, line in enumerate(lines):
        s = line.strip().strip(":").strip().lower()
        if not s or len(s) > 60:
            continue
        if any(re.fullmatch(rf"{p}\s*:?", s) for p in pats):
            start = i + 1
            break
    if start < 0:
        return ""
    out: list[str] = []
    for line in lines[start:]:
        s = line.strip()
        # 遇到下一个章节标题就停
        if s and len(s) <= 60 and s.endswith(":") and not s.endswith("."):
            break
        if s and len(s) <= 40 and re.fullmatch(r"[A-Za-z /()\-]+", s):
            break
        out.append(line)
    body = "\n".join(out).strip()
    # 去掉 de-identification 占位符，避免模型学到 [**...**]
    body = re.sub(r"\[\*\*.*?\*\*\]", "", body)
    return re.sub(r"\n{3,}", "\n\n", body).strip()


def split_by_subject(subjects: list[str], seed: int = 42,
                     n_probe: int = 500, n_eval: int = 500) -> dict[str, set[str]]:
    """按 subject_id 切三个互不重叠的集合。返回 {'train': set, 'probe': set, 'eval': set}。"""
    uniq = sorted(set(subjects))
    random.Random(seed).shuffle(uniq)
    n_eval = min(n_eval, len(uniq) // 5)
    n_probe = min(n_probe, len(uniq) // 5)
    eval_s = set(uniq[:n_eval])
    probe_s = set(uniq[n_eval:n_eval + n_probe])
    train_s = set(uniq[n_eval + n_probe:])
    return {"train": train_s, "probe": probe_s, "eval": eval_s}


def make_pair(meta: dict, course: str, dept: str, rid: str) -> dict:
    """组装一条 SFT 样本。meta 里放年龄/性别/主诉等背景。"""
    bg = []
    if meta.get("age"):
        bg.append(f"{meta['age']}-year-old")
    if meta.get("gender"):
        bg.append(str(meta["gender"]).lower())
    if meta.get("chief"):
        bg.append(f"presenting with {meta['chief'][:200]}")
    if meta.get("diagnosis"):
        bg.append(f"primary diagnosis: {meta['diagnosis'][:120]}")
    context = ", ".join(bg) if bg else "an adult inpatient"
    ins = (f"Patient background: {context}.\n\n"
           f"Write the 'Brief Hospital Course' section of the discharge summary "
           f"in 120-200 words, in clinical language.")
    return {"id": rid, "dept": dept, "instruction": ins, "response": course}


# ---------------------------------------------------------------- 自测

def selftest() -> int:
    fails = 0

    def check(ok: bool, name: str, detail: str = "") -> None:
        nonlocal fails
        print(f"{'✅' if ok else '❌'} {name}  {detail}")
        if not ok:
            fails += 1

    note = (
        "Admission Date: 2100-01-02\n"
        "Chief Complaint: Shortness of breath\n"
        "History of Present Illness:\n"
        "The patient is a 67 year old man with COPD who presented with dyspnea.\n"
        "Brief Hospital Course:\n"
        "He was admitted and started on steroids and nebulizers.\n"
        "Symptoms improved over three days. [**Name**] was seen by PT.\n"
        "He was discharged home on oral prednisone.\n"
        "Discharge Medications:\n"
        "1. Prednisone 40 mg daily\n"
        "Discharge Diagnosis: COPD exacerbation\n"
    )
    body = extract_section(note, "hospital_course")
    check("steroids and nebulizers" in body, "切出住院经过", body.splitlines()[0][:40])
    check("Discharge Medications" not in body, "遇到下一节就停", "")
    check("[**" not in body, "去掉 de-id 占位符", "")
    check(extract_section("no headers here at all", "hospital_course") == "",
          "没有该章节时返回空串", "")

    check(icd_to_dept("J44.1") == "resp", "J 开头 → resp", icd_to_dept("J44.1"))
    check(icd_to_dept("I50.9") == "cardio", "I 开头 → cardio", icd_to_dept("I50.9"))
    check(icd_to_dept("C34.9") == "onco", "C 开头 → onco", icd_to_dept("C34.9"))
    check(icd_to_dept("E11.9") == "endo", "E 开头 → endo", icd_to_dept("E11.9"))
    check(icd_to_dept("G40.9") == "neuro", "G 开头 → neuro", icd_to_dept("G40.9"))
    check(icd_to_dept("") == "other", "空编码 → other", "")

    subs = [f"s{i:04d}" for i in range(200)]
    sp = split_by_subject(subs, seed=42, n_probe=20, n_eval=20)
    check(not (sp["train"] & sp["probe"]), "train/probe 不重叠", "")
    check(not (sp["train"] & sp["eval"]), "train/eval 不重叠", "")
    check(not (sp["probe"] & sp["eval"]), "probe/eval 不重叠", "")
    check(sum(len(v) for v in sp.values()) == 200, "人数守恒", str(sum(len(v) for v in sp.values())))
    check(len(sp["eval"]) == 20 and len(sp["probe"]) == 20, "eval/probe 各 20 人", "")

    p = make_pair({"age": 67, "gender": "M", "chief": "dyspnea", "diagnosis": "COPD"},
                  body, "resp", "m00001")
    check("67-year-old" in p["instruction"], "背景写进 instruction", "")
    check(p["response"] == body, "response 是住院经过原文", "")
    check(p["dept"] == "resp", "dept 正确", "")

    print()
    if fails:
        print(f"❌ 自测失败 {fails} 项")
        return 1
    print("✅ 自测全通过（有数据之后可直接跑 --src/--out）")
    return 0


# ---------------------------------------------------------------- 主流程

REQUIRED = {
    "hosp/patients.csv.gz": ["subject_id", "gender", "anchor_age"],
    "hosp/admissions.csv.gz": ["subject_id", "hadm_id", "admittime"],
    "hosp/diagnoses_icd.csv.gz": ["subject_id", "hadm_id", "seq_num", "icd_code", "icd_version"],
    "hosp/d_icd_diagnoses.csv.gz": ["icd_code", "long_title"],
    "note/discharge.csv.gz": ["subject_id", "hadm_id", "text"],
}


def check_layout(src: Path) -> int:
    import pandas as pd

    bad = 0
    for rel, cols in REQUIRED.items():
        p = src / rel
        if not p.exists():
            print(f"❌ 缺文件 {rel}")
            bad += 1
            continue
        try:
            head = pd.read_csv(p, nrows=3)
        except Exception as e:                      # noqa: BLE001
            print(f"❌ 读不了 {rel}: {e}")
            bad += 1
            continue
        miss = [c for c in cols if c not in head.columns]
        print(f"{'✅' if not miss else '❌'} {rel}  列 {list(head.columns)[:6]}…"
              + (f"  缺 {miss}" if miss else ""))
        if miss:
            bad += 1
    print()
    if bad:
        print(f"❌ {bad} 处问题。先看 docs/MIMIC_CHECKLIST.md")
        return 1
    print("✅ 目录结构齐全，可以跑 --src/--out")
    return 0


def build(src: Path, out: Path, n_probe: int, n_eval: int, seed: int) -> int:
    import pandas as pd

    pat = pd.read_csv(src / "hosp/patients.csv.gz", usecols=["subject_id", "gender", "anchor_age"])
    adm = pd.read_csv(src / "hosp/admissions.csv.gz", usecols=["subject_id", "hadm_id"])
    dx = pd.read_csv(src / "hosp/diagnoses_icd.csv.gz")
    ddx = pd.read_csv(src / "hosp/d_icd_diagnoses.csv.gz")
    note = pd.read_csv(src / "note/discharge.csv.gz",
                       usecols=["subject_id", "hadm_id", "text"])

    # 主诊断（seq_num == 1）
    prim = dx[dx["seq_num"] == 1].copy()
    prim = prim.merge(ddx[["icd_code", "long_title"]], on="icd_code", how="left")
    prim = prim.drop_duplicates("hadm_id")[["hadm_id", "icd_code", "long_title"]]

    df = note.merge(prim, on="hadm_id", how="left")
    df = df.merge(pat, on="subject_id", how="left")
    df = df.merge(adm, on=["subject_id", "hadm_id"], how="left")
    print(f"[mimic] {len(df)} 份出院小结，{df['subject_id'].nunique()} 个病人")

    sp = split_by_subject(df["subject_id"].astype(str).tolist(), seed, n_probe, n_eval)
    rows = {"train": [], "probe": [], "eval": []}
    row_subject: dict[str, list] = {"train": [], "probe": [], "eval": []}
    skipped = 0
    for _, r in df.iterrows():
        body = extract_section(str(r["text"]), "hospital_course")
        if len(body) < 200:                 # 太短的不当样本
            skipped += 1
            continue
        chief = extract_section(str(r["text"]), "chief_complaint")
        meta = {"age": int(r["anchor_age"]) if pd.notna(r["anchor_age"]) else None,
                "gender": r["gender"], "chief": chief.splitlines()[0] if chief else "",
                "diagnosis": r.get("long_title") or ""}
        dept = icd_to_dept(str(r.get("icd_code") or ""))
        sid = str(r["subject_id"])
        bucket = "train" if sid in sp["train"] else ("probe" if sid in sp["probe"] else "eval")
        rid = f"m{bucket[0]}{len(rows[bucket]):05d}"
        rows[bucket].append(make_pair(meta, body, dept, rid))
        row_subject[bucket].append([rid, sid])

    out.mkdir(parents=True, exist_ok=True)
    for k, v in rows.items():
        name = "mimic_eval.jsonl" if k == "eval" else f"{k}.jsonl"
        with open(out / name, "w", encoding="utf-8") as f:
            for r in v:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"[mimic] {name}: {len(v)} 条")
    print(f"跳过（住院经过 <200 字符）: {skipped}")
    # 切分清单：审计要用。只记 subject_id 与归属，不记任何文本。
    manifest = {
        "seed": seed, "n_probe": n_probe, "n_eval": n_eval,
        "n_subject": int(df["subject_id"].nunique()),
        "splits": {k: sorted(str(s) for s in v) for k, v in sp.items()},
        "rows": {k: len(v) for k, v in rows.items()},
        # 每条样本属于哪个病人（只有伪 ID，没有文本）——审计要用它证明"同一个人没跨集合"
        "row_subject": row_subject,
        "skipped_short": skipped,
    }
    with open(out / "mimic_split.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print(f"[mimic] 切分清单 {out / 'mimic_split.json'}（{manifest['n_subject']} 个病人）")
    print("[mimic] 注意：MIMIC 的评测是**参考文本生成**（ROUGE/BERTScore + 人工抽检），"
          "不是四选一准确率，R 侧要另写一个分析脚本。")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="检查 src 目录结构")
    ap.add_argument("--selftest", action="store_true", help="用合成文本自测纯函数")
    ap.add_argument("--src", type=Path, default=ROOT / "data" / "raw" / "mimic")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "processed_mimic")
    ap.add_argument("--n-probe", type=int, default=500)
    ap.add_argument("--n-eval", type=int, default=500)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()

    if a.selftest:
        sys.exit(selftest())
    if a.check:
        sys.exit(check_layout(a.src))
    sys.exit(build(a.src, a.out, a.n_probe, a.n_eval, a.seed))


if __name__ == "__main__":
    main()
