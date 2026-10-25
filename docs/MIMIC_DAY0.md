# 数据到手当天：两小时 runbook

前提：`docs/MIMIC_CHECKLIST.md` 里的账号与 DUA 已经办完，`data/raw/mimic/` 下有解压后的
`hosp/patients.csv.gz`、`hosp/admissions.csv.gz`、`hosp/diagnoses_icd.csv.gz`、
`hosp/discharge.csv.gz`（MIMIC-IV-Note）。

按顺序敲，每步都有**验收标准**；不达标就停，别往下走。

---

## 0. 五分钟自检（不碰数据）

```bat
check_env.bat
```

验收：GPU 一段绿、模型 9 个文件齐、verify 全绿。

## 1. 看数据长什么样（10 分钟，别急着转化）

```bat
python tools\inspect_mimic.py --src data\raw\mimic
```

验收：打印出四张表的行数、列名、`subject_id` 唯一值个数。
**记下三个数**：总病人数、有出院小结的病人数、小结平均字符数。
如果"有小结的病人"少于 200，直接停下找导师——样本量撑不起 30% 的对照。

## 2. 走一遍转换（15 分钟）

```bat
python prepare_mimic.py --src data\raw\mimic --out data\processed_mimic --n-probe 200 --n-eval 400
```

验收：终端打印 `rows: ... skipped_short: ...`，且
`data\processed_mimic\train.jsonl` / `probe.jsonl` / `mimic_eval.jsonl` 三份都非空。

**关键检查**（这一步最容易出问题）：

```bat
python tools\check_leak.py --proc data\processed_mimic
```

验收：`train ∩ eval = 0`、`train ∩ probe` 尽量接近 0。
**只要这一条不过，后面跑出来的所有分数都别信。**

## 3. 小样冒烟（20 分钟，占 GPU）

```bat
set DATADIET_N_TRAIN=2000
python run_one.py --smoke --method full --seed 1
```

验收：`step k/k` 正常打印、`[eval] ... acc=...` 有数字、`results\metrics_long.csv` 多两行。

## 4. 定规模（10 分钟，纯算）

- 看 `results\runs\full_s1.json` 的 `train_seconds` 与 `n_samples` → 每样本耗时 `s`
- 池子定多大：**一轮总时长 = 池子 × s × (1 + 3×0.3)**（full + 三个 30% 臂）
- 8 GB 笔记本的量级参考：24k 池、每样本 0.15 s → 一轮约 2.6 GPU-h

把最终池大小写进 `docs/PREREG.md` 的偏离记录（第 5 条），**先写再做**。

## 5. 采激活 + 选子集（40 分钟）

```bat
set DATADIET_N_TRAIN=<第 4 步定的数>
python tools\collect_acts.py --split train
python tools\collect_acts.py --split probe
python tools\select_subset.py --probe-split probe --suffix ""
python tools\make_randlen.py
python tools\el2n_scores.py
```

验收：`results\select_stats.json` 里
- `dedupe_kept_pct` 应在 90% 以上（若只有 15%，说明忘了去均值）；
- 随机对余弦 `pair_cos_p50` 应在 −0.05…0.05（若接近 1.0，同上）。

## 6. 开跑（夜里）

```bat
python tools\night_queue.py --plan scale
```

## 7. 早上收尾

```bat
finish_round.bat
```

---

## 出问题时的对照表

| 现象 | 八成原因 | 处理 |
|---|---|---|
| `skipped_short: 全部` | CSV 里的换行被压平（我们踩过：写 CSV 时 `\n`→空格） | 检查原始 `discharge.csv.gz`：一份小结应该是多行 |
| 科室全是 other | ICD 列名不对（`icd_code` vs `icd9_code`） | 用第 1 步的列名核对 `icd_to_dept` 的输入 |
| `train ∩ eval > 0` | 没按 `subject_id` 切（按行切了） | 重跑第 2 步，别手工改 |
| 显存 OOM | 别的程序占了 GPU | `nvidia-smi`；笔记本**必须插电**（电池模式功耗上限 40 W，吞吐掉 3–10 倍） |
| 训练 200 MHz / 30 W | 同上，或 `powercfg` 省电模式 | 插电 + 高性能电源方案 |
| `dedupe_kept_pct ≈ 15%` | 激活没减去池内均值 | 检查 `nait_scores()` 的 `center()` |
