"""update_docs_v6.py —— 48k 轮补到"全量 3 种子 + 阶梯 2 种子 + 三条对照臂"之后，
把文档里的旧数字一次性换成新口径。

为什么要有这个脚本：结果是 CSV 生成的，文档里的数字是手写的；补跑之后分母（full）
从 1 个种子变成 3 个种子，所有 Δ 都会轻微移动，靠手工找容易漏。这里做的是
**精确字符串替换**，每一条都打印命中次数，跑完再用 tools/audit_final.py 验收。

新口径（results/*.csv 为唯一真源）：
    全量 2.131 GPU-h（3 种子均值）；nait@30% 1.094（48.6%）；random 0.639（70.0%）
    medmcqa@30% nait −0.98 [−1.57,−0.07] / random −1.47 [−2.15,−0.86] / nait_ns −0.89
    medqa@30%   nait −0.04 [−1.39,+1.26] / random −0.32 [−1.70,+0.58]
    contrast    nait−random +0.50 [−0.04,+1.03] raw p=0.016 / Holm 0.176（家族 C 现有 12 条）
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGETS = [
    "RESULTS.md",
    "README.md",
    "docs/ALIGNMENT.md",
    "docs/PREREG.md",
    "docs/ADVISOR_SUMMARY.md",
    "docs/CLAIM_EVIDENCE.md",
    "docs/ARTIFACT_USE.md",
    "docs/release_notes_v1.0.0.md",
    "paper/results_draft.md",
    "paper/discussion_draft.md",
    "paper/abstract_draft.md",
    "paper/conclusion_draft.md",
    "paper/appendix_en.md",
    "paper/table1.md",
    "docs/challenge_b/研制报告.md",
]

# (旧, 新, 备注) —— 全部是数字级替换，不动句子结构
RULES = [
    ("48.2%", "48.6%", "nait 净省"),
    ("1.080", "1.094", "nait 总 GPU-h"),
    ("0.625", "0.639", "nait 训练 GPU-h"),
    ("2.082", "2.131", "全量 GPU-h（3 种子）"),
    ("Holm 0.064", "Holm 0.176", "家族 C 扩到 12 条后"),
    ("0.064（不显著）", "0.176（不显著）", "同上"),
    ("−0.96", "−0.98", "medmcqa nait@30%"),
    ("-0.96", "-0.98", "medmcqa nait@30%"),
    ("−1.45", "−1.47", "medmcqa random@30%"),
    ("-1.45", "-1.47", "medmcqa random@30%"),
    ("−0.81", "−0.89", "medmcqa nait_ns@30%"),
    ("-0.81", "-0.89", "medmcqa nait_ns@30%"),
    ("[−1.77,+0.22]", "[−1.57,−0.07]", "nait@30 CI"),
    ("[-1.77,+0.22]", "[-1.57,-0.07]", "nait@30 CI"),
    ("[−2.39,−0.53]", "[−2.15,−0.86]", "random@30 CI"),
    ("[-2.39,-0.53]", "[-2.15,-0.86]", "random@30 CI"),
    ("[−2.52,+1.26]", "[−1.39,+1.26]", "medqa nait@30 CI"),
    ("[-2.52,+1.26]", "[-1.39,+1.26]", "medqa nait@30 CI"),
    ("[−2.36,+1.18]", "[−1.70,+0.58]", "medqa random@30 CI"),
    ("[-2.36,+1.18]", "[-1.70,+0.58]", "medqa random@30 CI"),
    ("−1.04", "−1.04", "EL2N@24k 不变（占位）"),
]


def main() -> None:
    total = 0
    for rel in TARGETS:
        p = ROOT / rel
        if not p.exists():
            print(f"  - 跳过（不存在）{rel}")
            continue
        text = p.read_text(encoding="utf-8")
        orig = text
        hits = []
        for old, new, note in RULES:
            if old == new or old not in text:
                continue
            n = text.count(old)
            text = text.replace(old, new)
            hits.append(f"{old}->{new}×{n}({note})")
        if text != orig:
            p.write_text(text, encoding="utf-8")
            total += len(hits)
            print(f"  ✓ {rel}: " + "; ".join(hits))
    print(f"\n共应用 {total} 组替换；下一步跑 tools/audit_final.py 验收")


if __name__ == "__main__":
    main()
