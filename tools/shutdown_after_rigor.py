"""shutdown_after_rigor.py —— 等 tools/run_rigor.py 那批 25 个 run 跑完，然后关机。

为什么单独写一个看门狗，而不是在 run_rigor.py 末尾加一句 shutdown：
  1. run_rigor 可能是被我手动重启的，关机逻辑不该混在训练脚本里；
  2. 关机前要确认"真的跑完了"（日志有 rigor finished），而不是"进程恰好不在"；
  3. 关不掉的机器要继续重试，并且留下证据（logs/shutdown_sent.txt）。

判定顺序：
  A. `logs/rigor.log` 出现 "rigor finished"   → 正常完成
  B. 连续 3 次检查（间隔 5 min）都看不到 run_rigor 进程 → 认为已结束/被终止
  C. 超过 --max-wait-hours 小时                          → 兜底（防止永远挂着）

关机命令用 `/s /f /t 120`：`/f` 会强制结束占用中的程序，
这正是上次（/t 300 不带 /f）被弹窗拦住、整夜没关成的原因。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "logs" / "shutdown_watch.log"
SENT = ROOT / "logs" / "shutdown_sent.txt"
RIGOR_LOG = ROOT / "logs" / "rigor.log"   # 可用 --log 覆盖


def log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def rigor_alive(proc_name: str = "run_rigor.py") -> bool:
    """有没有 run_rigor.py 在跑（用 psutil，避免 PowerShell 引号坑）。"""
    try:
        import psutil
    except ImportError:
        return True  # 没有 psutil 就当作还在跑，交给 A/C 判定
    for p in psutil.process_iter(["pid", "cmdline"]):
        try:
            cl = " ".join(p.info["cmdline"] or [])
        except Exception:
            continue
        if proc_name in cl and p.pid != os.getpid():
            return True
    return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=int, default=120, help="检查间隔（秒）")
    ap.add_argument("--max-wait-hours", type=float, default=30.0)
    ap.add_argument("--grace", type=int, default=180, help="确认完成后多等多久再关机（秒）")
    ap.add_argument("--log", default=None, help="盯哪个日志文件（默认 logs/rigor.log）")
    ap.add_argument("--process", default="run_rigor.py", help="盯哪个脚本进程")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    t0 = time.time()
    global RIGOR_LOG
    if a.log:
        RIGOR_LOG = ROOT / a.log
    log(f"watch up: log={RIGOR_LOG.name} process={a.process} interval={a.interval}s max={a.max_wait_hours}h dry_run={a.dry_run}")
    misses = 0
    reason = ""

    while True:
        elapsed_h = (time.time() - t0) / 3600
        finished = RIGOR_LOG.exists() and "rigor finished" in RIGOR_LOG.read_text(
            encoding="utf-8", errors="ignore")

        if finished:
            reason = "rigor.log 出现 'rigor finished'"
            break
        if rigor_alive(a.process):
            misses = 0
        else:
            misses += 1
            if misses >= 3:
                reason = f"连续 {misses} 次看不到 run_rigor.py 进程"
                break
        if elapsed_h > a.max_wait_hours:
            reason = f"超过兜底上限 {a.max_wait_hours} h"
            break
        time.sleep(a.interval)

    log(f"完成判据命中：{reason}")
    log(f"再等 {a.grace}s，让收尾脚本把文件写完、磁盘落盘")
    time.sleep(a.grace)

    # 关之前把最后的进度记下来，方便第二天看
    tail = ""
    if RIGOR_LOG.exists():
        lines = RIGOR_LOG.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
        tail = lines[-1] if lines else ""
    log(f"rigor.log 最后一行：{tail}")

    cmd = ["shutdown", "/s", "/f", "/t", "120", "/c", "rigor batch finished - auto shutdown"]
    if a.dry_run:
        log("dry-run：不执行 " + " ".join(cmd))
        return

    r = subprocess.run(cmd, capture_output=True, text=True, shell=False)
    log(f"shutdown rc={r.returncode} out={r.stdout.strip()} err={r.stderr.strip()}")
    SENT.write_text(
        f"{time.strftime('%Y-%m-%d %H:%M:%S')}\nreason={reason}\ncmd={' '.join(cmd)}\nrc={r.returncode}\n",
        encoding="utf-8",
    )
    if r.returncode != 0:
        log("立即关机失败，10 秒后用 /t 0 重试一次")
        time.sleep(10)
        r2 = subprocess.run(["shutdown", "/s", "/f", "/t", "0"], capture_output=True, text=True)
        log(f"retry rc={r2.returncode} err={r2.stderr.strip()}")


if __name__ == "__main__":
    main()