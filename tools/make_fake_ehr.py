"""生成一份"长得像 MIMIC-IV"的合成数据，用来在真数据到手之前演练整条流水线。

产出目录结构与 `prepare_mimic.py` 的 REQUIRED 完全一致：
    <out>/hosp/patients.csv.gz
    <out>/hosp/admissions.csv.gz
    <out>/hosp/diagnoses_icd.csv.gz
    <out>/hosp/d_icd_diagnoses.csv.gz
    <out>/note/discharge.csv.gz

刻意做坏的几种情况（真数据里一定会有，提前试）：
  * 章节标题大小写/空格不一致（`Brief Hospital Course:` / `BRIEF HOSPITAL COURSE` / `hospital course :`）
  * 8% 的出院小结**没有**住院经过这一节
  * 10% 的住院经过 < 200 字符（应被跳过）
  * 含 de-identification 占位符 `[**Name**]`、`[**2100-01-01**]`
  * 有的病人多次住院（同 subject_id 多个 hadm_id）→ 用来验证"按病人切分"
  * ICD 覆盖六个科室桶，另外留一批 K/N/R 开头进 other

**这些数据是编的，不得用于任何结论。**
"""
from __future__ import annotations

import argparse
import gzip
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# (icd_code, 主诊断描述, 病程句子, 用药)
CASES = [
    ("J44.1", "Chronic obstructive pulmonary disease with acute exacerbation",
     "He was started on IV methylprednisolone and continuous nebulizers.",
     "Prednisone 40 mg daily"),
    ("J18.9", "Pneumonia, unspecified organism",
     "She was started on ceftriaxone and azithromycin for community acquired pneumonia.",
     "Amoxicillin-clavulanate 875 mg twice daily"),
    ("I50.9", "Heart failure, unspecified",
     "Diuresis with IV furosemide was initiated and she lost four liters of fluid.",
     "Furosemide 40 mg daily"),
    ("I21.4", "Non-ST elevation myocardial infarction",
     "Cardiology was consulted and he underwent cardiac catheterization on hospital day two.",
     "Aspirin 81 mg daily"),
    ("C34.90", "Malignant neoplasm of unspecified part of bronchus or lung",
     "Oncology was consulted and palliative radiation was arranged as an outpatient.",
     "Oxycodone 5 mg every six hours as needed"),
    ("C18.9", "Malignant neoplasm of colon, unspecified",
     "She underwent partial colectomy on hospital day three without complication.",
     "Cefazolin 1 g every eight hours"),
    ("E11.9", "Type 2 diabetes mellitus without complications",
     "Blood glucose was managed with a basal-bolus insulin regimen.",
     "Insulin glargine 18 units nightly"),
    ("E03.9", "Hypothyroidism, unspecified",
     "Levothyroxine was resumed at the prior dose after review of thyroid studies.",
     "Levothyroxine 75 mcg daily"),
    ("G40.909", "Epilepsy, unspecified, not intractable",
     "Neurology was consulted and levetiracetam was loaded intravenously.",
     "Levetiracetam 500 mg twice daily"),
    ("G20.C1", "Parkinsonism",
     "Carbidopa-levodopa was continued and physical therapy evaluated gait safety.",
     "Carbidopa-levodopa 25-100 mg three times daily"),
    ("K92.2", "Gastrointestinal hemorrhage, unspecified",
     "She underwent upper endoscopy which showed a bleeding duodenal ulcer, and clips were placed.",
     "Pantoprazole 40 mg daily"),
    ("N17.9", "Acute kidney injury, unspecified",
     "Creatinine trended down after fluids and holding nephrotoxic agents.",
     "Sodium bicarbonate 650 mg twice daily"),
]

HEADER_VARIANTS = [
    "Brief Hospital Course:",
    "Brief Hospital Course",
    "HOSPITAL COURSE:",
    "Hospital Course:",
    "hospital course :",
    "Clinical Course:",
]


def make_note(rng: random.Random, age: int, gender: str, chief: str,
              course: str, dx: str, med: str, kind: str) -> str:
    """拼一份出院小结。kind = 'full' | 'no_course' | 'short_course'。"""
    lines = [
        "Admission Date: 2100-03-04",
        "Discharge Date: 2100-03-09",
        "",
        f"Chief Complaint: {chief}",
        "",
        "History of Present Illness:",
        f"The patient is a {age} year old {'man' if gender == 'M' else 'woman'} "
        f"with a history of {dx.lower()} who presented with {chief.lower()}.",
        "",
    ]
    if kind != "no_course":
        lines.append(rng.choice(HEADER_VARIANTS))
        if kind == "short_course":
            lines.append(course)
        else:
            lines += [
                course,
                f"[**Name**] was admitted to the general ward. Vital signs were monitored "
                f"every four hours and [**2100-03-05**] repeat labs were obtained.",
                f"The primary team adjusted therapy and the patient improved steadily.",
                f"Case management arranged follow up in the {rng.choice(['cardiology','pulmonary','oncology','endocrine','neurology'])} clinic.",
            ]
        lines.append("")
    lines += [
        "Discharge Medications:",
        f"1. {med}",
        "",
        "Discharge Diagnosis:",
        dx,
        "",
        "Discharge Disposition: Home",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "raw" / "_fake_ehr")
    ap.add_argument("--n-subject", type=int, default=150)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()

    rng = random.Random(a.seed)
    out = a.out
    (out / "hosp").mkdir(parents=True, exist_ok=True)
    (out / "note").mkdir(parents=True, exist_ok=True)

    patients, admissions, dxs, ddx, notes = [], [], [], [], []
    ddx_seen = set()
    hadm_id = 20000000
    for i in range(a.n_subject):
        sid = 10000000 + i
        gender = rng.choice(["M", "F"])
        age = rng.randint(21, 92)
        patients.append((sid, gender, age))
        # 25% 的病人住两次院 → 用来验证按病人切分
        n_adm = 2 if rng.random() < 0.25 else 1
        for _ in range(n_adm):
            hadm_id += 1
            admissions.append((sid, hadm_id, "2100-03-04 12:00:00"))
            code, title, course, med = rng.choice(CASES)
            chief = rng.choice(["shortness of breath", "chest pain", "abdominal pain",
                                "fatigue", "confusion", "weight loss"])
            r = rng.random()
            kind = "no_course" if r < 0.08 else ("short_course" if r < 0.18 else "full")
            notes.append((sid, hadm_id,
                          make_note(rng, age, gender, chief, course, title, med, kind)))
            dxs.append((sid, hadm_id, 1, code, 10))
            # 次要诊断（不该被当成主诊断）
            extra = rng.choice(CASES)[0]
            dxs.append((sid, hadm_id, 2, extra, 10))
            if code not in ddx_seen:
                ddx.append((code, title))
                ddx_seen.add(code)
            if extra not in ddx_seen:
                ddx.append((extra, dict((c, t) for c, t, _, _ in CASES)[extra]))
                ddx_seen.add(extra)

    def w(path: Path, header: list[str], rows: list[tuple]) -> None:
        with gzip.open(path, "wt", encoding="utf-8", newline="") as f:
            f.write(",".join(header) + "\n")
            for r in rows:
                cells = []
                for v in r:
                    # 注意：文本里的换行**必须保留**（CSV 允许引号内换行）。
                    # 早先把 \n 换成空格，导致出院小结变成一整行，
                    # extract_section() 按"标题行"切分就全部切不出来（196 条全被跳过）。
                    s = str(v).replace('"', '""')
                    cells.append(f'"{s}"' if ("," in s or '"' in s or "\n" in s) else s)
                f.write(",".join(cells) + "\n")

    w(out / "hosp" / "patients.csv.gz", ["subject_id", "gender", "anchor_age"], patients)
    w(out / "hosp" / "admissions.csv.gz", ["subject_id", "hadm_id", "admittime"], admissions)
    w(out / "hosp" / "diagnoses_icd.csv.gz",
      ["subject_id", "hadm_id", "seq_num", "icd_code", "icd_version"], dxs)
    w(out / "hosp" / "d_icd_diagnoses.csv.gz", ["icd_code", "long_title"], ddx)
    w(out / "note" / "discharge.csv.gz", ["subject_id", "hadm_id", "text"], notes)

    multi = sum(1 for s in {p[0] for p in patients}
                if sum(1 for x in admissions if x[0] == s) > 1)
    print(f"[fake] 目录 {out}")
    print(f"[fake] 病人 {len(patients)}（其中 {multi} 人有多次住院），"
          f"出院小结 {len(notes)} 份，诊断 {len(dxs)} 行")
    print("[fake] 提醒：这些是编的数据，只用于跑通流水线，不得用于任何结论。")


if __name__ == "__main__":
    main()
