# A 计划：放大池子那一轮（等 GPU 空出来再跑）

> ⚠️ **已归档（2026-10-28）**：本文是 24k 池那一轮 的操作手册/计划，里面的池子大小、子集条数、耗时都是当时的口径。当前口径（48k 池、30% = 14,400 条）见 `RESULTS.md` 与 `docs/PROTOCOL.md`。保留本文只为追溯当时的决策过程，**不要拿这里的数字写论文**。

**一句话**：把训练池从 12,000 放大到 24,000，跑 12 个 run，看"激活选择 vs 朴素随机"的差距会不会拉开。

---

## 为什么只改池子、不改 epoch

上一轮的结论是"削减 70% 数据等效成立，但选择算法相对随机没有可检测优势（+0.46pp，p=0.166，符号翻转）"。

主流的解释有两个：

1. **池子太小、冗余不够**：12k 条里语义近重复只有 ~3%，随机抽 3,600 条已经很"干净"，选择算法没多少可省的。
2. **欠拟合**：只训 1 epoch，全量本身就在天花板下方，选择算法带来的微小差异被压住了。

对应两种改法：放大池子 / 加 epoch。**一晚上只能选一个**：

| 方案 | full 单次 | 12 run 总计 | 是否装得下一夜 |
|---|---|---|---|
| 池子 24k，1 epoch | ~66 min | **~6.3 h** | ✅ |
| 池子 12k，3 epoch | ~100 min | ~13 h | ❌ |

所以这轮跑 **24k 池 + 1 epoch**。3 epoch 留到下一轮（如果 24k 有效，3 epoch 才值得花时间）。

---

## 怎么跑（一条命令）

```powershell
.venv\Scripts\python.exe tools\run_scale.py --dry-run   # 只打印，不动文件
.venv\Scripts\python.exe tools\run_scale.py             # 真跑，约 6.3 h
```

`run_scale.py` 会依次做：

| 步骤 | 命令 | 耗时 |
|---|---|---|
| 0 | 归档上一轮产物 → `results_round1_12k/`、`data/subsets_round1_12k/`、`data/processed_round1_12k/`、`cache/acts_round1_12k/`、`models/adapters_round1_12k/` | 秒级 |
| 1 | `prepare_data.py --pool domain`（`DATADIET_N_TRAIN=24000`） | ~1 min |
| 2–3 | `collect_acts.py --split train / probe` | ~13 min |
| 4 | `select_subset.py` | ~2 min |
| 5 | `tools/make_randlen.py` | ~1 min |
| 6 | `tools/night_queue.py --plan scale`（12 run） | **~6.3 h** |
| 收尾 | `report_numbers` → `Rscript R\run_all.R` → `make_table1` → `make_audit` → `audit_final` | ~2 min |

**为什么归档而不是加前缀**：R 脚本和所有审计工具都默认读 `results/`，归档后零改动、不会和上一轮撞 exp_id。要回头看第一轮，直接进 `results_round1_12k/`。

**关掉的东西**：这轮不跑 `nait_dedup`（去重只删 0.9%，等于同臂）、不跑剂量曲线（12k 那轮已有五档）、不跑 10%/50%/70%（结论已定）。

---

## 跑完怎么判（先写死，避免事后挑指标）

看 Table 2 里 `nait − random` 在 30% 档的两行：

| 结果 | 结论 | 怎么写 |
|---|---|---|
| Δ ≥ +1pp 且 6/6 或 3/3 同号，p<0.05 | 选择算法在更大池子上有效 | 主结论升级为"激活选择优于随机"，池子规模作为关键变量写进正文 |
| Δ 在 0±0.5pp，符号仍翻转 | 选择算法在这套数据上确实没有增量 | 结论维持"无可检测优势"，把"池子规模"写进 limitation（已试过 24k，不是没试） |
| Δ ≤ −1pp 且同号 | 选择算法反而有害 | 更值得写：报告"激活选择在 in-domain MCQ 上偏向长/难样本，反而伤基线" |

无论哪种，**12k 与 24k 的对比本身就是论文里的一张表**（削减比例 vs 池子规模 vs 掉点），这比单个数字更有信息量。

---

## 需要人做的事

1. **等另一个工作区的 QQ 机器人跑完**（它占着 GPU），确认机器空闲；
2. **插上电源**（电池模式下功耗被压到 40 W，吞吐掉 3–10 倍，这个坑踩过）；
3. 关掉不必要的 GPU 程序（QQ/浏览器硬件加速会挤显存）；
4. 双击或命令行启动后，别锁屏休眠：`powercfg /change standby-timeout-ac 0`。

---

## 已知风险

- **显存**：24k 池不改变单样本长度，bs=4/512 的峰值仍是 7.3 GiB，与 12k 时相同，不需要调 bs。
- **时间**：66 min/run 是按 12k 实测 33 min 线性外推；如果 full 超过 80 min，说明有别的进程抢算力，先查 `nvidia-smi`。
- **归档不可逆**：如果 `results_round1_12k` 已存在，脚本会直接退出而不是覆盖——这是故意的。
