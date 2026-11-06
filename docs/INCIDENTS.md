# 事故记录（Incident log）

只记"会重复发生、且已经浪费过时间"的事故。每条写清：症状、根因、修法、下次怎么防。

---

## 2026-11-05 01:57 — 批次被会话重启连坐，空转 15.5 h

**症状**：`logs/rigor.log` 停在 `01:50 start random_r30_s18`，s18 训练日志停在 `step 320/1800`，没有 traceback；GPU 空闲；"跑完关机"的看门狗也没留下任何记录。

**根因**：这批 run 和关机看门狗都是 DSH 会话后台 job 的子进程。会话重启 → job 对象被回收 → 整棵进程树被杀。看门狗同样在树里，所以既没继续跑也没关机。

**修法**：长任务用 WMI 启动（父进程挂在 WmiPrvSE 侧，不在 DSH job 对象里）：

```powershell
Invoke-CimMethod -ClassName Win32_Process -MethodName Create `
  -Arguments @{CommandLine='cmd /c cd /d D:\code\codetest\datadiet-ehr && .venv\Scripts\python.exe tools\resume_rigor.py >> logs\resume_stdout.log 2>&1'}
```

**坑**：`schtasks` 在这台机器上建得成功、`/run` 也返回成功，但 `Last Result: 1`、日志从不生成，别再用。

---

## 2026-11-05 22:43 — 显卡驱动重置 → CUDA 调用卡死 → 静默失败 18 h

**症状**：`random_r30_s16`、`rand_len_r30_s4/s5`、`nait_dedup s2–s5`、`el2n s2–s4` 共 10 个 run 在 00:12–00:13 各用 0.6–1.3 分钟全部失败，签名统一为 `torch.AcceleratorError: CUDA error: out of memory`，栈顶在梯度检查点的 `fork_rng` → `set_rng_state`。之后机器空转到次日 18:00。

**根因**：22:36–00:13 系统日志里 `nvlddmkm` 事件 153 刷了二十多次（显卡驱动反复重置）。22:43 起的 `run_one/train.py`（el2n s3）卡在 CUDA 调用里**既不返回也不退出**，于是：

1. 后续每个 run 都拿不到可用显存 → 秒挂 OOM；
2. `post_rigor` 的存活判据是"resume 进程还在不在"，卡死进程一直"在"，于是它一直等，永远不触发完整性闸门。

**修法**（`tools/post_rigor.py`）：

- 判活改成**看日志有没有往前走**：`--stall-minutes 75`，超时就 kill 整棵 resume 树并重拉；
- 每 `--heartbeat-minutes 10` 打一行 `heartbeat: alive=... missing=.../25`，不再静默；
- `resume finished` 只认**最后一行**（整文件搜索会被上一轮的旧记录骗到，18:02 就撞过一次）。

**恢复步骤**（下次照做）：`taskkill /PID <卡死进程> /T /F` 清干净 → `nvidia-smi` 确认显存归零 → 跑一个 512×512 bf16 matmul 确认 GPU 真能用 → 再重启批次。实测杀干净后 GPU 立刻恢复（0 MiB / 47 MiB，matmul 通过）。

**教训**：判活不能只看"进程在不在"。对 CUDA 程序，进程活着但 GPU 已经废掉是最常见的中间态。

---

## 2026-11-05 17:36 — `eval.py` 整批 OOM

**症状**：`torch.log_softmax(logits, dim=-1)[:, opt_ids]` 在 bs=16、max_len=1024 时对 (16, 1024, 151936) 求 softmax，bf16 约 5 GB，8 GB 卡直接炸；17 个 run 的评测全废。

**修法**：`logits_to_keep=1`（只保留最后位置）+ 先切四个选项再 softmax（`logits[:, opt_ids]`）+ `score_chunk` 捕获 `torch.cuda.OutOfMemoryError` 后把 bs 减半递归重试。

**副作用（已记录在 `docs/API.md`）**：`pA..pD` 的归一化范围前后不一致（旧文件是整个词表、新文件是 A–D 内部）。argmax 与 `pred/correct` 不受影响，但做置信度/ECE 必须重新评测。

## 事故 4：我自己把分配器改坏了（2026-11-05 22:00 → 11-06 18:15）

**症状**：11-06 18:05 之后，所有 `bs4` 的 run 都在第 1 个训练步 OOM，而 18:05 之前 15 个
run 用同样参数全部正常。

**根因**：为了治 `s16` 的 OOM，我在 `train.py` 顶部加了
`os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "max_split_size_mb:128")`。
`max_split_size_mb` 会**禁止大于 128 MB 的单块分配**，而这张卡上一次 logits 分配就要几百 MB，
等于把大块切碎——于是所有 run 都崩。它不是"减少碎片"，而是"禁止大块"。

**修法**：整段回滚，并在原位置留注释说明为什么不能再加。显存不够时唯一的正确做法是
降 `--bs`（`run_one.py --bs 2` 会自动把 `--grad-accum` 翻倍，保持等效 batch 8）。

**教训**：在没有 A/B 对照的情况下改分配器参数，会把"个别样本 OOM"变成"全部样本 OOM"，
而且症状完全一样，极易误判成硬件故障。改性能/内存相关开关必须一次只改一个变量，
并先跑 10 步验证。
