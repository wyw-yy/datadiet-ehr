# 从这里开始（DataDiet-EHR）

一句话：**用神经元激活挑出 30% 的临床训练数据，证明微调效果不降、算力净省。**

当前状态：主实验已跑完一轮（19 run / 3 seeds），正在补到 6 seeds；代码、统计、审计链都已闭环。
所有数字可在 `RESULTS.md` 查到，所有命令都在下面。

## 📍 进度（2026-10-24 15:00）

| # | 阶段 | 状态 | 产物 |
|---|---|---|---|
| 1 | 环境（venv + torch cu128 + ML 栈） | ✅ | `.venv/`、`check_env.bat` 一键体检 |
| 2 | 公开数据（MedMCQA / MedQA） | ✅ | `data/raw/`、`data/processed/` |
| 3 | 数据统一 + 泄漏检查 | ✅ | `tools/check_leak.py`、`tools/audit_run.py` |
| 4 | 激活采集（5 层 × 12k 条） | ✅ | `cache/acts/acts_train.npz`（174 MB） |
| 5 | 子集选择（nait / nait_dedup / rand_len） | ✅ | `data/subsets/*.json`、`results/select_stats*.json` |
| 6 | 冒烟（train→adapter→eval→upsert） | ✅ | `results/metrics_long.csv` |
| 7 | 第一轮主实验（19 run，3 seeds） | ✅ | `RESULTS.md` |
| 8 | **第二轮：补到 6 seeds + rand_len 对照** | 🟡 正在跑 | `night6.log` |
| 9 | R 分析层（等效性/剂量/科室/算力） | ✅ | `R/run_all.R` → `paper/figures/` |
| 10 | 预注册 + 审计链 + 论文表 | ✅ | `docs/PREREG.md`、`audit/`、`paper/table1.md` |
| 11 | 真数据（MIMIC / 院内 EMR） | ⬜ 卡许可 | `docs/MIMIC_CHECKLIST.md` |
| 12 | 生成式评估 | ⬜ 设计完成 | `docs/GENERATIVE_EVAL.md` |

**与最初计划的偏离（都写进 limitation）**

1. **基座 1.5B 而不是 3B**：3B 显存峰值 7.3–9.5 GiB > 物理 7.96 GiB，Windows 换页导致 203 MHz 空转、0.35 样本/秒。
2. **训练池 12,000 条**（不是 24k）：时间账，12k 跑一遍约 40 分钟。
3. **训练池从 HealthCareMagic 换到 MedMCQA-train**：前者是患者口语，训完 MedQA 反而掉 3.8pp（base 0.4776 → SFT 0.4399），不对域。
4. 待办：跑 full 在 6k/12k/24k 三点，证明 12k 已到平台。

**本机实测性能**（`results/benchmarks.json`）：36 SM、7.96 GiB、最高 3090 MHz；bf16 矩阵乘 7.0–11.8 TFLOPS；满载功耗顶到 93 W 上限、时钟约 202 MHz。

## ⚠️ 五个坑（都踩过）

1. **R 只能用 base R**——shell 装不了包，脚本一律零依赖。
2. **pip 打完 `Successfully installed` 不退出**——后台跑、读日志、见成功就 kill。
3. **8 GB 显存跑不了 3B**——会掉进显存换页；主矩阵用 1.5B。
4. **`expandable_segments` 在这台机器无效**——设了只会有警告。
5. **别用 PowerShell 的 `-replace | Set-Content` 改含中文的文件**——会把 UTF-8 写坏。

## 一条命令看全部结论

```bash
Rscript R\run_all.R          # 4 张图 + 3 张表，读 results/ 下的 CSV
python tools\make_table1.py  # 论文正文表 paper/table1.md
```

## 跑一个实验（3600 条约 13 分钟）

```bash
.venv\Scripts\python.exe run_one.py --method nait --ratio 0.30 --seed 4
.venv\Scripts\python.exe run_one.py --method rand_len --ratio 0.30 --seed 4   # 长度匹配对照
```

`--method` 可选：`full`、`random`、`nait`、`nait_dedup`、`rand_len`。
一条命令内部：选子集 → 训练 LoRA → 两个任务各评一次 → upsert 到 `results/*.csv`。

## 队列（整夜跑）

```bash
python tools\night_queue.py --plan seeds6 --dry-run   # 先看要跑哪些
python tools\night_queue.py --plan seeds6             # 真跑，自动跳过已完成的
```

## 五道自检（改完代码必跑）

```bash
.venv\Scripts\python.exe tools\verify.py        # 数据/子集/表值一致性
.venv\Scripts\python.exe tools\audit_run.py     # 原始文件 → JSONL → preds 溯源
.venv\Scripts\python.exe tools\audit_deep2.py   # 统计口径与混杂
.venv\Scripts\python.exe tools\audit_final.py   # 六段交叉核对 A–F
.venv\Scripts\python.exe tools\confirm_fixes.py # 四项修复是否还在
```

全绿才能引用数字。

## 目录

```
config.py           全局常量（模型路径、池子大小、种子、方法表）
prepare_data.py     原始数据 → data/processed/*.jsonl（统一契约）
prepare_mimic.py    MIMIC → 同一契约（有数据后才跑；现在可 --selftest）
collect_acts.py     采激活 → cache/acts/*.npz
select_subset.py    打分 + 分层配额 + 去重 → data/subsets/*.json
train.py            LoRA SFT（只对 response 算 loss，长度分桶）
eval.py             四选一，比 " A".." D" 的 logprob
run_one.py          一条命令跑完一个 (method, ratio, seed)
R/                  分析层（base R，出表和图）
tools/              下载、审计、队列、表、自检脚本
docs/               PROTOCOL / PREREG / ALIGNMENT / MIMIC_CHECKLIST / GENERATIVE_EVAL / ADVISOR_SUMMARY
results/            逐题预测、指标表、审计 JSON（都在 git 里）
```

## 现在只有三件事会卡住进度

1. **MIMIC 许可**（唯一有排队延迟的）：见 `docs/MIMIC_CHECKLIST.md`，需要导师签 DUA。
2. **院内 EMR 渠道**：找导师要，哪怕几千条去标识化记录就能升级结论。
3. **机器**：另外两台机器的显卡/显存还没确认；≥6 GB 就能分担种子。

## 如果卡住

- 先跑 `check_env.bat`，它会告诉你环境哪一段坏了。
- 再看 `night.log` / `night6.log` 最后 20 行。
- 数据问题看 `docs/PROTOCOL.md` 的"输入契约"一节。
- 统计口径的争论看 `docs/PREREG.md`（判据是跑之前定的，不许改）。
