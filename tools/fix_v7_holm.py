"""fix_v7_holm.py —— 加入 EL2N 两个对比后，家族 C 从 12 条涨到 14 条，Holm 0.176 -> 0.208。

只做数字级替换，避免中文引号进 Python 字符串。
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

RULES = [
    # 数字
    ("0.176", "0.208"),
    # 家族大小（中文）
    ("12 条对比", "14 条"),
    ("12 条**对比", "14 条**对比"),
    # 家族大小（英文）
    ("the twelve contrasts at 30%", "the fourteen contrasts at 30%"),
]

FILES = [
    "RESULTS.md",
    "README.md",
    "docs/ARTIFACT_USE.md",
    "docs/CLAIM_EVIDENCE.md",
    "docs/release_notes_v1.0.0.md",
    "docs/ADVISOR_SUMMARY.md",
    "paper/abstract_draft.md",
    "paper/appendix_en.md",
    "paper/discussion_draft.md",
    "paper/results_draft.md",
    "paper/table1.md",
    "docs/challenge_b/研制报告.md",
    "docs/patent/交底书_草稿.md",
]


def main() -> None:
    for rel in FILES:
        p = ROOT / rel
        if not p.exists():
            continue
        s = p.read_text(encoding="utf-8")
        before = s
        for old, new in RULES:
            if old in s:
                s = s.replace(old, new)
        if s != before:
            p.write_text(s, encoding="utf-8")
            print(f"  ✓ {rel}")


if __name__ == "__main__":
    main()
