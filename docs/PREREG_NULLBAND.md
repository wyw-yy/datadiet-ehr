# 预注册：随机 30% 子集的零分布（null band）

**写于 2026-11-04 18:20，在任何一个新 run 开始之前。**
目的是把"random 越界、nait 没越界"这个**单点比较**换成**分布位置**，避免"显著性差异当强弱差异"的陷阱。

## 一、要回答的问题

1. 一个典型（median）随机 30% 子集，相对全量到底掉多少？分布有多宽？
2. `nait` 的 −0.98pp 落在这条分布的哪个位置？是"比典型随机好"，还是"就是随机"？
3. 20 个随机子集里，有几个能通过我们的 ±2pp 等效检验？——**如果大多数都过，那"random 越界"只是一个坏运气样本，标题级结论必须改写。**

## 二、固定的实验设置（与既有 run 完全一致，不许调）

- 池：`data/processed/train.jsonl`，48,000 条（`DATADIET_N_POOL=48000`）
- 子集：`random.Random(seed).sample(pool, 14400)`，即 30%
- 基座：`models/Qwen2.5-1.5B-Instruct`；LoRA r=16, α=32, dropout 0.05, 7 个投影
- 训练：bf16、gradient checkpointing、`bs=4 × grad_accum=2`、`max_len=512`、**1 epoch**、OneCycleLR 1e-4
- 评测：`medmcqa`（主）+ `medqa`（次），选择题判别式、贪心、确定性
- 全量分母：`full_s1`、`full_s2`、`full_s3` 三颗种子的 acc 均值（MedMCQA 0.4682 / MedQA 0.4800）

## 三、样本与统计量

- 随机子集 **20 个**：seeds **1–20**。其中 1–6 已于 2026-11-03 完成，本次补 **7–20**。
  **20 个一起分析，不挑选、不剔除、不替换。**
- 每个种子的统计量：
  - `delta_pp = (acc_subset − acc_full_mean) × 100`
  - 逐题配对 bootstrap 95% CI（`B = 2000`，以 item 为重采样单位，`delta_i = correct_i − mean(full_1..3 的 correct_i)`）
  - 逐题 TOST：`H0: |delta| ≥ 2pp`，`alpha = 0.05`
- 分布特征：mean / sd / min / max / P10 / P50 / P90 / P2.5 / P97.5

## 四、判定规则（**跑之前定死**）

设 `P10 / P90` 为 20 个随机 `delta_pp` 的 10% / 90% 分位。

- **R1** 若 `nait` 的 delta 落在 `[P10, P90]` → 结论写 **"与随机不可区分"**，不得写"优于随机"。
- **R2** 若 `nait` 的 delta `> P90` → 可写"优于典型随机"，但仍须报 Holm 校正后的 p，且必须在讨论里说明这是分布位置而非显著性差异。
- **R3** 若 `nait` 的 delta `< P10` → 写"差于典型随机"。
- **R4** 记 `pi_pass` = 20 个随机子集中"逐题 TOST 通过"的比例，给 Clopper–Pearson 95% CI（base R `binom.test`）。
  - 若 `pi_pass ≥ 0.5` → 主线改为 **"30% 保留本身是稳健的；nait 与随机都在等效带内"**，删掉所有"nait 更好"的表述。
  - 若 `pi_pass` 很低（≤ 0.2）→ "random 越界"是可复现的，`nait` 通过就有意义，但仍以 R1–R3 为准。
- **R5** 20 个结果全部进 `results/nullband.csv`，一个都不许删。
- **R6** 同时报 `rand_len`（−0.91，长度匹配对照）与 `nait_dedup` 的位置，用于区分"长度效应"与"选择效应"。

## 五、明确不做的事

- 不调超参、不换池子、不改 δ=2pp、不改评测集。
- **不扩大多重比较家族**：家族 C 仍是 14 条对比（nait/nait_ns × 2 任务 + 已有条目）。随机种子增多只描述分布，不新增"对比"。
- 不因为是坏结果就重跑某个种子。

## 六、同一批顺手补的种子（方案 A）

| arm | 现有种子 | 补到 | run 数 |
|---|---|---|---|
| `rand_len` @30% | 1 | 1–5 | 4 |
| `nait_dedup` @30% | 1 | 1–5 | 4 |
| `el2n` @30% | 1 | 1–4 | 3 |

这三条都**不新增对比条目**（家族大小不变），只把各自的均值/CI 收窄——`rand_len` 是唯一支撑"长度不是机制"的对照，必须做实。

## 七、分析脚本与产物

- `R/08_nullband.R` → `results/nullband.csv`、`paper/figures/fig07_nullband.png`
- 复验：`report_numbers` → `make_table1` → `make_audit` → `audit_final` → `audit_runs`