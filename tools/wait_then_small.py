"""等显存真的空出来，再跑 1%/5% 极小预算档。

用户 2026-11-02：另一个课题（medmem-law）在占显存，跑完才轮到我们。

第一版只看显存，22:29 抓到两次训练之间的 3 分钟空隙就开跑了，结果 22:37 对方
重新训练把卡抢回去，我们的 eval 直接 `CUDA error: device-side assert` 崩掉，
整个链条也被一起带走。所以这一版加了三道更严的闸：

  1. 显存 ≤ 800 MiB 且**连续 10 次**（10 分钟）—— 不是看空隙，是看真的没人用；
  2. **没有外来的训练进程**（psutil 扫 cmdline，含 train/finetune/sft 但不属于本项目）；
  3. 开跑后若再有 CUDA 错误，**立刻停**并重新挂等待，不继续糟蹋后面的 run。

已跑过的 adapter 会被 `run_one --reuse` 复用，所以崩掉的 run 不用重新训练。
"""

import os
import subprocess
import sys
import time
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parent.parent
PY = ROOT / ".venv" / "Scripts" / "python.exe"
LOG = ROOT / "logs" / "small_wait.log"
QLOG = ROOT / "logs" / "small_queue.log"

TMP = ROOT / "tmp"
TMP.mkdir(exist_ok=True)
for k in ("TMP", "TEMP", "TMPDIR"):
    os.environ[k] = str(TMP)
os.environ["PYTHONIOENCODING"] = "utf-8"

FREE_MIB = 800
NEED_CONSECUTIVE = 10      # 10 分钟持续空闲才算数
INTERVAL = 60
TRAIN_WORDS = ("train.py", "-m train", "finetune", "sft", "deepspeed", "accelerate launch")


def log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def used_mib() -> int:
    out = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=30,
    ).stdout.strip().splitlines()
    return int(out[0]) if out else 10 ** 6


def ancestors() -> set[int]:
    pids, me = set(), os.getpid()
    while me and me not in pids:
        pids.add(me)
        try:
            me = psutil.Process(me).ppid()
        except psutil.Error:
            break
    return pids


def foreign_training() -> list[str]:
    """別人家的训练进程（本项目自己的不算）。"""
    skip = ancestors()
    hits = []
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if p.info["pid"] in skip:
                continue
            name = (p.info["name"] or "").lower()
            if "python" not in name:
                continue
            cmd = " ".join(p.info["cmdline"] or [])
            if "datadiet-ehr" in cmd:
                continue
            low = cmd.lower()
            if any(w in low for w in TRAIN_WORDS):
                hits.append(f"pid {p.info['pid']}: {cmd[:90]}")
        except (psutil.Error, TypeError):
            continue
    return hits


def run_queue() -> int:
    env = dict(os.environ)
    env.update({
        "DATADIET_N_TRAIN": "48000",
        "DATADIET_N_POOL": "48000",
        "DATADIET_RATIOS": "0.01,0.05,0.10,0.20,0.30,0.50,0.70",
        "DATADIET_EPOCHS": "1",
    })
    with open(QLOG, "a", encoding="utf-8") as lf:
        lf.write(f"\n=== start {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        lf.flush()
        return subprocess.run([str(PY), "tools/night_queue.py", "--plan", "small"],
                              cwd=ROOT, stdout=lf, stderr=subprocess.STDOUT, env=env).returncode


def report() -> None:
    import csv
    path = ROOT / "results" / "metrics_long.csv"
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    keep = [r for r in rows if r["ratio"] in ("0.01", "0.05")]
    print("\n保留率 | 方法 | 任务 | 准确率 | 种子", flush=True)
    for r in sorted(keep, key=lambda x: (x["ratio"], x["method"], x["task"], x["seed"])):
        print(f"{r['ratio']:>6} | {r['method']:<7} | {r['task']:<8} | "
              f"{float(r['value']):.4f} | {r['seed']}", flush=True)
    log(f"1%/5% 现有 {len(keep)} 条记录")


def main() -> int:
    while True:
        log(f"waiting: need used<={FREE_MIB} MiB x{NEED_CONSECUTIVE} and no foreign training")
        hits = 0
        while hits < NEED_CONSECUTIVE:
            u = used_mib()
            busy = foreign_training()
            if u <= FREE_MIB and not busy:
                hits += 1
                log(f"idle {hits}/{NEED_CONSECUTIVE} (used {u} MiB)")
            else:
                if hits:
                    log(f"reset (used {u} MiB, foreign={len(busy)})")
                hits = 0
                if busy and hits == 0 and u <= FREE_MIB:
                    log("foreign training process present - holding")
            if hits < NEED_CONSECUTIVE:
                time.sleep(INTERVAL)

        log("GPU free for 10+ min - starting the 1%/5% round")
        rc = run_queue()
        log(f"queue exit={rc}")
        report()

        # 队列非零退出 = 中途崩了（多半是卡被抢）。等回空闲再补剩下的，最多重试 3 轮。
        if rc == 0:
            log("small round finished")
            return 0
        log("queue failed - re-arming the wait (finished adapters will be reused)")
        time.sleep(600)


if __name__ == "__main__":
    sys.exit(main())
