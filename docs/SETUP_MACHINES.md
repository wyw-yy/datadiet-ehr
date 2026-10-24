# 第二、三台机器怎么接进来

> 结论先说：**现在不用弄。** 单机跑完整个矩阵约 7 小时，一晚上就完了；
> 只有当你想把 7 小时压到 2.5 小时，才需要 B/C。
> 这份文档是"真的要用"时的操作手册，别提前折腾。

---

## 0. 先回答三个问题（决定能不能用）

在**空白机器**上开一个 cmd，粘这三行：

```bat
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv
python --version
wmic logicaldisk where "DeviceID='C:'" get FreeSpace
```

对照这张表：

| 检查项 | 要求 | 不满足会怎样 |
|---|---|---|
| GPU | **NVIDIA，显存 ≥ 6 GB** | 没有 N 卡 = 完全不能参与训练（CPU 训练要慢 50 倍） |
| 驱动 | ≥ 550（支持 CUDA 12.x） | 装不了 cu128 的 torch |
| Python | **3.12**（必须与 A 机同小版本） | 轮子对不上，装不了 |
| C 盘 | ≥ 12 GB 空闲 | 装到一半失败 |

GPU 显存 6–8 GB：能跑，但只能用 `--bs 2`（慢一点，结果一样）。
显存 ≥ 12 GB：能跑 3B 模型，甚至比 A 机更快。

---

## 1. 迁移包怎么做（在 A 机上，三条命令）

A 机 = 你现在这台，环境已好、数据已好、模型已好。

```bat
:: ① 生成离线 wheelhouse（约 400 MB + 2.5 GB 的 torch 轮子）
tools\build_wheelhouse.bat
```

```bat
:: ② 把项目复制到 U 盘 / 局域网共享（排除 .venv 和各台机器不需要的大件）
robocopy "C:\Users\yang'yu\Desktop\codetest\datadiet-ehr" "E:\datadiet-ehr" /E ^
  /XD ".venv" "__pycache__" "cache\acts" "data\raw" "results\preds" ^
  /XF "*.log" "*.zip"
```

> `cache\acts`（200 MB 激活）**不用复制**——激活只在 A 机采集，
> 子集名单（`data/subsets/subsets.json`，几 MB）复制过去就够了。

```bat
:: ③ 检查包里的关键文件在不在
dir "E:\datadiet-ehr\data\processed"      :: 应有 train/probe/medqa/medmcqa.jsonl
dir "E:\datadiet-ehr\data\subsets"        :: 应有 subsets.json
dir "E:\datadiet-ehr\models\Qwen2.5-1.5B-Instruct"  :: 应有 model.safetensors
dir "E:\datadiet-ehr\wheelhouse"          :: 应有几十个 .whl
```

整个包约 **4 GB**（模型 3.1 GB + 依赖轮子 0.4 GB + 数据 20 MB）。

---

## 2. 在 B / C 上装（双击一次）

把包拷到 B 机，比如 `D:\datadiet-ehr`，然后**双击 `setup_new_machine.bat`**。

它会自动：建 venv → 离线装 torch → 离线装依赖 → 打印 GPU 与版本。
**全程不需要联网**，约 6–10 分钟（U 盘速度决定）。

最后看到：

```
torch 2.11.0+cu128
gpu NVIDIA GeForce RTX ...
cap (8, 6)          ← 你的卡是什么就是什么，不必和 A 一样
transformers 5.20.2
cuda_ok True
```

---

## 3. 验收（关键，别跳过）

```bat
.venv\Scripts\python.exe tools\verify.py
```

**必须 20 项全绿**。任何一项红，说明数据包不完整，别开始训练。

再确认一件事——三台机器的**版本必须完全一致**：

```bat
.venv\Scripts\python.exe -m pip freeze | findstr /i "torch transformers peft datasets"
```

三台的输出应该一模一样。不一致 = 结果不可比，宁可只在一台上跑。

---

## 4. 分工纪律（三条铁律，违反就等于白跑）

### 铁律一：只有 A 机做采集和选子集

`collect_acts.py` 与 `select_subset.py` **只跑一次**（在 A 机上）。
三台各自算一遍激活，得到的子集可能有微小差异，实验就不可比。

### 铁律二：按 **seed** 切分，不按方法切

| 机器 | 分到的 seed |
|---|---|
| A | seed 1 |
| B | seed 2 |
| C | seed 3 |

**为什么**：如果 A 只跑 `nait`、B 只跑 `random`，那么"机器差异"和"方法差异"混在一起，
审稿人会问"你怎么知道是方法好还是那张显卡好"。按 seed 切，每台机器都跑所有方法，噪声就被平摊了。

### 铁律三：每条命令带 `--tag`，记下是哪台机器跑的

```bat
.venv\Scripts\python.exe run_one.py --method nait --ratio 0.30 --seed 2 --epochs 1 --tag machineB
```

`--tag` 会写进结果表，将来可以做"设备效应"的敏感性检查（如果 B 机器整体偏高 2 个点，
你能立刻发现并排除）。

---

## 5. 具体怎么分配任务

矩阵是 27 个 run（3 方法 × 5 比例 + full 的 3 个 seed + nait 的额外 seed）。

**A 机**（现在这台）：

```bat
.venv\Scripts\python.exe run_one.py --method full   --seed 1 --epochs 1 --tag A
.venv\Scripts\python.exe run_one.py --method full   --seed 2 --epochs 1 --tag A
.venv\Scripts\python.exe run_one.py --method nait   --ratio 0.10 --seed 1 --epochs 1 --tag A
.venv\Scripts\python.exe run_one.py --method nait   --ratio 0.20 --seed 1 --epochs 1 --tag A
.venv\Scripts\python.exe run_one.py --method nait   --ratio 0.30 --seed 1 --epochs 1 --tag A
.venv\Scripts\python.exe run_one.py --method nait   --ratio 0.50 --seed 1 --epochs 1 --tag A
.venv\Scripts\python.exe run_one.py --method nait   --ratio 0.70 --seed 1 --epochs 1 --tag A
```

**B 机**：把上面 `nait` 换成 `nait_dedup`，`--tag B`。
**C 机**：把 `nait` 换成 `random`，`--tag C`。

> 这个分法是"方法切"——**只在方法之间互不共享 seed 时才可接受**。
> 更规范的做法是三台都跑全部方法、各跑不同 seed；
> 折中方案：A 跑 seed1 的全部方法 + seed2 的 full，B/C 跑 seed2/3 的关键几档。
> 如果时间够，用前者。

---

## 6. 结果怎么合

三台各自把 `results\` 下的三个文件拷回 A 机：

```
metrics_long.csv
compute.csv
preds\*.csv.gz
```

放到 A 机同名位置——`run_one.py` 用的是 **upsert**（按 exp_id 覆盖/追加），
所以直接覆盖合并就行，不会重复不会串。

然后 A 机上：

```bat
.venv\Scripts\python.exe tools\verify.py
"C:\Program Files\R\R-4.6.1\bin\x64\Rscript.exe" R\run_all.R
```

---

## 7. 常见坑

| 现象 | 原因 | 处理 |
|---|---|---|
| `setup_new_machine.bat` 报 `need Python 3.12 exactly` | 装了 3.13 或 3.11 | 卸了重装 3.12（轮子是 cp312） |
| `no torch wheel in wheelhouse\` | 打包时漏了 2.5 GB 那个文件 | 手动拷 `torch-2.11.0+cu128-cp312-...whl` 进去 |
| 装完 `cuda_ok False` | 显卡驱动太老 | 更新驱动到 550+ |
| 训练比 A 机慢一倍 | 显存小，触发了换页 | 加 `--bs 2`，显存占用减半 |
| 结果表出现两行同一个 exp_id | 两台机器跑了同一个 seed | 正常，upsert 会覆盖；但说明分工写错了 |
| `CUDA out of memory` | 6 GB 卡跑默认 bs=4 | `--bs 2 --grad-accum 4` |

---

## 8. 一句话

**现在别弄。** 今天先把 A 机的 3 个 pilot 跑完看结论；
如果结论成立、要铺 27 个 run，再花 20 分钟打迁移包、20 分钟装 B/C。
