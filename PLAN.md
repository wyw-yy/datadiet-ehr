# DataDiet-EHR 执行方案 v0.1
> 基于激活的临床训练子集选择协议与开源实现
> 目标期刊形态：JAMIA / Nature MI（工具 + 软件系统）

---

## 0. 先把题目翻译成一句可验证的话

**一句话主张（claim）**：在临床指令微调场景下，用「神经元激活模式」给训练样本打分并选出一个子集，可以在**下游效果不下降**的前提下把训练数据削掉 **≥30%**，并等比例节省算力；该协议可复现、可选择过程可审计。

这句话里有 5 个可证伪的子命题，**论文的每一节都必须挂在一个子命题上**，跑实验就是为了给它们填数字：

| ID | 子命题 | 需要产出的数字 | 对应幻灯片 |
|---|---|---|---|
| C1 | 选出的子集能替代全量数据 | 30% 子集 vs 全量：Δ指标 + 95%CI | 04-④ 验收 |
| C2 | 不是"随便抽 30%"也能做到 | 随机子集 20 次的分布带，激活选择要落在带外 | 01-③ 方法 |
| C3 | 算力确实省了 | tokens、GPU-hours、墙钟、选择开销的净账 | 04-④ 算力节省 |
| C4 | 跨科室 / 跨任务不塌 | leave-one-dept-out、A 选 B 测 | 01-③ 稳健性 |
| C5 | 别人能复现、能审计 | 一条命令重跑 + manifest 全字段 | 02-④ 可审计 |

> **验收口径必须在跑实验之前写死**，否则跑完再挑指标就是自欺欺人。定为：**δ = 2.0 个绝对点**，TOST 等效性检验，5 seeds，逐题配对。
>
> 为什么不是 1 个点：逐题差值 d∈{-1,0,1}，方差约 0.37；1000–3000 道题 × 5 seeds，配对 CI 半宽约 1.0–1.5pp。δ=1pp 时**连真等效都可能因为 CI 太宽而判不合格**（功效不足），δ=2pp 才有检验功效。这个理由要写进 Method，别等审稿人问。若后期把 MedQA+MedMCQA+CMB 合起来评、或加到 10 seeds，可以再收紧到 1.5pp。

---

## 1. 阶段总览（4 周冲刺版）

| 阶段 | 内容 | 产出物 | 验收门槛（Gate） | 工期 |
|---|---|---|---|---|
| **G0** | 环境 + 仓库骨架 | 能 import torch、能跑 1 个 step | `torch.cuda.get_device_capability()` 返回 `(12, 0)` | 0.5–1 天 |
| **G1** | 文章框架 + claim-evidence 矩阵 | `paper/outline.md` | 每条 claim 都能指到一个实验 ID | 1 天 |
| **G2** | 数据集落地 + 统一 schema | `data/processed/*.jsonl` | 病人级切分、无泄漏、字段齐全 | 1–3 天（MIMIC 1–2 周） |
| **G3** | 基线跑通（全量训练） | `runs/full/` 指标 | 3B 模型在测试集上显著优于 base | 2–3 天 |
| **G4** | 激活采集 + 选择算法 | `selection/manifest.jsonl` | 30% 子集的激活覆盖 ≥ 全量的 90% | 3–5 天 |
| **G5** | 主对照：数据效率曲线 | `results/curve.csv` + 图 | 曲线单调、随机带有明显上界 | 3–5 天 |
| **G6** | 稳健性 + 算力核算 | `results/robustness.csv` | 跨科室掉点 ≤ δ，算力账能对上 | 3–4 天 |
| **G7** | 写作 + 开源发布 | 论文初稿 + repo + 协议文档 | 陌生人照 README 能复现主表 | 1 周 |

**关键路径**：G2 的数据集许可是唯一可能卡两周的事 → **今天就去申请**，其余并行。

---

## 2. 逐阶段怎么做

### G0 环境（Windows + RTX 5070 Laptop 8GB）

你的卡是 Blackwell（sm_120），**必须装 cu128 的 torch**，否则会报 `no kernel image is available for execution on the device`。

```powershell
cd C:\Users\yang'yu\Desktop\codetest\datadiet-ehr
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install torch --index-url https://download.pytorch.org/whl/cu128
pip install transformers datasets peft trl accelerate scikit-learn sentencepiece protobuf tqdm pyyaml
python -c "import torch;print(torch.__version__, torch.cuda.get_device_capability())"
```

- **磁盘**：C 盘剩 62 GB，够 3B 模型 + 数据；7B QLoRA 要清盘或外挂盘。
- **bitsandbytes 在 Windows 上是坑**（无官方 wheel）→ 本机只跑 1.5B/3B 的 bf16 LoRA，不要在本机碰 4bit。要跑 7B 就上 AutoDL 单卡 4090（24 GB，约 ¥2/h）。
- 先在 `AutoDL` 建一个镜像环境，把 `data/`、`configs/` 同步过去，本机只做开发和 1.5B 调试。

### G1 文章框架（别写成"综述式框架"，要写成"证据表"）

`paper/outline.md` 必须包含四块，缺一块后面就会返工：

1. **Introduction 的三段式**：临床模型训练成本高（钱/算力/伦理审批）→ 数据侧压缩是最便宜的一刀 → 但"选哪些样本"此前没有可复现协议（这就是你的 gap，直接引用 Nait 的不可复现性）。
2. **Method 的符号表**：模型 M、样本 (x_i, y_i)、科室 d_i、任务 t_i、激活向量 a_i、选择比例 ρ、子集 S_ρ。**符号先定死，代码里的变量名跟符号一一对应**。
3. **Claim–Evidence 矩阵**：C1–C5 每行写"用哪张表/哪张图证明"，空着的格子就是你还没做的实验。
4. **图表清单**（先画空图，后填数）：
   - Fig.1 流程图（数据 → 激活 → 打分 → 选子集 → 训练 → 评估）
   - Fig.2 数据效率曲线（x = 保留比例，y = 指标，多条方法线 + 随机带）
   - Fig.3 激活打分分布（按科室分面）
   - Fig.4 冗余度热图 / 近重复比例
   - Table.1 主结果（全量 vs 随机 vs EL2N vs 激活 vs 激活+去重+分层）
   - Table.2 算力账

> **给导师看的一句话**：框架不是目录，是"每条结论对应哪个实验"，这样他一眼就知道你要跑多少卡时。

### G2 数据集（这是你今天要去办的事）

**选择原则**：① 有 `prompt/response` 指令对；② 样本 ≥ 5000（否则 30% 削减的噪声大于效应）；③ 最好带科室/学科标签；④ 许可清晰。

| 选项 | 规模 | 任务形态 | 许可/门槛 | 获取耗时 | 建议 |
|---|---|---|---|---|---|
| **MIMIC-IV**（PhysioNet） | 数十万住院记录 | 出院小结 → ICD 编码 / 再入院 / 摘要 | CITI 培训 + DUA，**需导师挂靠** | 1–2 周 | 最贴题（院内 EHR），**主选**，今天就去申请 |
| MIMIC-IV **demo** | 100 病人 | 同上 | 全开放 | 10 分钟 | 只用来调 pipeline，不能出论文数 |
| **HealthCareMagic-100k**（`lavita/ChatDoctor-HealthCareMagic-100k`） | 10 万医患问答 | 指令微调 | 完全开放 | 10 分钟 | **无伦理审批时的主力替身**，规模刚好够画曲线 |
| **MedMCQA**（`openlifescienceai/medmcqa`） | 19.4 万选择题，21 个 `subject_name` | 评测 + 科室分层 | 开放 | 10 分钟 | 跨科室实验的标签来源 |
| **MedQA-USMLE**（`GBaker/MedQA-USMLE-4-options`） | 1.2k 测试 | 评测 | 开放 | 10 分钟 | 主评测集 |
| **CMB / Huatuo-26M** | 中文 | 中文指令 | 开放 | 半小时 | 若做中文临床场景 |
| 院内真实 EMR | 未知 | 最贴题 | 伦理审批 3–6 个月 | 不可控 | 只做"limitation"，别当主线 |

**落地动作（不管选哪个）**：

1. 统一成一份 JSONL，字段固定：
   ```json
   {"id":"...", "patient_id":"...", "dept":"cardiology", "task":"qa",
    "prompt":"...", "response":"...", "n_tokens":312, "source":"mimic-iv"}
   ```
2. **按病人切分，不按样本切分**（MIMIC 用 `subject_id`；HealthCareMagic 没有病人 ID，就先做近重复去重再随机切）。这是审稿人第一个会问的问题。
3. 切三份：`train`（用来选子集）/ `val`（早停）/ `test`（只碰一次）。
4. 写 `reports/data_card.md`：来源、许可、去标识化、样本数、科室分布、token 分布、已知偏差。

> **陷阱**：HealthCareMagic 里有大量近重复问答，直接随机切分会导致 test 泄漏、指标虚高 10+ 个点。先去重（cosine > 0.95 视为重复），**而这个去重统计本身就是 C5 冗余度报告的第一张图**。

### G3 基线（先把"全量"跑出可信的数）

- 基座：`Qwen2.5-3B-Instruct`（8 GB 能训，中文强）或 `Llama-3.2-3B-Instruct`；有 24 GB 卡再上 7B。
- 训练：LoRA（r=16, α=32, 所有 linear），bf16，seq 1024，bs 1 + grad-accum 8，cosine，lr 1e-4，1–3 epoch。
- 必须记录：`tokens_seen`、`gpu_hours`、`peak_vram`、`wall_clock`、`seed`、`git_sha`、`data_hash`。
- **验收**：全量基线在 test 上要显著高于未微调 base（否则你的任务太难/太小，30% 削减根本测不出来）。

> **陷阱**：如果全量基线还没收敛（loss 还在掉），子集当然"效果不降"，这种结论一文不值。**先确认全量已经到平台期**，再谈削减。

### G4 激活采集 + 选择算法（本项目的技术核心）

**Step 1 采集激活**（只前向，bf16，无梯度，一次约等于 1/3 个 epoch 的成本）

- 挂 hook 在每层 FFN 的中间神经元上：`h = act_fn(gate_proj(x)) * up_proj(x)`，维度 `d_ff`。
- 取层：`L = {8, 12, 16, 20, 24}`（3B 模型约 28–36 层，取中后段，做层数消融）。
- 池化：**只对 response token 取均值**（prompt 是模板，会污染信号），得到 `ā_{i,l} ∈ R^{d_ff}`。
- 二值化：`b_{i,l} = 1[ā_{i,l} > τ_l]`，`τ_l` = 该层全数据集 90 分位（这个 τ 要写进协议，是超参）。

**Step 2 目标域特征**（Nait 的关键：不是"难样本优先"，而是"像目标域的样本优先"）

- 从 `test` 里抽 200 条不参与训练的 in-domain 探针 `P`，算质心 `c_l = mean_{p∈P} ā_{p,l}`。
- 样本得分：`s_i = mean_l cos(ā_{i,l}, c_l)`（或二值向量的 Jaccard，做消融）。

**Step 3 选择**（三段式，缺一不可）

```
输入: 得分 s_i, 科室 d_i, 预算 ρ
1) 去重: 激活余弦 > 0.95 的样本聚成一簇, 每簇只留 s 最高的
2) 分层配额: 每个科室按其在训练集中的占比 × ρN 分配名额
3) 簇内按 s 降序取满, 输出 S_ρ
```

- 比例扫描：`ρ ∈ {10%, 20%, 30%, 50%, 70%, 100%}`（只做 30% 一个点会被审稿人打）。
- **输出 manifest**（这就是"可审计"的实体）：

```json
{"sample_id":"...", "dept":"...", "task":"...", "score":0.813,
 "rank":17, "selected":true, "layer_scores":{"8":0.79,"12":0.83},
 "dup_cluster":3, "config_hash":"...", "code_sha":"...", "seed":42}
```

> 这张表的字段要能直接对上幻灯片 02-③ 的"关键字段：样本激活统计、被选子集、训练数据量、下游任务表现、训练算力"。

### G5 主对照实验（决定成败的一组）

**两套训练协议都要跑**，这是最容易被人挑毛病的地方：

| 协议 | 定义 | 回答什么问题 |
|---|---|---|
| **P1 等 epoch** | 子集训同样 epoch 数 | 数据少了 → 算力省了多少（主线） |
| **P2 等 token** | 子集重复到与全量同 token 数 | 掉点是因为"数据少"还是"没训够"（防守） |

**方法矩阵（每格 5 seeds）**：

| 方法 | 说明 | 作用 |
|---|---|---|
| Full | 100% 数据 | 上界 |
| Random-ρ | 20 次随机抽样 | **随机带**，C2 的对照组 |
| EL2N / GraNd | 训练早期 loss/梯度范数 | 经典难度基线（无激活） |
| Length heuristic | 按长度选 | 最蠢的基线，必须有 |
| **Nait-style（ours）** | 激活相似度 | 主方法 |
| **Ours + dedup + strat** | 三段式完整版 | 消融：去重和分层各值多少 |

**统计口径（写进 Method，不要事后补）**：
- 5 seeds，报 mean ± std；
- 配对 bootstrap（10k 次）给 95% CI；
- 等效性：TOST，δ = 1.0 绝对点；
- 随机带取 20 次的 5–95 分位，主方法必须落在**带外**才算"选择有效"。

### G6 稳健性与算力核算

- **跨科室**：留一科室（每次去掉一个 dept 训练，测该 dept）→ 报最差科室的掉点。
- **跨任务**：在 task A 上选子集，训完测 task B（零样本迁移）。
- **算力账**（一定要算**净账**）：

```
净节省 = 全量训练 GPU-h − (选择阶段前向 GPU-h + 子集训练 GPU-h)
```

选择阶段大约是全量训练的 0.3×，所以 30% 数据 → 净省约 0.4× 训练算力，**别写成省 30% 算力**，会被抓。

- 换算成钱：`GPU-h × 单价`，再换算成"每千次推理成本"，这是 JAMIA 读者真正关心的。

### G7 写作与开源

- 仓库三件套：`README`（一条命令复现主表）、`protocol.md`（协议规范，可被别的医院照做）、`manifest` 示例。
- 论文里必须有一段 **Limitations**：公开替身数据 ≠ 院内 EHR、单中心、模型规模 ≤7B、等效性只在本任务族成立。

---

## 2.5 工具链分工：Python 出数，R 出结论

一句话：**凡是前向/反向传播的活只能在 Python；凡是"这个差异到底可信不可信"的活全放 R。**

| 环节 | 语言 | 具体活 | 产物 |
|---|---|---|---|
| 数据统一 / 病人级切分 / 去重 | Python | `datasets` + `pandas` | `data/processed/*.jsonl` |
| 激活采集 | Python | torch forward hook，bf16，无梯度 | `runs/<id>/acts/*.npz` |
| 打分 / 选择 | Python | 余弦 + 去重 + 分层配额 | `results/selection.parquet` |
| 训练 / 推理 | Python | LoRA SFT + 生成 | `results/preds/<exp_id>.parquet` |
| **指标聚合 / 等效性 / CI** | **R** | 配对 bootstrap、McNemar、TOST | `results/eq_table.csv` |
| **数据效率曲线 / 出图** | **R** | ggplot2 + 随机带 ribbon | `paper/figures/*.png` |
| **科室 / 任务稳健性** | **R** | 分层 delta + CI（`lme4` 可选） | `results/robust.csv` |
| **算力账 / 成本表** | **R** | dplyr 汇总 + 线性模型 | `results/compute.csv` |
| **冗余度报告** | **R** | 相似度分布、近重复率、有效样本数 | `reports/redundancy.md` |

**语言边界只有这 5 个文件**（改字段先改这张表，别在两边的代码里各自发明列名）：

| 文件 | 谁写 | 谁读 | 关键列 |
|---|---|---|---|
| `results/metrics_long.csv` | Py | R | `exp_id, method, ratio, seed, dept, task, metric, value, n` |
| `results/preds/<exp_id>.parquet` | Py | R | `item_id, y_true, y_pred, correct, score`（**逐题**，不是汇总；demo 阶段用 `.csv.gz`，读法一样） |
| `results/selection.parquet` | Py | R | `sample_id, dept, score, layer, selected, ratio, dup_cluster` |
| `results/compute.csv` | Py | R | `exp_id, tokens_seen, gpu_hours, wall_s, peak_vram_gb, select_overhead_h` |
| `results/redundancy.parquet` | Py | R | `i, j, cosine, same_dept`（抽样后的成对相似度） |

**三条铁律**
1. Python 侧**不算 p 值**（只写原始指标和逐题预测）；R 侧**不读** `runs/` 里的 JSON，只认 `results/` 下的 parquet/csv。
2. 每个 run 目录必须落 `config.yaml + git_sha + data_hash`，R 靠 `exp_id` 关联。
3. 新增任何实验 = 新增一行 `method`，不改 schema。

**这条分工为什么能给你加分**：审稿人问"你凭什么说 30% 不掉点"，如果你答"5 个 seed 的均值±标准差"，其实答不了——seed 噪声可能比效应还大。正确的答法是**逐题配对检验**：同一批测试题，全量模型对、子集模型错（b/c 格） vs 反过来（c/b 格），McNemar 检验 + 配对 bootstrap 的 95%CI + 等效性界 δ。R 里 20 行，Python 里要手写半天。**R 不是配角，它是这篇论文的统计护城河。**

**本机现状（已实测）**：R 4.6.1 在 `C:\Program Files\R\R-4.6.1\bin\x64\Rscript.exe`，`Rscript` 不在 PATH；只装了 30 个基础包，无 tidyverse。**而且这台机器的 shell 连不上外网**（`Invoke-WebRequest` 到 TUNA/CRAN 都报"基础连接已经关闭"），`install.packages()` 装不上任何东西。

对策已经落地：**R 层全部用 base R 写成零依赖脚本**（`read.csv` + `aggregate` + `binom.test` + `png` 手绘），换任何一台新装 R 的机器都能直接跑，这反而是可复现性的加分项。真要装包，你在 RStudio 里手动跑一次即可。

---

## 2.6 R 分析层已经写好了，现在就能跑

```powershell
cd C:\Users\yang'yu\Desktop\codetest\datadiet-ehr
& "C:\Program Files\R\R-4.6.1\bin\x64\Rscript.exe" "R/run_all.R"
```

12 秒跑完，产出全部表格和图。**现在跑的是假数据**（`R/99_make_demo_data.R` 生成 210 个 run），目的是在拿不到 GPU 结果之前把统计口径、图表版式、文档结构全部定死。真实数据到位后：删掉 99 那个脚本、把 `R/00_setup.R` 里的 `RESULTS` 指向 `results/`，其它一行不用改。

| 脚本 | 干什么 | 产出 |
|---|---|---|
| `R/00_setup.R` | 路径、δ、调色板、`read_preds`、`boot_ci` | — |
| `R/01_equivalence.R` | 逐题配对 → 配对 bootstrap 95%CI → 精确 McNemar → TOST | `results/eq_table.csv` |
| `R/02_curve.R` | 数据效率曲线（绝对准确率版 + 掉点版） | `paper/figures/fig02_*.png` |
| `R/03_robustness.R` | 分科室 delta + CI（r=0.30） | `results/robust.csv`、`fig04_dept.png` |
| `R/04_compute.R` | 算力净账（扣掉选择阶段前向） | `results/compute_table.csv`、`fig05_compute.png` |
| `R/run_all.R` | 一条命令跑完 | 上面全部 |

假数据跑出来的样子（论文主结果的"版式预演"）：

- r=0.30 时 nait 相对全量：MedQA −0.78pp（95%CI −1.98…+0.42），ICD −0.62pp（−1.76…+0.47）→ **两条都落在 ±2pp 等效界内**；el2n −2.9pp、random −6.8pp → 都不合格。这正是"既能等效、又不是随便抽都行"的证据结构。
- 分科室：nait 最差科室 −2.2pp，random 在肿瘤科掉 10pp（该科样本少、题目难）。
- 算力：全量 3.20 GPU-h；30% 子集训练 0.96 + 选择前向 0.55 = 1.51 GPU-h，**净省 53%**（不是 70%）——这就是"净账"和"省三成"的区别，也是最容易被审稿人抓的地方。

---

## 3. 代码怎么选（"可以优化的代码"在哪）

不要从零写训练循环，**在成熟框架上只加一个"选择阶段"**，这是最省时间也最像"开源实现"的做法。

| 用途 | 仓库 | 怎么用 |
|---|---|---|
| 训练框架（推荐） | `hiyouga/LLaMA-Factory` | 支持自定义 JSONL、LoRA、断点续训；加一个 `preprocess/select.py` 前置阶段 |
| 备选训练框架 | `axolotl-ai-cloud/axolotl` | YAML 配置更干净，适合做多组对照 |
| 激活提取 | `TransformerLensOrg/TransformerLens` 或原生 `register_forward_hook` | 建议原生 hook，少一层依赖 |
| 经典剪枝基线 | `mansheej/data_diet`（DataDiet 官方，GraNd/EL2N） | 把 CIFAR 版的打分逻辑搬到 token 级 |
| 影响力度量基线 | `princeton-nlp/LESS` | 梯度相似度选数据，指令微调场景的最强对手 |
| 去重 | `facebookresearch/SemDeDup` | 换成激活空间即可复用 |
| 评测 | `lm-evaluation-harness` + 自写临床任务脚本 | MedQA/MedMCQA 现成 |

**目录骨架（先建空壳，G3 之前填满）**

```
datadiet-ehr/
├─ configs/            # base.yaml, select.yaml, ratios/*.yaml
├─ src/
│  ├─ data/            # 统一 schema、病人级切分、去重
│  ├─ activate/        # hook 采集、池化、二值化、目标域质心
│  ├─ select/          # 打分、去重、分层配额、导出 manifest
│  ├─ train/           # LoRA SFT 封装（调 LLaMA-Factory 或 trl）
│  └─ eval/            # 临床任务 + 通用基准 + 统计检验
├─ scripts/            # 01_prepare.sh 02_activate.sh 03_select.sh 04_train.sh 05_eval.sh
├─ data/{raw,processed}/
├─ runs/               # 每次实验一个目录，落 config+git_sha+metrics
├─ reports/            # data_card.md, redundancy.md, compute.md
└─ paper/              # outline.md, figures/
```

---

## 4. 风险与预案（提前想好，别等跑完才发现）

| 风险 | 症状 | 预案 |
|---|---|---|
| **30% 不成立** | 30% 掉点 > δ | 退到"20% 等效 + 50% 近无损"的**曲线**叙事，论文改成"给出冗余度上界"，仍是有效结论 |
| 全量没收敛 | 全量 loss 还在降 | 加 epoch / 加数据；否则一切对比无效 |
| 随机基线太强 | 随机 30% 也等效 | 说明数据本身高度冗余 → 把论文重心挪到"冗余度报告"（C5），这是更有意思的发现 |
| 测试集泄漏 | 指标异常高（>90） | 病人级切分 + 近重复去重 + 检查 prompt 模板是否出现在训练集 |
| 显存不够 | OOM | seq 降到 512、grad checkpoint、bs=1；或上 24 GB 卡 |
| 选择开销吃掉收益 | 净算力为负 | 只采 1/4 层、只采 response token、batch 前向 |

---

## 5. 现在就能做的 5 件事（按顺序）

1. **今天**：去 PhysioNet 申请 MIMIC-IV 访问（CITI 课程 2 小时，DUA 要导师签字）——这是唯一卡两周的事。
2. **今天**：同时把 `HealthCareMagic-100k` 拉下来（10 分钟），保证明天有东西可跑。
3. **明天**：建 venv + 装 cu128 torch，验证 `(12,0)`；跑通 1.5B 模型的 10 步 LoRA，确认显存峰值。
4. **明天**：写 `paper/outline.md` 的 Claim–Evidence 矩阵（C1–C5），拿给导师确认"就按这 5 条验收"。
5. **本周**：跑出全量基线（1 seed 先校准时长），再决定要不要租 4090。

---

## 6. 给导师的三句话汇报模板

> ① 我把题目拆成 5 条可证伪结论（数据削减 30% 同效果、优于随机、算力净省、跨科室、可复现），每条形一个实验；
> ② 数据集双轨：MIMIC-IV 走伦理（已提交），公开替身 HealthCareMagic-100k 今天就能跑通管线；
> ③ 代码不重写，在 LLaMA-Factory 上加"激活采集 + 选择"两个模块，主表 = 全量 / 随机 / EL2N / 激活四行 × 5 seeds。
