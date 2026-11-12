# DataDiet-EHR

> 口径：训练池 **48,000 条**，30% = **14,400 条**；近重复去重保留 **46,714 / 48,000 = 97.32%**。

**一句话结果**：30% 保留下，nait 掉 **−0.98 pp**（逐题 CI [−1.43, +0.22]，双口径等效），random 掉 **−1.40 pp**（CI [−2.15, −0.86]，逐题口径越界）；两者差 **+0.50 pp**（未校正 p = 0.016，Holm 校正 **0.176**，不显著）。全量一次训练 **2.128 GPU-h**，nait 合计 **1.093 GPU-h（净省 48.6%）**。

**用神经元激活挑出 30% 的临床训练样本，在效果不变差的前提下省掉一半以上的训练算力。**

这是一个可复现的实验装置，不是一次性的脚本堆。核心主张与判据在 `docs/PREREG.md` 里**事先锁死**，
报告口径在 `RESULTS.md`，与提案的逐条对账在 `docs/ALIGNMENT.md`。

---

## 它到底做了什么

```
医学题库/病历    ┌──────────────┐   全量 48,000 条 ──► LoRA 训练 ──► MedQA + MedMCQA 考试
（48,000 条）──►│ 采 5 层激活  │                                 │
                │ 减池内均值    │──► 与目标域质心算余弦 ──► 分层配额 ──► 14,400 条 ──► LoRA 训练 ──► 同一张考卷
                │ L2 归一化     │                                            │
                └──────────────┘                                   两组成绩逐题配对比较（TOST，δ=2pp）
```

对照臂：`random`（同样条数、纯随机）、`rand_len`（同样条数、**长度分布与 nait 一致**）、
`nait_dedup`（先去近重复再选）。

---

## 30 秒上手（Windows）

```bat
:: 1. 环境（一次性）：双击，装依赖并验证 GPU
check_env.bat

:: 2. 一条命令跑通冒烟（约 2 分钟）
.venv\Scripts\python.exe run_one.py --smoke --method full --seed 1

:: 3. 跑实验（每个 run 约 10–45 分钟，8GB 显存够）
.venv\Scripts\python.exe run_one.py --method nait --ratio 0.30 --seed 1
.venv\Scripts\python.exe run_one.py --method random --ratio 0.30 --seed 1
.venv\Scripts\python.exe run_one.py --method rand_len --ratio 0.30 --seed 1

:: 4. 出表出图（R 侧，零第三方包依赖）
Rscript R\run_all.R

:: 5. 三道自检（数据 / 真实性 / 交叉核对）
.venv\Scripts\python.exe tools\verify.py
.venv\Scripts\python.exe tools\audit_run.py
.venv\Scripts\python.exe tools\audit_final.py
```

Linux/macOS：把 `.venv\Scripts\` 换成 `.venv/bin/`，其余相同。

---

## 目录

| 路径 | 是什么 |
|---|---|
| `config.py` | 唯一的参数表：模型、池规模、种子、层号、阈值、任务 |
| `prepare_data.py` | 原始数据 → 统一 JSONL（去重、按科室打标、切训练/探针/考题） |
| `collect_acts.py` | 采激活（response 段 token 均值，5 层） |
| `select_subset.py` | 去均值 → 打分 → 去重 → 分层配额 → `data/subsets/*.json` |
| `train.py` | LoRA SFT，只对 response 算 loss，长度分桶批处理 |
| `eval.py` | 单次前向读 `" A".." D"` 的 logprob，不算生成 |
| `run_one.py` | 一条命令 = 选子集→训练→评测→写 `results/*.csv` |
| `tools/` | 检查器（verify/audit_*）、进度窗口、下载器、长度匹配基线 |
| `R/` | 分析与出图，**base R 零依赖**，只读 `results/` |
| `docs/` | `PREREG.md`（判据）、`PROTOCOL.md`（协议）、`ALIGNMENT.md`（对账） |
| `audit/` | 代码哈希、产物哈希、每次选择的输入输出哈希 |

---

## 现在的结果（两轮，48 个 run）

| 项 | 数字 |
|---|---|
| 30% 保留 vs 全量（24k 池，3 seeds） | **−0.60 / −0.71pp**（MedQA / MedMCQA），逐题 95%CI 均不足 ±2pp |
| nait vs random | **+0.10 / −0.83pp**（p=0.98 / 0.07）→ 无可检测优势 |
| nait vs rand_len（长度匹配） | **+0.29 / −0.42pp**（p=0.57 / 0.10）→ 长度不是机制 |
| 算力净省 | nait **48.6%**、random 70.0%（EL2N 的 45.9% 来自 24k 轮）（都含各自的选择前向） |
| 去重保留率 | 97.32%（这批数据几乎没有语义级重复） |

> 第一轮 12k 池上曾有"nait 比长度匹配对照领先 1.13pp、6 个种子同号、p=-0.101"的结果，24k 池上没有复现，按预注册判据**作废**。

详细表格与"能写/不能写"清单：`RESULTS.md`。**已知五条 limitation 见 `docs/ALIGNMENT.md` 末尾。**

---

## 你需要知道的三个坑

1. **R 侧一律 base R。** 不要 `install.packages()`——本机装不上，脚本也不依赖它。
2. **pip 打完 `Successfully installed` 后进程可能不退出。** 后台跑 + 看日志 + import 验证，别等退出码。
3. **8GB 显存跑 3B 模型不可行**（实测 0.65 样本/秒，且显存换页）。默认基座是 1.5B；3B 需要 ≥12GB。

---

## 换自己的数据

只要满足三个条件就能直接换（不用改代码）：

1. 每条样本有 `instruction` 与 `response` 字段（JSONL）；
2. 有标准答案的评测集（四选一：`question/options/answer`）；
3. 训练集与评测集**不重叠**（按病人/文档 id 切分）。

改 `config.py` 的路径与规模，然后 `prepare_data.py → collect_acts.py → select_subset.py → run_one.py`。

---

## 引用与许可

**代码 MIT**（见 `LICENSE`；著作权人 Yu Yang / 杨宇，
ORCID [0009-0002-6307-3373](https://orcid.org/0009-0002-6307-3373)）。
机器可读的引用信息在 `CITATION.cff`（GitHub 侧栏会显示 "Cite this repository"）。

数据请遵守各自许可：MedMCQA（CC BY 4.0）、MedQA（MIT）、
ChatDoctor-HealthCareMagic-100k（学术用途，见原仓库）。**本项目不含任何院内病历数据。**

> ⚠️ 若要就本方法申请专利：**先提交专利申请，再把仓库转为 public**。
>
> 2026-11-12 记录：本项目**近期不申请专利**（见 `docs/patent/申请路径与费用.md` 第九节），因此转 public 不受此限；但公开即永久丧失该方案的专利新颖性。
> 公开仓库 / 预印本 / 竞赛材料都可能破坏新颖性；软著登记不构成公开。

方法参考：*Neuron-Aware Data Selection in Instruction Tuning for Large Language Models*
（Nait, ICLR 2026）——本仓库复现其**选择机制**，未与官方实现做逐步对齐（官方无可运行代码）。
