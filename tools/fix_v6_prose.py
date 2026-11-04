"""fix_v6_prose.py —— 只用短数字串替换，避免中文引号进 Python 字符串。

补跑之后 prose 里过期的数字：
  摘要 nait -0.96/-1.45、Holm 0.064、2.08/1.08 GPU-h；附录 Holm family 大小；CLAIM_EVIDENCE 的 0.064。
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (文件, 旧, 新) —— 全是数字级短串，安全可替换
RULES = [
    ("paper/abstract_draft.md", "0.96pp（95% CI [−1.77, +0.22]）", "0.98pp（95% CI [−1.57, −0.07]）"),
    ("paper/abstract_draft.md", "1.45pp（CI [−2.39, −0.53]）", "1.47pp（CI [−2.15, −0.86]）"),
    ("paper/abstract_draft.md", "p = 0.064", "p = 0.176"),
    ("paper/abstract_draft.md", "2.08 GPU-h", "2.13 GPU-h"),
    ("paper/abstract_draft.md", "1.08 GPU-h", "1.09 GPU-h"),
    ("paper/abstract_draft.md", "loses 0.96 pp", "loses 0.98 pp"),
    ("paper/abstract_draft.md", "[−1.77, +0.22]", "[−1.57, −0.07]"),
    ("paper/abstract_draft.md", "loses 1.45 pp", "loses 1.47 pp"),
    ("paper/abstract_draft.md", "[−2.39, −0.53]", "[−2.15, −0.86]"),
    ("paper/abstract_draft.md", "Holm-corrected p = 0.064", "Holm-corrected p = 0.176"),
    ("paper/abstract_draft.md", "2.08 GPU-hours", "2.13 GPU-hours"),
    ("paper/abstract_draft.md", "1.08 GPU-hours", "1.09 GPU-hours"),
    ("paper/appendix_en.md", "the four contrasts at 30% (nait and nait_ns × two tasks); corrected p = 0.064",
     "the twelve contrasts at 30% (six arm pairs × two tasks); corrected p = 0.176"),
    ("docs/CLAIM_EVIDENCE.md", "Holm 后 0.064", "Holm 后 0.176"),
]


def main() -> None:
    by_file: dict[str, list[tuple[str, str]]] = {}
    for rel, old, new in RULES:
        by_file.setdefault(rel, []).append((old, new))

    for rel, rules in by_file.items():
        p = ROOT / rel
        s = p.read_text(encoding="utf-8")
        applied = 0
        for old, new in rules:
            n = s.count(old)
            if n:
                s = s.replace(old, new)
                applied += n
                print(f"  {rel}: {old[:38]} -> {new[:38]}  x{n}")
        if applied:
            p.write_text(s, encoding="utf-8")


if __name__ == "__main__":
    main()
