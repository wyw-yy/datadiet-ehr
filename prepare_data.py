"""Normalise the raw downloads into the JSONL contract every later stage uses.

Input  (whatever the HF snapshot produced, parquet/json/csv all fine):
    data/raw/healthcaremagic/   -> training pool   (question / answer)
    data/raw/medqa/             -> eval set        (USMLE 4-option)
    data/raw/medmcqa/           -> eval set        (21 subjects, 4-option)

Output:
    data/processed/train.jsonl   {id, dept, instruction, response}
    data/processed/probe.jsonl   same, held out — used only to build centroids
    data/processed/medqa.jsonl   {id, dept, question, options[4], answer}
    data/processed/medmcqa.jsonl {id, dept, question, options[4], answer}
    data/processed/manifest.json counts + dept distribution + source files

Why a probe split: Nait's activation features are extracted from *in-domain*
data. The probe set must never be seen in training, otherwise the centroid is
contaminated by the very samples we then select.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import random
import re
import sys
from collections import Counter

import pandas as pd

import config as C

# ------------------------------------------------------------------ column names
Q_KEYS = ["question", "Question", "instruction", "prompt", "input", "patient", "text"]
A_KEYS = ["answer", "Answer", "output", "response", "doctor", "completion"]

# ------------------------------------------------------------------- dept taxonomy
DEPT_RULES = {
    "cardio": r"heart|cardiac|cardio|chest pain|blood pressure|hypertens|arrhythm|palpitat|cholesterol|angina|stroke",
    "onco":   r"cancer|tumor|tumour|chemotherap|carcinoma|malignan|oncolog|lymphoma|leukemia|metasta",
    "neuro":  r"headache|migraine|seizure|epilep|brain|nerve|memory|dementia|anxiety|depress|sleep|dizz|numb",
    "resp":   r"cough|asthma|breath|lung|pneumon|bronch|wheez|sputum|smok|tubercul|sinus",
    "endo":   r"diabet|thyroid|sugar|insulin|hormone|metaboli|obes|weight|menstrua|pregnan",
}
# medmcqa subject_name -> dept (its 21 official subjects)
SUBJECT_DEPT = {
    "Medicine": "cardio", "Physiology": "resp", "Biochemistry": "endo",
    "Pathology": "onco", "Pharmacology": "other", "Microbiology": "other",
    "Anatomy": "neuro", "Forensic Medicine": "other",
    "Social & Preventive Medicine": "other", "Surgery": "other",
    "Pediatrics": "other", "Obstetrics & Gynaecology": "endo",
    "ENT": "resp", "Ophthalmology": "other", "Orthopaedics": "other",
    "Anaesthesia": "other", "Radiology": "other", "Psychiatry": "neuro",
    "Dermatology": "other", "Dentistry": "other", "Unknown": "other",
}


def dept_of(text: str) -> str:
    t = (text or "").lower()
    for d, pat in DEPT_RULES.items():
        if re.search(pat, t):
            return d
    return "other"


def norm_key(text: str) -> str:
    """Coarse key for exact-duplicate removal (case/punct/space insensitive)."""
    t = re.sub(r"[^a-z0-9\u4e00-\u9fff ]+", " ", (text or "").lower())
    return re.sub(r"\s+", " ", t).strip()


def load_any(folder: str) -> pd.DataFrame | None:
    """Read every parquet/json/jsonl/csv under a raw folder into one frame."""
    files = []
    for ext in ("*.parquet", "*.json", "*.jsonl", "*.csv"):
        files += glob.glob(os.path.join(folder, "**", ext), recursive=True)
    if not files:
        return None
    frames = []
    for f in sorted(files):
        try:
            if f.endswith(".parquet"):
                frames.append(pd.read_parquet(f))
            elif f.endswith(".csv"):
                frames.append(pd.read_csv(f))
            elif f.endswith(".jsonl"):
                frames.append(pd.read_json(f, lines=True))
            else:
                frames.append(pd.read_json(f, lines=True))
        except Exception as e:                       # noqa: BLE001
            print(f"  [skip] {os.path.basename(f)}: {type(e).__name__}")
    if not frames:
        return None
    df = pd.concat(frames, ignore_index=True)
    print(f"  {os.path.basename(folder)}: {len(df)} rows from {len(frames)} file(s), "
          f"columns={list(df.columns)[:12]}")
    return df


def pick_col(df, keys):
    for k in keys:
        if k in df.columns:
            return k
    return None


# --------------------------------------------------------------------- builders
def build_train_pool(raw: pd.DataFrame, n_train: int, n_probe: int, seed: int):
    qc, ac = pick_col(raw, Q_KEYS), pick_col(raw, A_KEYS)
    if not qc or not ac:
        sys.exit(f"[prepare] cannot find question/answer columns in {list(raw.columns)}")

    # ChatDoctor-style rows carry the boilerplate role prompt in `instruction`
    # and the actual patient description in `input` — the description is what we
    # want to train on (and classify by department).
    if qc == "instruction" and "input" in raw.columns:
        filled = raw["input"].astype(str).str.strip()
        if (filled.str.len() > 20).mean() > 0.5:
            raw = raw.copy()
            raw["_q"] = filled.where(filled.str.len() > 20, raw["instruction"].astype(str))
            qc = "_q"
            print("  using `input` (patient description) as the question column")

    seen, rows = set(), []
    for q, a in zip(raw[qc].astype(str), raw[ac].astype(str)):
        q, a = q.strip(), a.strip()
        if len(q) < 15 or len(a) < 15 or len(q) > 2000 or len(a) > 4000:
            continue
        k = norm_key(q) + "|" + norm_key(a)[:120]
        if k in seen:
            continue
        seen.add(k)
        rows.append({"dept": dept_of(q), "instruction": q, "response": a})

    print(f"  kept {len(rows)} after length filter + exact dedupe "
          f"(from {len(raw)})")
    if len(rows) < n_train + n_probe:
        sys.exit(f"[prepare] need {n_train + n_probe} usable rows, only {len(rows)} — "
                 f"lower N_TRAIN in config.py or add more raw data")

    random.Random(seed).shuffle(rows)
    probe = rows[:n_probe]
    train = rows[n_probe : n_probe + n_train]
    for i, r in enumerate(train):
        r["id"] = f"t{i:05d}"
    for i, r in enumerate(probe):
        r["id"] = f"p{i:05d}"
    return train, probe


def build_choice_eval(raw: pd.DataFrame, name: str):
    qc = pick_col(raw, ["question", "Question", "prompt"])
    if qc is None:
        sys.exit(f"[prepare] {name}: no question column in {list(raw.columns)}")

    def opt_row(r):
        if "options" in raw.columns and isinstance(r["options"], dict):
            opts = r["options"]
            order = sorted(opts.keys())
            texts = [(opts[k]["text"] if isinstance(opts[k], dict) else str(opts[k]))
                     for k in order]
            letters = order
        else:
            letters, texts = [], []
            for k in ("opa", "opb", "opc", "opd"):
                if k in raw.columns:
                    letters.append(k[-1].upper())
                    texts.append(str(r[k]))
        return letters, texts

    out = []
    for i, (_, r) in enumerate(raw.iterrows()):
        letters, texts = opt_row(r)
        if len(texts) != 4:
            continue
        if "cop" in raw.columns:                        # medmcqa: 0..3, -1 = no answer
            try:
                ans = int(r["cop"])
            except (TypeError, ValueError):
                continue
            if not 0 <= ans <= 3:
                continue
        elif "answer_idx" in raw.columns:               # medqa: "A".."D"
            try:
                ans = letters.index(str(r["answer_idx"]).strip().upper())
            except ValueError:
                continue
        elif "answer" in raw.columns:                   # medqa alt: full text
            txt = str(r["answer"]).strip()
            if txt not in texts:
                continue
            ans = texts.index(txt)
        else:
            continue

        subj = str(r.get("subject_name", "")).strip()
        out.append({
            # medqa -> qa..., medmcqa -> mc...: ids must never collide across tasks
            "id": f"{'qa' if name == 'medqa' else 'mc'}{i:05d}",
            "dept": SUBJECT_DEPT.get(subj, dept_of(r[qc])),
            "question": str(r[qc]).strip(),
            "options": [t.strip() for t in texts],
            "answer": int(ans),
        })
    print(f"  {name}: {len(out)} usable items")
    return out


def build_domain_probe(raw: pd.DataFrame, n: int, seed: int):
    """Target-domain reference set for the activation centroid.

    This is the "in-domain data" Nait uses to define *what a good sample looks
    like*: text from the task family we will be evaluated on (medical
    multiple-choice QA), NOT from the training domain (patient chat). Same
    shape as train.jsonl (instruction/response) so collect_acts.py can reuse
    the exact same pooling code; the rows are never trained on.
    """
    rng = random.Random(seed)
    qc = pick_col(raw, ["question", "Question", "prompt"])
    if qc is None:
        sys.exit(f"[prepare] domain probe: no question column in {list(raw.columns)}")

    rows = []
    for _, r in raw.iterrows():
        try:
            cop = int(r.get("cop", -1))
        except (TypeError, ValueError):
            continue
        if not 0 <= cop <= 3:
            continue
        exp = str(r.get("exp", "") or "").strip()
        if len(exp) < 20:
            continue
        opts = [str(r.get("opa", "")).strip(), str(r.get("opb", "")).strip(),
                str(r.get("opc", "")).strip(), str(r.get("opd", "")).strip()]
        if not all(opts):
            continue
        instr = (f"{str(r[qc]).strip()}\n"
                 + "\n".join(f"{L}) {t}" for L, t in zip("ABCD", opts)))
        rows.append({
            "id": f"dp{len(rows):05d}",
            "dept": SUBJECT_DEPT.get(str(r.get("subject_name", "")).strip(),
                                    dept_of(str(r[qc]))),
            "instruction": instr,
            "response": exp,
        })
    rng.shuffle(rows)
    rows = rows[:n]
    rows.sort(key=lambda x: x["id"])
    print(f"  domain probe: {len(rows)} items from target-domain QA")
    return rows


def build_domain_train_pool(raw: pd.DataFrame, n_train: int, n_probe: int, seed: int):
    """Training pool built from the TARGET domain (medical MCQ with explanations).

    Why this exists: with ChatDoctor rows as the pool, supervised fine-tuning
    *lowered* MedQA accuracy (0.4776 base -> 0.4399 after 12k rows), because the
    chat-style answers teach the model to write "you should see a doctor", not
    to pick A/B/C/D. When fine-tuning hurts regardless of data volume, there is
    nothing for a data-selection method to show. So the pool has to live in the
    same domain as the evaluation tasks.

    Response format starts with the answer letter, matching eval.py, which
    scores the logprobs of " A".." D" at the first assistant token.
    """
    qc = pick_col(raw, ["question", "Question", "prompt"])
    if qc is None:
        sys.exit(f"[prepare] domain pool: no question column in {list(raw.columns)}")

    seen, rows = set(), []
    for _, r in raw.iterrows():
        try:
            cop = int(r.get("cop", -1))
        except (TypeError, ValueError):
            continue
        if not 0 <= cop <= 3:
            continue
        q = str(r[qc]).strip()
        exp = str(r.get("exp", "") or "").strip()
        opts = [str(r.get("opa", "")).strip(), str(r.get("opb", "")).strip(),
                str(r.get("opc", "")).strip(), str(r.get("opd", "")).strip()]
        if len(q) < 15 or not all(opts) or len(exp) < 20:
            continue
        k = norm_key(q)
        if k in seen:
            continue
        seen.add(k)
        instr = q + "\n" + "\n".join(f"{L}) {t}" for L, t in zip("ABCD", opts))
        rows.append({
            "dept": SUBJECT_DEPT.get(str(r.get("subject_name", "")).strip(), dept_of(q)),
            "instruction": instr,
            "response": f"{'ABCD'[cop]}. {exp}",
            "answer": int(cop),
            "subject": str(r.get("subject_name", "")).strip(),
        })

    print(f"  kept {len(rows)} usable MCQ rows (from {len(raw)})")
    if len(rows) < n_train + n_probe:
        sys.exit(f"[prepare] need {n_train + n_probe} rows, only {len(rows)}")

    random.Random(seed).shuffle(rows)
    probe = rows[:n_probe]
    train = rows[n_probe : n_probe + n_train]
    for i, r in enumerate(train):
        r["id"] = f"d{i:05d}"
    for i, r in enumerate(probe):
        r["id"] = f"pd{i:05d}"
    return train, probe


def write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"  wrote {path}  ({len(rows)} rows, {path.stat().st_size / 1e6:.1f} MB)")


def main(seed=42, pool="domain"):
    C.ensure_dirs()
    dom = load_any(str(C.RAW / "medmcqa-train"))

    if pool == "domain":
        if dom is None:
            sys.exit("[prepare] data/raw/medmcqa-train missing - download it first")
        print("[prepare] medmcqa train split -> in-domain training pool + probe")
        train, probe = build_domain_train_pool(dom, C.N_TRAIN, C.N_PROBE, seed)
    else:
        print("[prepare] healthcaremagic -> training pool (cross-domain arm)")
        hcm = load_any(str(C.RAW / "healthcaremagic"))
        if hcm is None:
            sys.exit("[prepare] data/raw/healthcaremagic is empty - download it first")
        train, probe = build_train_pool(hcm, C.N_TRAIN, C.N_PROBE, seed)

    write_jsonl(C.PROC / "train.jsonl", train)
    write_jsonl(C.PROC / "probe.jsonl", probe)

    for name in ("medqa", "medmcqa"):
        print(f"[prepare] {name} -> eval set")
        raw = load_any(str(C.RAW / name))
        if raw is None:
            print(f"  [warn] data/raw/{name} missing, skipping this eval task")
            continue
        write_jsonl(C.PROC / f"{name}.jsonl", build_choice_eval(raw, name))

    # Source-domain probe (held-out patient chat). Only meaningful when the pool
    # is ChatDoctor; kept so the cross-domain arm stays reproducible.
    if dom is not None and pool == "hcm":
        print("[prepare] medmcqa train split -> extra domain probe")
        write_jsonl(C.PROC / "probe_domain.jsonl", build_domain_probe(dom, C.N_PROBE, seed))

    manifest = {
        "pool": pool,
        "n_train": len(train),
        "n_probe": len(probe),
        "dept_train": dict(Counter(r["dept"] for r in train)),
        "dept_probe": dict(Counter(r["dept"] for r in probe)),
        "sha_train": hashlib.sha256(
            open(C.PROC / "train.jsonl", "rb").read()).hexdigest()[:16],
    }
    with open(C.PROC / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print("[prepare] dept distribution (train):", manifest["dept_train"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--pool", default="domain", choices=["domain", "hcm"],
                    help="domain = medical MCQ (in-domain, the default); "
                         "hcm = ChatDoctor patient chat (cross-domain arm)")
    a = ap.parse_args()
    main(a.seed, a.pool)
