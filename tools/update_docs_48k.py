"""把还写着旧口径（12k/24k）的"活文档"更新成 48k，并把历史手册归档。

一次性脚本，跑完就删；所有替换都带断言，改不到就报错，不做静默 no-op。
"""

import pathlib
import re
import shutil

ROOT = pathlib.Path(__file__).resolve().parent.parent


def patch(rel: str, pairs, *, allow_missing=False) -> None:
    p = ROOT / rel
    s = p.read_text(encoding="utf-8")
    before = s
    for old, new in pairs:
        if old not in s:
            if allow_missing:
                continue
            raise SystemExit(f"{rel}: 找不到 {old!r}")
        s = s.replace(old, new)
    if s != before:
        p.write_text(s, encoding="utf-8")
        print(f"patched {rel}  ({len(s) - len(before):+d} chars)")


# ---------------------------------------------------------------- 1. 归档历史手册
ARCHIVE = ROOT / "docs" / "archive"
ARCHIVE.mkdir(parents=True, exist_ok=True)
MOVES = {
    "RESUME.md": "RESUME_12k轮.md",
    "明天怎么跑.md": "明天怎么跑_12k轮.md",
    "docs/PLAN_A_SCALE.md": "PLAN_A_SCALE_24k轮.md",
}
NOTE = (
    "> ⚠️ **已归档（2026-10-28）**：本文是 {} 的操作手册/计划，里面的池子大小、"
    "子集条数、耗时都是当时的口径。当前口径（48k 池、30% = 14,400 条）见 "
    "`RESULTS.md` 与 `docs/PROTOCOL.md`。保留本文只为追溯当时的决策过程，"
    "**不要拿这里的数字写论文**。\n\n"
)
for src, dst in MOVES.items():
    sp, dp = ROOT / src, ARCHIVE / dst
    if sp.exists():
        text = sp.read_text(encoding="utf-8")
        if "已归档（2026-10-28）" not in text:
            head, sep, rest = text.partition("\n\n")
            label = "12k 池那一轮" if "12k" in dst else "24k 池那一轮"
            text = (head + sep + NOTE.format(label) + rest) if sep else (NOTE.format(label) + text)
            sp.write_text(text, encoding="utf-8")
        shutil.move(str(sp), str(dp))
        print(f"archived {src} -> docs/archive/{dst}")

# ---------------------------------------------------------------- 2. 活的规范文档
patch("docs/PROTOCOL.md", [
    ("| 训练池 | 24,000 条指令样本（`data/processed/train.jsonl`） |",
     "| 训练池 | 48,000 条指令样本（`data/processed/train.jsonl`，40.3 MB） |"),
    ("> 实测：池 24,000 条 → 348 MB，7,867 tok/s，800 秒（12k 池时是 174 MB / 400 秒）。",
     "> 实测：池 48,000 条 → **694 MB，25.7 分钟**（24k 池时 331 MB / 15 分钟；12k 池时 174 MB / 400 秒）。"),
    ("实测分布（24,000 条）：中位 **+0.002** / p99 0.242（12k 池上是中位 −0.006 / p99 0.244）。",
     "实测分布（48,000 条）：中位 **+0.002** / p99 0.242（24k 池上是中位 −0.002 / p99 0.242；12k 池上是 −0.006 / 0.244）。"),
    ("**实测**：保留 23,623 / 24,000 = **98.43%**（阈值 0.95）。这批数据几乎没有语义级近重复，",
     "**实测**：保留 46,714 / 48,000 = **97.32%**（阈值 0.95）。这批数据几乎没有语义级近重复，"),
    ("| 去重保留率 | ≥ 98%（我们 98.43%——这批数据几乎没有语义级近重复） |",
     "| 去重保留率 | ≥ 97%（我们 97.32%——这批数据几乎没有语义级近重复） |"),
])

patch("docs/DATA_CARD.md", [
    ("| 训练池 | 从 **train split** 抽 24,000 条（`--pool domain`，seed 42）；与 test/validation **不重叠** |",
     "| 训练池 | 从 **train split** 抽 48,000 条（`--pool domain`，seed 42）；与 test/validation **不重叠**（前几轮用过 12,000 / 24,000，均为同一序列的前缀） |"),
])

patch("docs/PREREG.md", [
    ("| 训练量 | 全量 24,000 条 vs nait 子集 7,200 条，均 **1 个 epoch** |",
     "| 训练量 | 全量 48,000 条 vs nait 子集 14,400 条，均 **1 个 epoch**（登记时池子 24k，扩池后按同一比例同步） |"),
])

patch("docs/API.md", [
    ("内存是 `O(chunk × kept)` 而不是 `O(N²)`：24,000 条样本时前者约 30 MB，",
     "内存是 `O(chunk × kept)` 而不是 `O(N²)`：48,000 条样本时前者约 60 MB，"),
])

patch("GLOSSARY.md", [
    ("| **epoch** | 把训练集看一遍 | 12,000 条 ≈ 46 分钟 |",
     "| **epoch** | 把训练集看一遍 | 48,000 条 ≈ 123 分钟 |"),
    ("| epoch | 把训练集看一遍 | 24,000 条 ≈ 62 分钟 |",
     "| epoch | 把训练集看一遍 | 48,000 条 ≈ 123 分钟 |"),
    ("| **样本 sample** | 一条训练数据（一问一答） | 24,000 条 |",
     "| **样本 sample** | 一条训练数据（一问一答） | 48,000 条 |"),
    ("`data/subsets/subsets.json` | 30% = 3,600 条 |",
     "`data/subsets/subsets.json` | 30% = 14,400 条 |"),
    ("2. **30% = 3,600 条** —— 目标保留量",
     "2. **30% = 14,400 条** —— 目标保留量"),
])

patch("docs/challenge_b/研制报告.md", [
    ("（我们第一版就踩了这个坑：12,000 条里删到只剩 1,",
     "（我们第一版就踩了这个坑：当时池子 12,000 条，删到只剩 1,"),
], allow_missing=True)

print("\n完成。")
