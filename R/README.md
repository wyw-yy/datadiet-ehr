# R 分析层 · 使用说明

这一层只做一件事：**把 Python 跑出来的逐题预测，变成论文里能站住的统计结论**。
它不参与训练，不碰 GPU，也不读 `runs/` 里的中间文件——只认 `results/` 下五个约定文件。

**零依赖**：只用 base R（`read.csv` / `aggregate` / `binom.test` / `png` 手绘）。
这台机器的 shell 连不上 CRAN，所以刻意不写 `library(dplyr)` 之类的调用；
换任何一台新装 R 的 Windows 都能直接跑。

## 一条命令

```powershell
cd C:\Users\yang'yu\Desktop\codetest\datadiet-ehr
& "C:\Program Files\R\R-4.6.1\bin\x64\Rscript.exe" "R/run_all.R"
```

现在跑的是**假数据**（`R/99_make_demo_data.R` 生成的 210 个 run，约 12 秒），
用来定死统计口径与图表版式。

## 切到真实数据（三步）

1. 删掉 `R/99_make_demo_data.R` 的调用（`R/run_all.R` 里第一行 `steps`）；
2. 打开 `R/00_setup.R`，把 `RESULTS <- file.path(PROJ, "results", "demo")` 改成 `file.path(PROJ, "results")`；
3. 确保 Python 侧按下面的字段写文件（列名不要改，改了先改 `PLAN.md` §2.5 的表）：

| 文件 | 必需列 |
|---|---|
| `results/metrics_long.csv` | `exp_id, method, ratio, seed, dept, task, metric, value, n` |
| `results/preds/<exp_id>.csv.gz` | `item_id, dept, y_true, y_pred, correct, score` |
| `results/compute.csv` | `exp_id, tokens_seen, gpu_hours, wall_s, peak_vram_gb, select_overhead_h` |

`exp_id` 的约定（`R/00_setup.R::exp_id`）：`<method>_r<保留百分比>_s<seed>_<task>`，
例如 `nait_r30_s2_medqa` = nait 方法、保留 30%、第 2 个种子、MedQA 任务。
**method 新增一个实验就多一个字符串，不要改列结构。**

## 每个脚本在算什么

| 脚本 | 统计口径 | 产物 |
|---|---|---|
| `00_setup.R` | δ = 0.02（2 个绝对点，理由见文件注释与 `PLAN.md` §0） | — |
| `01_equivalence.R` | 同一批测试题逐题配对 → 配对 bootstrap 95%CI → 精确 McNemar（`binom.test(b, b+c)`）→ TOST 等效性（CI 落在 ±δ 内即合格） | `eq_table.csv` |
| `02_curve.R` | 种子间 mean ± 1.96SE，画绝对准确率与相对全量的掉点 | `fig02_*.png` |
| `03_robustness.R` | r=0.30 时按科室分层，检验"某些科室是否被牺牲" | `robust.csv`、`fig04_dept.png` |
| `04_compute.R` | 净账 = 全量 −（子集训练 + 选择前向），并折算 ¥（2 元/GPU-h） | `compute_table.csv`、`fig05_compute.png` |

## 常见坑

- **`Rscript` 不在 PATH**：永远用全路径 `C:\Program Files\R\R-4.6.1\bin\x64\Rscript.exe`。
- **必须在项目根目录跑**：脚本用 `R/00_setup.R` 相对路径定位，且会检查 `R/` 是否存在。
- **中文文件别用 PowerShell 改**：`Set-Content` 可能把 UTF-8 写坏（本项目踩过一次），
  要改脚本就用编辑器或 RStudio 存成 UTF-8。
- **写 gz 连接要显式 `close()`**：用 `gzfile()` 内联传给 `write.csv()` 时，连接被 GC 回收会截断文件
  （本项目踩过，5/210 个文件损坏）。`99_make_demo_data.R` 里是正例。
- **PNG 中文会变方框**：图的标签一律用英文，中文只写在 Markdown/论文正文里。
