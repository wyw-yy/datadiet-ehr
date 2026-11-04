# Abstract（草稿）

## 中文摘要

**背景与问题**：临床文本模型（指令微调的 LLM）的训练成本主要花在样本量上。领域里普遍相信"病历里冗余很多，砍掉一大半也能训出同样的模型"，但"砍多少、怎么砍、砍完算力到底省没省"缺少可复现的协议与诚实的核算。

**方法**：我们在公开医学问答数据上构建了一个同域训练池（MedMCQA train split 抽 48,000 条），以 Qwen2.5-1.5B-Instruct 为基座做 LoRA 指令微调，比较四种取 30% 子集的策略：激活相似度选择（nait，复现 Nait/ICLR 2026 的机制）、长度匹配随机（rand_len）、朴素随机（random）、以及经典基线 EL2N。评估用 MedMCQA（同域，4,183 题）与 MedQA（跨任务，1,273 题），主终点锁定 30% 保留率，等效界 δ = 2pp 在实验前写死，采用逐题配对 McNemar + TOST + 逐种子 Stouffer 合并，并对方法对比做 Holm 校正。

**结果**：在 6 个种子下，激活选择的 30% 子集相对全量掉 0.96pp（95% CI [−1.77, +0.22]），逐题与逐种子双口径均落在等效界内；朴素随机子集掉 1.45pp（CI [−2.39, −0.53]），逐题口径**越过**等效界。两者相差 +0.50pp（未校正 p = 0.016；家族 Holm 校正后 p = 0.064，未达显著），6 个种子中 5 个方向为正。算力方面，全量一次训练 2.08 GPU-h，激活选择方案合计 1.08 GPU-h（**净省 48.6%**），其中 0.46 GPU-h 花在"为了挑选而多看一遍模型"的选择前向上。EL2N 基线在 24k 池上反而显著差于随机（Holm p = 0.025）且算力只省 10.8%；长度匹配随机对照则显示**长度不是**激活选择的机制。

**机制发现**：激活相似度筛出来的样本更偏爱"带出处、篇幅长"的作答样式——nait 选中的子集里 52.7% 的参考答案带引用/页码（其余 70% 只有 27.9%），生成式评测中 50.6% 的 nait 回答会写出 `Ref./Harrison/页码`（其他臂 2.6–11.2%），但准确率并不更高。**它放大的是样式，不是能力。**

**结论与交付**：同域 48k 池上，"数据 −70%、算力净 −48%"是可复现的；"激活选择显著优于随机"在本研究的功效下**不成立**。我们开源了完整协议、逐题预测、每样本激活统计与审计链，使选择过程可重放、数字可溯源。

**关键词**：训练子集选择；神经元激活；数据冗余度；等效性检验（TOST）；算力核算；临床文本模型

## English Abstract

**Motivation.** Training clinical text models is dominated by sample count. The field widely assumes that clinical corpora are highly redundant and that a large fraction can be dropped without loss, yet *how much*, *how to choose*, and *whether the compute actually shrinks* lack a reproducible protocol and an honest accounting.

**Methods.** We build an in-domain training pool of 48,000 instruction samples (drawn from the MedMCQA train split) and LoRA-fine-tune Qwen2.5-1.5B-Instruct, comparing four ways of keeping 30%: neuron-activation similarity selection (nait, reproducing the mechanism of Nait/ICLR 2026), length-matched random (rand_len), plain random, and the classical EL2N baseline. We evaluate on MedMCQA (in-domain, 4,183 items) and MedQA (cross-task, 1,273 items). The primary endpoint is fixed at 30% retention with a pre-registered equivalence margin δ = 2 pp, tested by paired McNemar plus TOST and seed-level Stouffer combination; method contrasts are Holm-corrected.

**Results.** Across six seeds, activation selection loses 0.96 pp versus full data (95% CI [−1.77, +0.22]) and is equivalent under both item-level and seed-level criteria, whereas the random subset loses 1.45 pp (CI [−2.39, −0.53]) and **crosses** the margin at item level. The gap is +0.50 pp (uncorrected p = 0.016; Holm-corrected p = 0.064, not significant), positive in 5 of 6 seeds. Full training costs 2.08 GPU-hours; activation selection costs 1.08 GPU-hours in total (**48.6% net saving**), of which 0.46 GPU-hours is the one-off selection forward pass. EL2N is significantly *worse* than random on the 24k pool (Holm p = 0.025) while saving only 10.8% compute, and a length-matched control shows that **length is not the mechanism**.

**Mechanism.** Activation similarity selects answers that carry citations and run long: in nait's subset 52.7% of reference answers contain a citation/page number (versus 27.9% in the remaining pool), and 50.6% of nait's generative answers cite `Ref./Harrison/page` (other arms 2.6–11.2%) without any accuracy advantage. **It amplifies style, not capability.**

**Release.** We publish the full protocol, per-item predictions, per-sample activation statistics and an audit chain, so that selection is replayable and every reported number is traceable. The claim "70% fewer data, 48% less compute" is reproducible; the claim "activation selection beats random" is not supported at this study's power.

**Keywords**: training-subset selection; neuron activation; data redundancy; equivalence testing (TOST); compute accounting; clinical text models
