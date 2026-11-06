"""sync_numbers.py —— 数字变了就把文档里的旧口径跟着改掉（机械替换，不做叙述判断）。

为什么需要它：这个项目的每一个数字都写死在各处 Markdown 里（RESULTS / README /
ALIGNMENT / ADVISOR_SUMMARY / 论文草稿 / 研制报告 …）。每跑完一批实验，上一次的口径
（比如 48.2%、−0.98、Holm 0.208）就会全部过期。靠手改必然漏。

机制：
  1. `--snapshot` 把当前从 results/*.csv 算出的关键数字存进 docs/.numbers_snapshot.json；
  2. 不带参数运行时，把"快照值 → 当前值"成对替换到文档里（同时处理 ASCII `-` 与
     Unicode `−` 两种负号），然后更新快照；
  3. 叙述性内容（"random 越界""与随机不可区分"这类判断句）脚本不改，只在末尾打印 TODO。

只替换长度 ≥ 4 的字符串，避免把 "1%"、"0.5" 这种短串误伤到无关位置；每次替换都打印
文件名与次数，便于 review。

用法：
    python tools/sync_numbers.py --snapshot   # 开跑前先存一份基线
    python tools/sync_numbers.py              # 新结果出来后同步
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
SNAP = ROOT / "docs" / ".numbers_snapshot.json"

DOCS = [
    "RESULTS.md",
    "README.md",
    "docs/ALIGNMENT.md",
    "docs/ADVISOR_SUMMARY.md",
    "docs/CLAIM_EVIDENCE.md",
    "docs/ARTIFACT_USE.md",
    "docs/PROTOCOL.md",
    "docs/PREREG_NULLBAND.md",
    "docs/NOVELTY_REVIEW.md",
    "docs/release_notes_v1.0.1.md",
    "paper/table1.md",
    "paper/results_draft.md",
    "paper/discussion_draft.md",
    "paper/abstract_draft.md",
    "paper/conclusion_draft.md",
    "paper/appendix_en.md",
    "docs/challenge_b/研制报告.md",
]


def _num(x, nd=2) -> str:
    return f"{x:.{nd}f}"


def _csv(name: str) -> pd.DataFrame | None:
    p = RESULTS / name
    if not p.exists():
        return None
    try:
        return pd.read_csv(p)
    except Exception:
        return None


def collect() -> dict[str, str]:
    """从 CSV 算出所有值得追踪的数字，返回 {key: 格式化字符串}。"""
    out: dict[str, str] = {}

    eq = _csv("eq_table.csv")
    if eq is not None:
        for _, r in eq.iterrows():
            if abs(float(r["ratio"]) - 0.30) > 1e-9:
                continue
            m, t = str(r["method"]), str(r["task"])
            if m not in ("nait", "random", "nait_ns", "rand_len", "nait_dedup", "el2n"):
                continue
            out[f"eq.{t}.{m}.delta"] = _num(r["delta_pp"])
            out[f"eq.{t}.{m}.lo"] = _num(r["ci_lo_pp"])
            out[f"eq.{t}.{m}.hi"] = _num(r["ci_hi_pp"])

    ct = _csv("eq_contrast.csv")
    if ct is not None:
        for _, r in ct.iterrows():
            if abs(float(r["ratio"]) - 0.30) > 1e-9:
                continue
            if str(r["method"]) == "nait" and str(r["vs"]) == "random":
                out[f"contrast.{r['task']}.delta"] = _num(r["delta_pp"])
                out[f"contrast.{r['task']}.p"] = _num(r["stouffer_p"], 3)

    holm = _csv("holm.csv")
    if holm is not None:
        cols = {c.lower(): c for c in holm.columns}
        pcol = cols.get("p_holm") or cols.get("holm") or cols.get("p_adj")
        if pcol:
            out["holm.max_p"] = _num(holm[pcol].max(), 3)

    comp = _csv("compute_table.csv")
    if comp is not None:
        for _, r in comp.iterrows():
            m = str(r["method"])
            if abs(float(r["ratio"]) - 1.0) < 1e-9:
                out["compute.full_h"] = _num(r["gpu_hours"])
            elif abs(float(r["ratio"]) - 0.30) < 1e-9 and m in ("nait", "random", "el2n", "nait_ns"):
                out[f"compute.{m}.h"] = _num(r["gpu_hours"])
                out[f"compute.{m}.net"] = _num(r["net_saving_pct"], 1)

    nb = _csv("nullband.csv")
    if nb is not None:
        pcol = "tost_pass" if "tost_pass" in nb.columns else None
        if pcol is not None:
            n = len(nb)
            npass = int(nb[pcol].astype(bool).sum())
            out["nullband.n"] = str(n)
            out["nullband.n_pass"] = str(npass)
        dcol = "delta_pp" if "delta_pp" in nb.columns else None
        if dcol is not None:
            s = nb[dcol].astype(float)
            out["nullband.p10"] = _num(s.quantile(0.10))
            out["nullband.p90"] = _num(s.quantile(0.90))
            out["nullband.median"] = _num(s.median())

    return out


def variants(s: str) -> set[str]:
    """同一个数字的两种负号写法。"""
    return {s, s.replace("-", "\u2212")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", action="store_true", help="只写快照，不改文档")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    cur = collect()
    print(f"collected {len(cur)} tracked numbers from results/*.csv")

    if a.snapshot or not SNAP.exists():
        SNAP.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"snapshot written: {SNAP.relative_to(ROOT)} ({len(cur)} keys)")
        return 0

    old = json.loads(SNAP.read_text(encoding="utf-8"))

    # 只替换"变了且够长"的数字，避免短串误伤
    pairs: list[tuple[str, str, str]] = []   # (key, old, new)
    for k, new in cur.items():
        o = old.get(k)
        if not o or o == new:
            continue
        if len(o) < 4 or len(new) < 4:
            continue
        pairs.append((k, o, new))

    if not pairs:
        print("nothing changed — docs already in sync")
        return 0

    print(f"{len(pairs)} number(s) changed:")
    for k, o, n in pairs:
        print(f"  {k}: {o} -> {n}")

    total = 0
    for rel in DOCS:
        p = ROOT / rel
        if not p.exists():
            continue
        txt = p.read_text(encoding="utf-8")
        orig = txt
        hits = 0
        for _, o, n in pairs:
            for ov in variants(o):
                nv = n if ov == o else n.replace("-", "\u2212")
                if ov in txt:
                    hits += txt.count(ov)
                    txt = txt.replace(ov, nv)
        if txt != orig:
            if not a.dry_run:
                p.write_text(txt, encoding="utf-8")
            print(f"  {rel}: {hits} replacement(s)")
            total += hits

    print(f"total replacements: {total}{' (dry-run)' if a.dry_run else ''}")

    if not a.dry_run:
        SNAP.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")

    print("\nTODO（脚本不改判断句，需要人改）：")
    print("  - RESULTS.md 的标题级结论：nait 与 random 是'不可区分'还是'一个越界一个没越界'")
    print("  - docs/NOVELTY_REVIEW.md 第七节（回答 DIQ 的那段）")
    print("  - docs/ADVISOR_SUMMARY.md 的'四条结论'")
    print("  - paper/abstract_draft.md / conclusion_draft.md 的主张句")
    print("  - 挑战杯研制报告：改完 md 后跑 tools/md_to_blocks.py + tools/blocks_to_docx.ps1 重生成 docx/pdf")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())