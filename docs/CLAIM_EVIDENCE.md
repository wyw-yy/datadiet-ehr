# 主张 ↔ 证据对照表

每一行都要能指到一个**具体文件的具体列**。指不到的，就是还不能写进论文的主张。
状态只有三种：✅ 支持 / ⚠️ 部分支持（写的时候必须带限定语）/ ❌ 不支持（不许写）。

生成这些数字的脚本：`tools/report_numbers.py`、`tools/make_table1.py`、`R/run_all.R`。
核对脚本：`tools/audit_final.py`（会检查文档里的数字能否在这几张表里找到）。

---

## 1. 主终点：30% 数据等效

**主张**：把训练池砍到 30%，在 MedQA 与 MedMCQA 上效果等效（界 δ = 2pp）。

| 证据 | 位置 |
|---|---|
| 8 行等效性表 | `results/eq_table.csv`（列 `delta_pp` / `ci_lo_pp` / `ci_hi_pp` / `equiv_item` / `equiv_seed`） |
| 逐种子 32 行 | `results/eq_per_seed.csv` |
| 论文表 | `paper/table1.md` Table 1 |
| 图 | `paper/figures/fig02_data_efficiency.png`、`fig06_forest.png` |

状态：**✅ 8 行里 7 行双口径等效（nait / random / rand_len 三个臂在 6 个种子下全部通过；el2n 两项不通过）。**
写法要求：必须两个口径都报（`docs/PREREG.md` §3.3）。只报逐题口径等于藏起一半事实。

---

## 2. 激活选择优于随机

**主张**：nait（激活选择）比随机挑选更好。

| 证据 | 位置 |
|---|---|
| 方法对比 6 行（30%） | `results/eq_contrast.csv`（列 `delta_pp` / `ci_lo_pp` / `ci_hi_pp` / `stouffer_p`） |
| Holm 校正 | `results/holm.csv`（列 `stouffer_p` / `p_holm` / `sig_holm`） |
| 逐种子符号 | `eq_contrast.csv` 的 `per_seed_pp`；图 `fig06_forest.png` |

状态：**❌ 不支持。**
- MedQA：nait − random = +0.00pp（p = 0.979）
- MedMCQA：nait − random = +0.50pp（未校正 p = 0.016，Holm 后 0.064，不显著；符号 5/6 正）
- 6 个种子里符号来回翻（见 `fig06_forest.png` 的散点）

**不许写**"优于随机"、"显著更好"、"选择算法有效"。**可以写**"无可检测优势（no detectable advantage）"，
并给出"为什么没测出来"的三条解释：种子噪声 ~1pp、池子冗余厚、1 epoch 训练不足。

---

## 3. 算力净省

**主张**：30% 子集把训练算力省下来。

| 证据 | 位置 |
|---|---|
| 算力表（含选择前向） | `results/compute_table.csv`（列 `train_h` / `select_h` / `gpu_hours` / `net_saving_pct`） |
| 选择开销实测值 | `results/select_overhead.json`（collect_acts 两遍 + 打分 480 s） |
| 论文表 | `paper/table1.md` Table 3（归一化列 + 墙钟列） |
| 图 | `paper/figures/fig05_compute.png` |

状态：**✅ 归一化口径 45.2%；墙钟口径 40.8%。**
**不许写**"省 70%"——70% 是 random/rand_len 的数字，它们不付选择开销。
也不许写"省 45%" 而不说明这是**净**节省（已扣掉选择前向）。

---

## 4. 长度混杂已排除

**主张**：nait 的收益不是"它偏爱长文本"造成的。

| 证据 | 位置 |
|---|---|
| 长度匹配对照臂 | `data/subsets/subsets_randlen.json`、`results/select_stats_randlen.json`（`len_diff_pct` < 2%） |
| 对比 | `results/eq_contrast.csv` 中 `nait - rand_len` 行 |

状态：**⚠️ 2026-10-25 更新：24k 轮不成立。**
- 12k 轮曾看到 nait 比长度匹配对照高 +1.13pp（6/6 同号，p = 0.001）→ **24k 轮没复现，已按预注册判据作废**（见 `docs/ALIGNMENT.md` 的"撤回"段）。
- 24k 轮：nait − rand_len = +0.29pp（MedQA，p = 0.568）、−0.42pp（MedMCQA，p = 0.103）。
- 但**混杂本身是真的**：nait 选中的样本比其余长 38.8%（24k 池），同条数训练墙钟多 16%。不能声称"长度无关"，只能说"长度匹配后结论不变"。

---

## 5. 跨科室稳健性

**主张**：等效性不是靠某个科室撑起来的。

| 证据 | 位置 |
|---|---|
| 科室表 | `results/robust.csv`（列 `delta_pp` / `ci_lo_pp` / `ci_hi_pp`，科室 n < 30 已跳过） |
| 图 | `paper/figures/fig04_dept.png` |

状态：**⚠️ 部分支持。** 最差科室 onco −3.55pp（CI [−8.51, +0.71]），CI 宽到无法判断；
科室级样本量太小，只能当作方向性参考，不能当作"每个科室都等效"的证据。

---

## 6. 可复现 / 可审计

**主张**：协议可复现，每一份数字都能追到产物。

| 证据 | 位置 |
|---|---|
| 协议 | `docs/PROTOCOL.md`（含参数总表、自检 4 条） |
| 预注册 | `docs/PREREG.md`（含偏离记录 4 条 + 事后补充 1 条） |
| 代码清单 | `audit/code_manifest.json`（每个 .py/.R 的 sha256） |
| 产物哈希 | `audit/ARTIFACTS.sha256` |
| 选择日志 | `audit/selection_log.jsonl`（每方法每比例一条，含子集哈希与科室分布） |
| 自检 | `tools/verify.py`（93 项）、`tools/audit_final.py`（6 段） |

状态：**✅。** 但注意 `verify.py` 的原话：*"没有发现硬伤，这不等于结论正确"*。

---

## 7. 数据来源

**主张**：用的是真实公开数据（不是编的），且不含院内病历。

| 证据 | 位置 |
|---|---|
| 数据卡 | `docs/DATA_CARD.md` |
| 原始文件与行数 | `data/raw/`（MedMCQA train 85.9 MB、MedQA 2.1 MB），`data/processed/manifest.json` |
| 泄漏检查 | `tools/check_leak.py` 输出：medqa 0/1273、medmcqa 1/4183、probe 6/2000 |

状态：**⚠️ 部分支持。** 是真实公开数据，**但不是提案里写的院内 EMR**。
提案对齐情况见 `docs/ALIGNMENT.md`，limitation 必须写"外部有效性受限"。

## 七、查新后新增的禁区（2026-11-02，见 docs/NOVELTY_REVIEW.md）

- ❌ **不许写"首个/首次在医学领域做数据子集选择"**：DIQ（CVPR 2026，arXiv:2508.01450）已报"1% 选数据追平全量、10% 超基线"；RSP（arXiv:2610.33440）已在医学 QA 上报选择优于随机。
- ❌ **不许写"我们提出了一种新的激活式选择方法"**：Nait（ICLR 2026）、NeurIPS 2025（SAE 解耦多义神经元）、TRACE（AAAI-40）已占满这条方法轴。
- ❌ **不许写"我们解决了激活的多义性/伪相似问题"**：NeurIPS 2025 用 SAE 做这件事；我们的均值校正只能写成"一个更便宜的替代方案"。
- ✅ 可以写：可判定的等效性评测协议（TOST + 双口径 + 预注册 + Holm）、把选择前向计入的算力净账（nait 48.6% vs EL2N 10.8%）、机制解释（引用样式 52.7% vs 27.9%、长度差 38.8%）、以及"砍多少比换哪个选择器更重要"（48k：random 越界、nait 在界内）。
