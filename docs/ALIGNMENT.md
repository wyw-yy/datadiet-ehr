# 与提案（No.65 DataDiet-EHR）的逐条对照

> 更新时间 2026-10-24（第一批 19 个 run 跑完之后重写）。
> 图例：✅ 已落实并能演示 ｜ 🟡 部分（有数但样本不够/待补）｜ ⚠️ 与提案有偏离（**必须写进 limitation**）｜ ⬜ 还没做
>
> 判断标准就一条：**导师指着这一行问"证据呢"，我能不能立刻打开一个文件给他看。**

---

## 01 内容

| # | 提案要求 | 我们的实现 | 证据文件 | 状态 |
|---|---|---|---|---|
| ① | 问题：少用三成病历数据还能不能训好模型 | 全量 12,000 条 vs 子集 3,600 条（30%），同一张考卷，等效界 δ=2pp | `results/eq_table.csv`、`RESULTS.md` §1 | 🟡 结论有了，但**种子只有 3 个**，种子级判定不够（见 `docs/PREREG.md` §5，需 6 个） |
| ② | 缺口：选择协议此前不可复现 | 随机性全固定（seed=42）、层集合 {8,12,16,20,24}、阈值 0.95、所有中间量落盘、代码哈希留档 | `data/subsets/subsets.json`、`results/select_stats.json`、`audit/` | ✅ |
| ③ | 做法：基于神经元激活做子集选择 | 采 5 层隐状态 → **减池内均值** → L2 归一 → 与 probe 质心算余弦 → 按科室分层配额取满 | `collect_acts.py`、`select_subset.py`、`cache/acts/*.npz` | ✅ |
| ③ | 做法：给出可复现协议 | 10 节协议文档：输入契约、采集、去均值、打分、去重、分层、审计、参数总表、自检、放弃的选项 | `docs/PROTOCOL.md` | ✅ |
| ③ | 做法：开源实现 | 代码齐全 + 一键脚本 + 环境锁定 + 新机器部署说明；**缺 README / LICENSE** | `check_env.bat`、`run_pilots.bat`、`requirements-lock.txt`、`docs/SETUP_MACHINES.md` | 🟡 缺 `README.md` + `LICENSE` |
| ③ | 做法：测量数据削减比例 | 五档 10 / 20 / 30 / 50 / 70% 全部跑完（30% 有 3 种子，其余 1 种子） | `results/eq_table.csv`、`paper/figures/fig02_data_efficiency.png` | ✅ |
| ③ | 做法：算力节省 | 每次 run 的真实 `train_seconds`；选择前向开销 **0.13 GPU-h** 实测；每样本耗时用中位数剔污染 | `results/compute_table.csv`、`paper/figures/fig05_compute.png` | ✅ 净省 **45.9%**（不是 70%） |
| ③ | 做法：跨科室稳健性 | 6 个科室逐题结果可分；科室 n<30 跳过 | `results/robust.csv`、`paper/figures/fig04_dept.png` | 🟡 有图有表，但科室级样本小、CI 很宽（最差 onco −1.70pp，CI 跨 0） |
| ③ | 做法：跨任务稳健性 | MedMCQA（同域，4,183）＋ MedQA（跨任务，1,273） | `data/processed/medmcqa.jsonl`、`medqa.jsonl` | ✅ |
| ④ | 产出：开源协议 | 同"可复现协议" | `docs/PROTOCOL.md` | ✅ |
| ④ | 产出：数据冗余度报告 | 去重保留 **99.08%**（11,889/12,000）；随机对余弦 p50 −0.014 / p99 0.427 | `results/select_stats.json` | ✅ 结论：**这批数据几乎没有语义级近重复**，冗余不在"重复样本"上 |
| ④ | 产出：算力节省结论 | 净省 45.9%（子集训练 0.17 + 选择 0.13 / 全量 0.55） | `results/compute_table.csv` | ✅ |

---

## 02 数据

| # | 提案要求 | 我们的实现 | 证据 | 状态 |
|---|---|---|---|---|
| ① | 来源：院内电子病历（结构化与文本） | **偏离**：用公开医学题库 `MedMCQA` 的 train split 当训练池（182,822 条里抽 12,000），用其 test+valid 当考卷 | `data/raw/medmcqa-train/train.parquet` | ⚠️ **必须写 limitation**：不是院内 EMR，没有结构化生命体征/实验室值 |
| ① | （备选）公开医患问答 | `lavita/ChatDoctor-HealthCareMagic-100k` 112,165 条仍留在磁盘，作**跨域对照**（已验证：在这上面训练会让 MedQA 掉 3.8pp） | `data/raw/healthcaremagic/hcm-100k.parquet` | ✅ 作为反例证据留着 |
| ② | 单位与规模：样本单位为训练样本 | 1 条"题干+四选项→答案+解析"= 1 个训练样本；池子 12,000 条 | `data/processed/train.jsonl` | ✅ |
| ③ | 关键字段：样本激活统计 | **每样本一行**：激活得分、全池名次、百分位、是否被 10 档子集选中 | `results/sample_stats.csv`（12,000 行 × 15 列） | ✅ |
| ③ | 关键字段：被选子集 | 两个变体 × 五档比例，附 id 列表 | `data/subsets/subsets.json` | ✅ |
| ③ | 关键字段：训练数据量 | 每个 run 的 method / ratio / 实际样本数 | `results/metrics_long.csv` | ✅ |
| ③ | 关键字段：下游任务表现 | 每道题的对错 + 四个选项概率 | `results/preds/<run>_<task>.csv.gz`（19 run × 2 任务） | ✅ |
| ③ | 关键字段：训练算力 | 每次 run 秒数、GPU-hours、选择开销 | `results/compute_table.csv` | ✅ |
| ④ | 获取与合规：伦理审批与去标识化 | 公开数据不涉及院内伦理审批；但**真数据还没到手**，这条现在是"没做"而不是"不需要" | `PLAN.md` §4 | ⚠️ 需在文中声明，且别写成"已完成合规" |
| ④ | 子集选择过程须可审计 | 阈值/分位/保留率/每档规模/科室分布全落盘；另有代码哈希、产物哈希、每次选择的输入输出哈希 | `audit/{code_manifest.json,ARTIFACTS.sha256,selection_log.jsonl}`、`tools/verify.py` | ✅ |

---

## 03 模型

| # | 提案要求 | 我们的实现 | 证据 | 状态 |
|---|---|---|---|---|
| ① | 主模型：临床模型（指令微调场景） | Qwen2.5-1.5B-Instruct + LoRA SFT（1.18% 参数可训） | `train.py`、`results/runs/*.json` | ✅ |
| ② | 方法：激活基选择协议 + **等效果对照实验** | TOST 口径：80% CI 落在 ±2pp 内判等效；逐题配对 McNemar + bootstrap | `R/01_equivalence.R`、`results/eq_table.csv` | ✅ 口径已固化，但见下方"统计偏离" |
| ② | 对照 **Nait / ICLR 2026** | **偏离口径**：复现它的核心机制（域内 probe 质心 + 余弦相似度选样本），**不是**与官方实现逐步对齐（官方无可运行代码） | `select_subset.py`、`RESULTS.md` §2 | ⚠️ 论文只能写"复现其选择机制" |
| ③ | 基线：全量数据训练 | `full_s1/2/3` 三个种子 | `results/metrics_long.csv` | ✅ |
| ④ | 验证：等效果条件下的数据削减比例 | 30% 保留：逐题口径 4/4 等效（掉点 0.22–0.66pp）；种子口径 2/4 | `results/eq_table.csv` | 🟡 需 6 个种子才能下种子级结论 |
| ④ | 验证：跨任务稳健性 | MedQA（训练池是 MedMCQA）掉点 −0.31pp | `results/eq_table.csv` | ✅ |

---

## 04 临床

| # | 提案要求 | 我们的实现 | 证据 | 状态 |
|---|---|---|---|---|
| ① | 场景：临床模型训练算力预算压缩 | 单卡 8GB 笔电上把 12k 条的训练压到 0.17 GPU-h | `results/compute_table.csv` | ✅ |
| ② | 用户：模型训练团队 / 信息科 / 预算决策方 | 一句话能讲清："少看七成题，考分不掉，电费省一半" | `RESULTS.md` | 🟡 缺一页给非技术读者的摘要 |
| ③ | 用途：效果不降前提下降低数据与算力成本 | 净省 45.9%，代价是 0.13 GPU-h 的一次性选择开销 | `fig05_compute.png` | ✅ |
| ④ | 验收：同效果下训练数据削减 ≥30% | **30% 达成**（逐题口径），但"同效果"的强度取决于种子数 | `results/eq_table.csv` | 🟡 |
| ⑤ | 落地：发布开源协议与实施指南 | 协议有、脚本有、新机器部署说明有；缺 README/LICENSE 与"如何换自己的数据"教程 | `docs/PROTOCOL.md`、`docs/SETUP_MACHINES.md` | 🟡 |

---

## 五条必须写进 limitation 的偏离

1. **数据不是院内 EMR。** 用的是公开医学题库；没有结构化检验值、没有真实病历书写风格。这是最硬的一条。
2. **只做选择题，没做生成。** 评测是"读 A/B/C/D 的 logprob 取最大"，不是自由文本生成——它便宜、确定，但比真实临床问答窄得多。
3. **"优于随机"没成立。** 三个种子方向翻转（+0.55 / −0.86 / −0.02），p 全部 > 0.14。论文只能写"无可检测优势"。
4. **长度混杂。** 激活选中的样本比池子平均长 12.3%；已建长度匹配对照臂 `rand_len`（把差距压到 1.25% 以内），但**还没跑**。
5. **种子数不足。** 3 个种子下种子级 CI 半宽 2.58pp > δ=2pp，等 6 个种子重跑才能下种子级结论。

---

## 缺口清单（按优先级）

| 优先级 | 缺什么 | 谁来做 | 成本 |
|---|---|---|---|
| P0 | 补 3 个种子（跑满 6 个）＋ 跑 `rand_len` 对照臂 | 我（开机即可） | 约 6–8 GPU-h |
| P0 | `README.md` + `LICENSE`（开源落地） | 我 | 1 h |
| P1 | 真数据：PhysioNet 注册 + CITI + DUA | 用户 | 4–6 h + 1–2 周审批 |
| P1 | 主表（正文那张 Table 1） | 我 | 半天 |
| P2 | 给导师的一页非技术摘要 | 我 | 30 min |
| P2 | 生成式评测（换成"输出完整答案"再比） | 待定 | 需要额外设计 |
