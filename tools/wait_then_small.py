"""等显存空出来，再跑 1%/5% 极小预算档。

用户 2026-11-02：另一个课题的训练在占显存（约 7 GB / 8 GB），跑完才能轮到我们。
所以这里只做一件事：每 60 秒看一次显存，连续 3 次都 ≤ 800 MiB 才开跑。

开跑后依次：
  1. night_queue --plan small   （nait / random × 1% / 5% × 2 seeds = 8 run）
  2. 打印每个臂的准确率（直接读 metrics_long.csv，不依赖 R）
日志：logs/small_wait.log、logs/small_queue.log
"""

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = ROOT / ".venv" / "Scripts" / "python.exe"
LOG = ROOT / "logs" / "small_wait.log"
QLOG = ROOT / "logs" / "small_queue.log"

TMP = ROOT / "tmp"
TMP.mkdir(exist_ok=True)
for k in ("TMP", "TEMP", "TMPDIR"):
    os.environ[k] = str(TMP)
os.environ["PYTHONIOENCODING"] = "utf-8"

FREE_MIB = 800          # 显存占用低于这个值才算空
NEED_CONSECUTIVE = 3    # 连续几次
INTERVAL = 60           # 秒


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


def main() -> int:
    log(f"small-round watcher up (need used<={FREE_MIB} MiB x{NEED_CONSECUTIVE}, every {INTERVAL}s)")
    hits = 0
    while hits < NEED_CONSECUTIVE:
        u = used_mib()
        if u <= FREE_MIB:
            hits += 1
            log(f"idle {hits}/{NEED_CONSECUTIVE} (used {u} MiB)")
        else:
            if hits:
                log(f"busy again (used {u} MiB) - reset")
            hits = 0
        if hits < NEED_CONSECUTIVE:
            time.sleep(INTERVAL)

    log("GPU is free - starting the 1%/5% round")
    env = dict(os.environ)
    env.update({
        "DATADIET_N_TRAIN": "48000",
        "DATADIET_N_POOL": "48000",
        "DATADIET_RATIOS": "0.01,0.05,0.10,0.20,0.30,0.50,0.70",
        "DATADIET_EPOCHS": "1",
    })
    with open(QLOG, "w", encoding="utf-8") as lf:
        rc = subprocess.run([str(PY), "tools/night_queue.py", "--plan", "small"],
                            cwd=ROOT, stdout=lf, stderr=subprocess.STDOUT, env=env).returncode
    log(f"queue exit={rc}")

    # 直接读 CSV 报数：不依赖 R，跑完立刻能看到
    import csv
    rows = list(csv.DictReader(open(ROOT / "results" / "metrics_long.csv", encoding="utf-8")))
    keep = [r for r in rows if r["ratio"] in ("0.01", "0.05", "1.0")]
    print("\n保留率 | 方法 | 任务 | 准确率 | 种子", flush=True)
    for r in sorted(keep, key=lambda x: (x["ratio"], x["method"], x["task"], x["seed"])):
        print(f"{r['ratio']:>6} | {r['method']:<7} | {r['task']:<8} | {float(r['value']):.4f} | {r['seed']}")
    log("small round finished")
    return 0


if __name__ == "__main__":
    sys.exit(main())
