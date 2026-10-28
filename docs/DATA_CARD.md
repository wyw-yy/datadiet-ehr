# 数据卡（Data Card）

本仓库**不含任何院内电子病历，也不含任何可识别个人身份的信息（PHI）**。
下面每一份数据都能追溯到公开来源，各自的许可与使用条件写在表里。

最后更新：2026-10-25

---

## 1. 当前主线：MedMCQA（训练池 + 同域评测）

| 项 | 内容 |
|---|---|
| 来源 | `openlifescienceai/medmcqa`（HuggingFace Datasets），源自 AIIMS 医学入学考试题库 |
| 许可 | MIT（数据集卡片声明） |
| 我们用到的文件 | `data/raw/medmcqa-train/train.parquet`（182,822 行，85.9 MB）、`data/raw/medmcqa/data/{test,validation}-00000-of-00001.parquet`（10,333 行，2.3 MB） |
| 字段 | `id, question, opa..opd, cop, choice_type, exp, subject_name, topic_name` |
| 训练池 | 从 **train split** 抽 48,000 条（`--pool domain`，seed 42）；与 test/validation **不重叠**（前几轮用过 12,000 / 24,000，均为同一序列的前缀） |
| probe | 同一次抽样里的 2,000 条，**不参与训练**，只用来定义"目标域的平均激活长什么样" |
| 评测 | test+validation 里 `0 <= cop <= 3` 的 **4,183** 条（丢弃 `cop=-1` 的无答案题） |
| 科室标签 | `subject_name` 21 个取值 → 六桶（`cardio/onco/neuro/resp/endo/other`），映射表在 `prepare_data.py` 的 `SUBJECT_DEPT` |
| 已知问题 | ① 评测集里有 20 组重复题干（40 题，0.96%），未剔除，但影响可忽略；② 答案分布轻微偏斜（A 32.2% / B 25.9% / C 22.1% / D 19.7%）；③ 评测集 `other` 占比 66%，训练池 57% —— 分布不完全对齐 |
| 泄漏检查 | `tools/check_leak.py`：评测与训练池题干重叠 1 条（`medmcqa`），`medqa` 0 条，train/probe 6 条（去重口径放过，已记录） |

## 2. 跨任务评测：MedQA（USMLE Step 1）

| 项 | 内容 |
|---|---|
| 来源 | `GBaker/MedQA-USMLE-4-options`（HuggingFace），文件 `phrases_no_exclude_test.jsonl` |
| 许可 | 依原数据集卡片；仅用于学术评测 |
| 规模 | 1,273 条，2.1 MB |
| 字段 | `question, answer, options{A..D}, meta_info="step1", answer_idx`（字母） |
| 用途 | **跨任务迁移**：模型从 MedMCQA 训练池学，考 MedQA。不作为主终点 |
| 已知问题 | 与训练池领域相近但题型不同（USMLE 题干更长、情景更复杂），所以掉点比 MedMCQA 大方差更大 |

## 3. 已弃用（留作跨域对照）：HealthCareMagic-100k

| 项 | 内容 |
|---|---|
| 来源 | `lavita/ChatDoctor-HealthCareMagic-100k`，112,165 条真实医患问答 |
| 许可 | 依原数据集卡片（源自公开网页问答，已由发布方清洗） |
| 为什么弃用 | **训练域不对**：这是患者口语问诊，模型学到的是"你该去看医生"，不是"选 A/B/C/D"。实测 base 1.5B MedQA 0.4776 → 用它 SFT 后 **0.4399（掉 3.8pp）** |
| 现在怎么用 | 作为"训练域错配会掉多少"的对照臂数据；结果归档在 `results_round1_12k/` |
| 注意 | 早期 R 侧用的**合成假数据**已单独归档到 `results/_archive_demo_synthetic/`，标注"不得引用" |

## 4. 计划中（尚未获取）：MIMIC-IV + MIMIC-IV-Note

| 项 | 内容 |
|---|---|
| 来源 | PhysioNet，需注册 + CITI 培训 + DUA（PI 必须是导师） |
| 许可 | PhysioNet Credentialed Health Data License；**不得再分发** |
| 计划用法 | `prepare_mimic.py`：`instruction` = 患者背景（年龄/性别/主诉/主诊断）+ "写出住院经过这一节"；`response` = 出院小结的 `Brief Hospital Course` 原文；`dept` = 主诊断 ICD-10 章节 → 六桶 |
| 切分 | **按 `subject_id`**，同一个人绝不跨集合；切分清单落 `processed_mimic/mimic_split.json` |
| 评测口径 | 参考文本生成（ROUGE / BERTScore）+ 人工抽检 300 条，**不是**四选一准确率 |
| 合规红线 | 派生产物只留本机、**不入库**（`.gitignore` 已有 `data/processed_mimic/`）、不上传、不出院；论文只报聚合统计 |
| 演练状态 | 已用合成"假病历"端到端跑通（`tools/rehearse_ehr.py`，六组检查全绿） |

## 5. 合成数据（仅测试用，不是数据集）

| 文件 | 用途 | 是否可引用 |
|---|---|---|
| `tools/make_fake_ehr.py` 生成的 `data/raw/_fake_ehr/` | 演练 MIMIC 流水线（章节切分、按病人切分、去标识化、ICD→科室） | ❌ 编的，不得用于任何结论 |
| `results/_archive_demo_synthetic/` | 早期 R 分析层的假数据 | ❌ 已归档并标注 |

---

## 许可与再分发

- 代码：MIT（见 `LICENSE`）
- 数据：**不随本仓库分发**。使用者需自行遵守各自数据集的许可；MIMIC 另有 DUA 约束。
- 本仓库的 `results/preds/` 只包含模型对公开题库的预测（题目 ID + 选项 + 是否正确），不含原文以外的敏感信息。

## 变更记录

- 2026-10-25：新增本文件；补 `mimic_split.json` 与逐样本 `row_subject` 映射（用于证明病人级切分）。
