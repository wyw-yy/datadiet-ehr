"""resume_rigor.py —— 把 2026-11-05 凌晨断掉的那批补齐（v2：抗卡死）。

一晚踩过的两个坑，这个版本都堵上：

1. **CUDA 调用卡死**（2026-11-05 22:43，显卡驱动重置后 `train.py` 卡在
   `fork_rng` 里不返回也不退出）→ 每个 run 有硬超时 `--per-run-min`，
   超时就 kill 整棵树、记为失败、继续下一个，不让整批停住。
2. **OOM 一次就放弃**（s16 连挂三次）→ 失败后用更小 batch 再来一次
   （`--bs 2`），再失败才记失败。

另外每次开跑前做一次 GPU 体检（256×256 bf16 matmul）：
显卡处于重置后的坏状态时，这一步会立刻失败，于是等 5 分钟重试，
而不是让训练进程半死不活地占着卡。

进度同时写 `logs/status.txt`（一行，带 ETA），方便一眼看状态。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parent.parent
PY = ROOT / ".venv" / "Scripts" / "python.exe"
LOG = ROOT / "logs" / "resume.log"
STATUS = ROOT / "logs" / "status.txt"
TASKS = ("medmcqa", "medqa")

PLAN: list[tuple[str, float, int]] = []
PLAN += [("random", 0.30, s) for s in range(7, 21)]
PLAN += [("rand_len", 0.30, s) for s in range(2, 6)]
PLAN += [("nait_dedup", 0.30, s) for s in range(2, 6)]
PLAN += [("el2n", 0.30, s) for s in range(2, 5)]

ENV = dict(os.environ)
ENV.update({
    "PYTHONIOENCODING": "utf-8",
    "DATADIET_N_TRAIN": "48000",
    "DATADIET_N_POOL": "48000",
    "DATADIET_EPOCHS": "1",
    "DATADIET_RATIOS": "0.01,0.05,0.10,0.20,0.30,0.50,0.70",
    "TMP": str(ROOT / "tmp"), "TEMP": str(ROOT / "tmp"), "TMPDIR": str(ROOT / "tmp"),
})


def eid(method: str, ratio: float, seed: int) -> str:
    return f"{method}_r{int(round(ratio * 100)):02d}_s{seed}"


def log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def status(text: str) -> None:
    STATUS.write_text(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {text}\n", encoding="utf-8")


def have_preds(e: str) -> bool:
    return all((ROOT / "results" / "preds" / f"{e}_{t}.csv.gz").exists() for t in TASKS)


def gpu_ok(timeout: int = 180) -> bool:
    """显卡还能不能算。驱动刚重置过时这里会失败。"""
    code = ("import torch;a=torch.randn(256,256,device='cuda',dtype=torch.bfloat16);"
            "print(float((a@a).sum()))")
    try:
        r = subprocess.run([str(PY), "-c", code], cwd=ROOT, env=ENV,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=timeout)
        return r.returncode == 0
    except subprocess.TimeoutExpired:
        return False


def kill_tree(p: psutil.Process) -> None:
    try:
        for ch in p.children(recursive=True):
            try:
                ch.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        p.kill()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass


def run_one(e: str, m: str, r: float, s: int, bs: int | None, timeout_min: float,
            attempt: str) -> int:
    """跑一个 run，带硬超时。返回 rc（-9 表示超时被杀）。"""
    cmd = [str(PY), "run_one.py", "--method", m, "--ratio", str(r),
           "--seed", str(s), "--epochs", "1", "--reuse"]
    if bs:
        cmd += ["--bs", str(bs)]
    logfile = ROOT / "logs" / f"resume_{e}{attempt}.log"
    with open(logfile, "w", encoding="utf-8") as lf:
        p = subprocess.Popen(cmd, cwd=ROOT, env=ENV, stdout=lf, stderr=subprocess.STDOUT)
        t0 = time.time()
        while True:
            if p.poll() is not None:
                return p.returncode
            if (time.time() - t0) / 60.0 > timeout_min:
                log(f"{e}: wall-clock timeout {timeout_min:.0f} min -> kill tree")
                try:
                    kill_tree(psutil.Process(p.pid))
                except psutil.NoSuchProcess:
                    pass
                p.wait(timeout=60)
                return -9
            time.sleep(15)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-run-min", type=float, default=110.0)
    ap.add_argument("--gpu-wait-min", type=float, default=20.0)
    a = ap.parse_args()

    todo = [(m, r, s) for (m, r, s) in PLAN if not have_preds(eid(m, r, s))]
    log(f"resume up: {len(PLAN)} planned, {len(PLAN) - len(todo)} already done, {len(todo)} todo")
    ok, fails = 0, []
    t0 = time.time()
    done_times: list[float] = []

    for i, (m, r, s) in enumerate(todo, 1):
        e = eid(m, r, s)

        # 开跑前体检：卡坏了就等，别让训练进程半死不活
        waited = 0.0
        while not gpu_ok():
            if waited >= a.gpu_wait_min:
                log(f"{e}: GPU still unhealthy after {a.gpu_wait_min:.0f} min -> mark failed")
                break
            log("GPU not usable right now; waiting 5 min before retry")
            time.sleep(300)
            waited += 5
        else:
            waited = None
        if waited is not None:
            fails.append(e)
            continue

        eta = ""
        if done_times:
            avg = sum(done_times) / len(done_times)
            eta = f" eta ~{(avg * (len(todo) - i + 1)) / 60:.1f} h"
        log(f"[{i}/{len(todo)}] start {e}  (elapsed {(time.time() - t0) / 3600:.1f} h{eta})")
        status(f"{i}/{len(todo)} running {e} elapsed={(time.time() - t0) / 3600:.1f}h{eta}")

        t1 = time.time()
        rc = run_one(e, m, r, s, None, a.per_run_min, "")
        if rc != 0 or not have_preds(e):
            log(f"{e}: rc={rc}, retrying once with --bs 2")
            rc = run_one(e, m, r, s, 2, a.per_run_min, "_bs2")

        dt = (time.time() - t1) / 60
        if rc == 0 and have_preds(e):
            ok += 1
            done_times.append(dt)
            log(f"{e}: ok in {dt:.1f} min")
        else:
            fails.append(e)
            log(f"{e}: FAILED rc={rc} in {dt:.1f} min (see logs/resume_{e}*.log)")

    log(f"resume finished: ok={ok} failed={len(fails)} {fails if fails else ''}")
    status(f"finished ok={ok} failed={len(fails)}")
    if fails:
        sys.exit(1)


if __name__ == "__main__":
    main()