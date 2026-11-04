"""stop_after_full.py —— 全量基线两条跑完就收手，让机器能安全断电。

用户 2026-11-03：第一轮（full 的 seed 2、seed 3）跑完要拔电源。

做法：盯 `logs/remaining.log`，一看到 `full_s3: exit=` 这行，就把队列进程和
它可能已经拉起的子进程一起温和地停掉（SIGTERM → 等 5 秒 → SIGKILL），
然后确认显存落回空闲，写 `logs/stopped_for_poweroff.log`。

只杀本项目自己的 python（命令行含 run_remaining / run_one / train.py / eval.py / el2n_scores），
不动别的程序。
"""

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "logs" / "remaining.log"
OUT = ROOT / "logs" / "stopped_for_poweroff.log"
MARK = ROOT / "logs" / "stop_watchdog.log"

PATTERNS = ("run_remaining.py", "run_one.py", "train.py", "eval.py", "el2n_scores.py")


def say(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(MARK, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def gpu_used() -> int:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=20,
        ).stdout
        return int(out.strip().splitlines()[0])
    except Exception:
        return -1


def targets():
    """本项目自己的、还在干活的 python 进程。"""
    try:
        import psutil
    except ImportError:
        return []
    hits = []
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmd = " ".join(p.info["cmdline"] or [])
        except Exception:
            continue
        if "python" not in (p.info["name"] or "").lower():
            continue
        if "stop_after_full" in cmd:
            continue
        if any(k in cmd for k in PATTERNS):
            hits.append(p)
    return hits


def main() -> int:
    say("watchdog up: 等 full_s3 结束就停队列")
    deadline = time.time() + 8 * 3600
    while time.time() < deadline:
        try:
            text = LOG.read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            time.sleep(30)
            continue
        if "full_s3: exit=" in text:
            break
        time.sleep(30)
    else:
        say("8 小时内没等到 full_s3，放弃")
        return 1

    say("full_s3 已结束 → 停止队列与子进程")
    procs = targets()
    say(f"待停进程数 = {len(procs)}")
    for p in procs:
        try:
            p.terminate()
        except Exception:
            pass
    for _ in range(10):
        time.sleep(0.5)
        alive = [p for p in procs if p.is_running() and p.status() != "zombie"]
        if not alive:
            break
    for p in procs:
        try:
            if p.is_running() and p.status() != "zombie":
                p.kill()
        except Exception:
            pass

    # 等显存回收
    used = gpu_used()
    for _ in range(20):
        if 0 <= used <= 600:
            break
        time.sleep(3)
        used = gpu_used()

    resume = (ROOT / "logs" / "remaining.log").read_text(encoding="utf-8", errors="replace")
    done = [ln for ln in resume.splitlines() if "exit=0" in ln]
    lines = [
        "可以安全拔电源了。",
        "",
        f"停止时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"GPU 显存占用：{used} MiB（>600 说明还有残留，等一下再看）",
        "",
        "已完成的步骤：",
        *[f"  {d}" for d in done],
        "",
        "恢复命令（下次开机、确认没别的训练在跑之后执行）：",
        r"  cd C:\Users\yang'yu\Desktop\codetest\datadiet-ehr",
        r"  .\.venv\Scripts\python.exe tools\run_remaining.py",
        "",
        "队列是幂等的：已经跑完的会自动跳过（--reuse），从第二步 50%/70% 接着往下跑。",
    ]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    say(f"已写 {OUT.name}，显存 {used} MiB")
    print("\n".join(lines), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
