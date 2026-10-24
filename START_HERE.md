# 从这里开始（DataDiet-EHR）

项目位置：`C:\Users\yang'yu\Desktop\codetest\datadiet-ehr`

---

## 📍 进度（2026-10-22 20:50 更新）

| # | 步骤 | 状态 | 证据 |
|---|---|---|---|
| 1 | 环境（venv + torch cu128 + ML 栈） | ✅ 完成 | `torch 2.11.0+cu128`、`capability=(12,0)`、bf16 显存实测通过；transformers 5.20.2 / peft / trl / datasets 全 import 通过 |
| 2 | 模型权重 | ✅ 完成 | `models/Qwen2.5-3B-Instruct/` 6.19 GB（备用，需 ≥12 GB 显存）；`models/Qwen2.5-1.5B-Instruct/` 3.09 GB（**主用**） |
| 3 | 数据下载 | ✅ 完成 | HCM 112,165 行、MedQA 1,273 题、MedMCQA 4,183 题（已剔 `cop=-1`）；`data/raw` 只剩 4 个合法输入 |
| 4 | 数据统一 | ✅ 完成 | `data/processed/{train,probe,medqa,medmcqa}.jsonl` = 12,000 / 2,000 / 1,273 / 4,183 行；科室分布 other 49.6% / neuro / cardio / endo / resp / onco |
| 5 | 五个 Python 脚本 + `run_one.py` | ✅ 完成 | `prepare_data.py` `collect_acts.py` `select_subset.py` `train.py` `eval.py` `run_one.py`，另有 `tools/` 下 10 个探针与工具 |
| 6 | 冒烟测试 | ✅ 通过 | `step 25/25 loss 2.4543 200 samples 4.34 samp/s`；eval 带 adapter 跑通 medqa 0.44 / medmcqa 0.42（100 题，只证明链路，不是结果）；`metrics_long.csv` 已有 2 行 |
| 7 | 全量基线（full） | ⬜ 待跑 | 与 STEP 8 的 3 个 pilot 一起跑，第一个就是 full |
| 8 | 激活采集 + 子集选择 | ✅ 完成 | `acts_train.npz` (12000, 5, 1536)、`acts_probe.npz` (2000, 5, 1536)；`subsets.json` 五档齐（30% = 3,600 条），审计数据在 `results/select_stats.json` |
| 9 | 主实验矩阵 | 🟡 **3 个 pilot 正在跑** | `full`(12k) → `nait@30%`(3.6k) → `random@30%`(3.6k)，各约 50/15/15 分钟 |
| 10 | R 出结论 | 🟡 管线就绪 | `R/run_all.R` 已用**假数据**跑通全部图与检验；把 `R/00_setup.R` 的 `RESULTS` 指向 `results/` 即切真实数据 |

**与最初计划的偏离（必须写进论文 limitation）**

1. **基座 1.5B 而不是 3B**：3B 显存峰值 7.3–9.5 GiB > 物理 7.96 GiB，Windows 换页导致 GPU 掉到 200 MHz、0.35 样本/秒，不可用。1.5B 实测 1.11 样本/秒（bs4×512）。
2. **训练池 12,000 条而不是 24,000**：时间账。12k 跑一遍约 1.3–1.5 h。
3. **3 个 seed 而不是 6 个**，比例仍为 10/20/30/50/70。
4. 待办之一：跑 full 在 6k/12k/24k 三点，证明 12k 已到平台（否则"30% 等效"可能只是"12k 冗余多"）。

**本机实测性能**（`results/benchmarks.json` 有原始记录）：36 SM、7.96 GiB、最高 3090 MHz；bf16/fp16 矩阵乘 7.0–11.8 TFLOPS、fp32 3.5–3.8；满载功耗仅 31 W（上限 93.8 W）。结论：GPU 被压在低功耗状态，约只用出额定的 1/8。

---

## ⚠️ 两个已知的坑（踩过，别再踩）

- **pip**：清华源会卡死在 `Looking in indexes`（一律用官方 `pypi.org` 或阿里云）；装完打了 `Successfully installed` 进程也不退出（kill 掉，用 `import` 验证）。
- **cuda**：`PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` 在这台机器**不生效**（`expandable_segments not supported on this platform`），别指望它省显存。

---

## STEP 1 · 环境（已完成，留档）

```bat
cd C:\Users\yang'yu\Desktop\codetest\datadiet-ehr
python -m venv .venv
.venv\Scripts\activate
python -m pip install -U pip
pip install torch --index-url https://download.pytorch.org/whl/cu128
pip install transformers datasets accelerate peft trl pandas numpy pyarrow
```

必须 cu128：5070 Laptop = Blackwell `sm_120`，cu118/cu121 会报
`no kernel image is available for execution on the device`。

**验收**：`python -c "import torch;print(torch.cuda.get_device_capability())"` → `(12, 0)`。

---

## STEP 2 · 数据（已完成，留档）

`data/raw/` 现在的 4 个输入：

```
healthcaremagic/hcm-100k.parquet                      67.25 MiB (112,165 行, instruction/input/output)
medmcqa/data/test-00000-of-00001.parquet               0.89 MB
medmcqa/data/validation-00000-of-00001.parquet         1.41 MB
medqa/phrases_no_exclude_test.jsonl                    1.98 MiB (1,273 题)
```

镜像经验：ModelScope 对模型最快（~2.5 MB/s，12 线程）；hf-mirror 对 dataset 单连接 ~0.66 MB/s 但**并发会 429**，`tools/fetch_parallel.py` 已加指数退避。

---

## STEP 3 · MIMIC 申请（还没做，唯一有排队延迟的事）

1. https://physionet.org 注册 + 完成 CITI "Data or Specimens Only Research"（约 2 小时，可中断）
2. 传 CITI 证书 → 提交 MIMIC-IV DUA（**需要导师签字**）
3. research use 里写清：研究训练子集选择与算力节省，不用于临床决策

**验收**：credentialing 完成邮件 + DUA submitted。批下来只换数据不换代码。

---

## STEP 4 · Python 骨架（已完成）

| 文件 | 作用 |
|---|---|
| `prepare_data.py` | 统一 JSONL、科室映射、去重、切 train/probe/评测集 |
| `collect_acts.py` | 采 5 层（8/12/16/20/24）response-token 平均激活 → `cache/acts/*.npz` |
| `select_subset.py` | 打分 `s_i=mean_l cos(ā,c_l)` → 流式贪心去重（cos>0.95）→ 科室配额 → 取满 |
| `train.py` | LoRA SFT；长度分桶 batch、分词缓存、只对 response 算 loss |
| `eval.py` | 单次前向比 `" A".." D"` 四个 token 的 logprob，输出逐题 preds |
| `run_one.py` | 一条命令 = 选子集 → 训练 → 评测 → upsert `metrics_long.csv` / `compute.csv` |

基座、数据、评测的口径都写在 `config.py` 顶部；改 `BASE_DIR` / `N_POOL` 就能整体换配置。

---

## STEP 5 · 冒烟测试（✅ 2026-10-22 20:53 通过）

```bat
.venv\Scripts\python.exe run_one.py --smoke --method full --seed 1 --epochs 1
```

**验收**：loss 不 nan、显存峰值 < 7.5 GiB、`results/preds/full_s1_medqa.csv.gz` 与 `full_s1_medmcqa.csv.gz` 都有文件、`results/metrics_long.csv` 多出两行。
唯一目的：在花 16 小时之前确认没有隐藏的坑。**已全部满足**，且长度分桶把吞吐从 1.11 提到 **4.34 样本/秒**（12,000 条一遍约 46 分钟）。

---

## STEP 6 · 全量基线（1 个 seed）

```bat
.venv\Scripts\python.exe run_one.py --method full --seed 1 --epochs 1
```

**验收**：域内 probe 与 MedQA 两项都记下来，且明显不同于 base。这组数是所有 delta 的分母。
**注意**：现在评测只有选择题；STEP 6 之后要补 **probe（HCM 留出 2,000 条）的 loss/准确率**作为域内主指标——那是"训得好不好"的正面证据。

---

## STEP 7 · 激活采集 + 选择（创新点）

```bat
.venv\Scripts\python.exe collect_acts.py --split train
.venv\Scripts\python.exe collect_acts.py --split probe
.venv\Scripts\python.exe select_subset.py
```

**验收**：`data/subsets/subsets.json` 里 `nait{10,20,30,50,70}` 与 `nait_dedup{...}` 的 id 数量与比例一致；打印的 dedupe 保留率 < 100%（说明真去重了）。

---

## STEP 8 · 先跑 3 个 run 看方向，再铺矩阵

```bat
.venv\Scripts\python.exe run_one.py --method full   --seed 1 --epochs 1
.venv\Scripts\python.exe run_one.py --method nait   --ratio 0.30 --seed 1 --epochs 1
.venv\Scripts\python.exe run_one.py --method random --ratio 0.30 --seed 1 --epochs 1
```

**决策点**：如果 `nait@30%` 相对 full 掉点 > 3pp，先改选择策略，别铺 16 小时。
过了再跑：`full × 3 seeds` + `{random,nait,nait_dedup}×0.30×3 seeds` + 曲线（seed 1 的 10/20/50/70）。

---

## STEP 9 · R 出结论（管线已就绪）

```bat
& "C:\Program Files\R\R-4.6.1\bin\x64\Rscript.exe" "R/run_all.R"
```

切真实数据：`R/00_setup.R` 里 `RESULTS` 改成 `results`，并删掉 `R/run_all.R` 第一行的 `99_make_demo_data.R`。

---

## STEP 10 · 写作

`PLAN.md` §0 的 C1–C5 就是论文骨架，图 2/4/5 由 R 直接出。
要补的是 §1 相关工作（读 20 篇 MIMIC / 子集选择方向）和临床场景叙述。

---

## 如果卡住

1. `import torch` 报 `no kernel image` → torch 版本不对，必须 cu128
2. 显存爆 → 降 `--bs`、降 `--max-len`、或换 1.5B（`config.BASE_DIR`）
3. 磁盘不够 → `pip cache purge`、删 `models/Qwen2.5-3B-Instruct`
4. R 装包失败 → 一律 base R 零依赖，不要装包
