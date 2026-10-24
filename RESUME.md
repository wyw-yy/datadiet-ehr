# 明天从哪继续（RESUME）

> 写于 2026-10-22 21:15，因为你今晚要断电关机。
> 现在的状态：**数据、激活、子集全部做完并校验通过；训练只差跑。**
> 断电前已做的保护：训练进程已停止、半成品 adapter 已删除、数据完整性校验 **20 项全过**。

---

## 一、今晚已经彻底完成的东西（关机不会丢）

| 产物 | 大小 | 说明 |
|---|---|---|
| `data/processed/train.jsonl` | 12.5 MB | 12,000 条训练样本 |
| `data/processed/probe.jsonl` | 2.1 MB | 2,000 条定方向样本（与训练集零重叠） |
| `data/processed/medqa.jsonl` | 1.2 MB | 1,273 道考卷 |
| `data/processed/medmcqa.jsonl` | 1 MB | 4,183 道考卷 |
| `cache/acts/acts_train.npz` | 165.5 MB | 12,000 × 5 层 × 1536 维激活 |
| `cache/acts/acts_probe.npz` | 27.6 MB | 2,000 条激活 |
| `data/subsets/subsets.json` | 很小 | 五档子集，30% = 3,600 条 |
| `results/select_stats.json` | 很小 | 选择过程中的所有审计数字 |
| `cache/sft_full_s1_*.pt` | 21 MB | **分词缓存**，明天跑 full 能省约 4 分钟 |
| `models/Qwen2.5-1.5B-Instruct/` | 3.1 GB | 基座模型 |

**已清理**：今晚冒烟测试的假结果（200 条训练出的 adapter、`metrics_long.csv` 里两行 smoke 记录）已删除，备份在 `results/metrics_smoke_backup.csv`。所以明天跑出来的第一个数字就是干净的真数据。

---

## 二、明天开机后，照着做

### 第 0 步：确认环境还在

```bat
cd C:\Users\yang'yu\Desktop\codetest\datadiet-ehr
.venv\Scripts\activate
python -c "import torch;print(torch.cuda.get_device_capability())"
```

要打印 `(12, 0)`。然后跑一次体检（20 项应该全绿）：

```bat
.venv\Scripts\python.exe tools\verify.py
```

### 第 1 步：跑三个 pilot（这是唯一没做完的事）

复制这三行，等它跑完（合计约 1 小时 25 分）：

```bat
.venv\Scripts\python.exe run_one.py --method full --seed 1 --epochs 1
.venv\Scripts\python.exe run_one.py --method nait --ratio 0.30 --seed 1 --epochs 1
.venv\Scripts\python.exe run_one.py --method random --ratio 0.30 --seed 1 --epochs 1
```

想一次跑完不守着，用这个（后台跑，日志写进 pilot.log）：

```bat
powershell -NoProfile -Command "& '.\.venv\Scripts\python.exe' -u run_one.py --method full --seed 1 --epochs 1 *> pilot.log; & '.\.venv\Scripts\python.exe' -u run_one.py --method nait --ratio 0.30 --seed 1 --epochs 1 *>> pilot.log; & '.\.venv\Scripts\python.exe' -u run_one.py --method random --ratio 0.30 --seed 1 --epochs 1 *>> pilot.log"
```

进度窗口（在另一个窗口里看进度，关掉不影响）：

```bat
powershell -NoProfile -ExecutionPolicy Bypass -File tools\progress.ps1 -Config tools\progress_pilot.json
```

**预期耗时**（实测 3.8–4.5 样本/秒）：
- full 12,000 条 → 约 50 分钟
- nait 3,600 条 → 约 16 分钟
- random 3,600 条 → 约 16 分钟

### 第 2 步：看结果

```bat
type results\metrics_long.csv
```

应该出现 6 行（3 个 run × 2 张考卷）。核心看 **nait 相对 full 差几个百分点**。

---

## 三、结果出来后的三种走法（`PLAN.md` §0 已经定好，不临时改口）

| nait@30% 相对 full | 结论 | 下一步 |
|---|---|---|
| 差 ≤ 2pp | **主命题成立**，可以铺矩阵写论文 | 跑 B 方案（见下） |
| 差 2–3pp | 边缘，需要更大比例或改进选择 | 先跑 nait@50% 看拐点 |
| 差 > 3pp | 假设不成立 | 改选择策略（换层、换质心定义），或把结论改成"冗余度报告" |

**B 方案（铺矩阵）**：`full × 3 seeds` + `{random,nait,nait_dedup} × {10,20,30,50,70}% × seed 1` + `nait@30% × seed 2,3`，约 27 个 run，12–16 小时。

---

## 四、如果哪一步报错

| 症状 | 命令 |
|---|---|
| 想知道现在到底坏了没 | `.venv\Scripts\python.exe tools\verify.py` |
| 断了重跑某个 run | 同一条 `run_one.py` 命令，加 `--reuse` 可跳过已训好的 adapter |
| 断在两处之间、结果表有半行 | 删掉 `results/runs/<exp_id>.json` 对应行后重跑，`metrics_long.csv` 会自动 upsert |
| 显存不够 | 加 `--max-len 384` 或 `--bs 2` |
| 全部重来 | 只需重跑 `collect_acts.py` 与 `select_subset.py`（各 7 分钟），数据不用重下 |

---

## 五、当前进度一句话

**10 步走完 8 步（环境、模型、数据、清洗、脚本、冒烟、激活、选子集），只剩"训练 + 评分"和"R 出图"。**
所有原料都齐了，明天开机只要跑那三行命令。
