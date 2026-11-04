"""fix_medqa_claims.py —— 全量补到 3 个种子后，MedQA 上两臂都通过等效判据了。

旧说法"MedQA 两臂都判不了"已不准确：现在 nait −0.04、random −0.32，逐题与种子口径都过；
但那边只有 1,273 题、逐题 CI 半宽 ±1.3pp，宽到不能当独立证据。这里把两处旧说法改掉。
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

EDITS = [
    (
        "paper/results_draft.md",
        '2. **MedQA（跨任务）上两臂都判不了**：只有 1,273 题，逐题 CI 半宽 ±1.9 pp，比等效界还宽。',
        '2. **MedQA（跨任务）两臂都过，但不算证据**：nait −0.04、random −0.32，逐题与种子口径都过；'
        '但那里只有 1,273 题、逐题 CI 半宽 ±1.3 pp，宽到判不了，只能当「没有反证」。',
    ),
    (
        "paper/conclusion_draft.md",
        '跨任务（MedQA）上两臂都因题目少而判不了，别拿它下结论。',
        '跨任务（MedQA）上两臂都过（−0.04 / −0.32），但只有 1,273 道题、CI 宽到 ±1.3 pp，别拿它当独立证据。',
    ),
]


def main() -> None:
    for rel, old, new in EDITS:
        p = ROOT / rel
        s = p.read_text(encoding="utf-8")
        if old not in s:
            print(f"  - 跳过（原文没找到）：{rel}")
            continue
        p.write_text(s.replace(old, new), encoding="utf-8")
        print(f"  ✓ {rel}")


if __name__ == "__main__":
    main()
