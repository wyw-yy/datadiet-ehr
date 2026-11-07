# v1.0.1 — 文稿补齐与文档口径统一

上一版（v1.0.0）把代码、结果与审计链锁住了，但论文还缺 Abstract / Conclusion / 英文附录，
而且若干次要文档仍写着旧池子（12k / 24k）的数字。这一版只做文档，不动任何实验结果。

## 这一版改了什么

- **新增** `paper/abstract_draft.md`（中英双语摘要）、`paper/conclusion_draft.md`、
  `paper/appendix_en.md`（英文附录：六张表 + 协议参数 + 产物清单）。
- **统一口径**：`docs/PROTOCOL.md`、`docs/DATA_CARD.md`、`docs/PREREG.md`、`docs/API.md`、
  `GLOSSARY.md` 全部从 12k/24k 更新到 **48,000 条池、30% = 14,400 条、去重 97.32%**。
- **归档历史手册**：`RESUME.md`、`明天怎么跑.md`、`docs/PLAN_A_SCALE.md` 移到 `docs/archive/`，
  文件头明确标注"数字不作口径"。
- **新增审查工具** `tools/review_docs.py`：扫描文档里残留的旧口径数字、检查主文档是否含关键值、
  抽查 CSV 与文档是否一致。当前输出 **0 处残留**。
- **Table 1 加口径脚注**：池子规模、子集条数、去重率、Holm 结论一次写清。

## 结果没变

30% 保留下 nait 掉 **−0.96 pp**（CI [−1.43, +0.22]，双口径等效），random 掉 **−1.45 pp**
（CI [−2.39, −0.53]，逐题口径越界）；两者差 **+-0.18 pp**（未校正 p = 0.016，**Holm 校正 0.064，不显著**）。
全量 2.082 GPU-h，nait 方案 1.080 GPU-h（**净省 48.2%**）。

## 复现

```bash
.venv\Scripts\python.exe run_one.py --method nait --ratio 0.30 --seed 1 --epochs 1
Rscript R\run_all.R
.venv\Scripts\python.exe tools\review_docs.py
.venv\Scripts\python.exe tools\audit_final.py
```
