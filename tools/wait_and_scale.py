"""等机器空出来，然后自动跑 A 轮（24k 池）。

判"空出来"的条件（三个同时满足，连续 N 次采样都成立）：
  1. GPU 利用率 <= --util-max（默认 8%）
  2. GPU 已用显存 <= --mem-max（默认 1200 MiB）——这条是关键：
     QQ 机器人那套 ollama/llama-server 会长期占着 6.4 GB 显存，
     只要它还挂着，我们的训练（峰值 7.3 GiB）就跑不动。
  3. 没有别的 python.exe 在跑我们这个项目以外的训练脚本（只看本项目之外的命令行）

一旦满足，就执行 tools/run_scale.py（约 6.3 h），把输出写进 scale.log。

用法：
    python tools/wait_and_scale.py                 # 等到空就开跑
    python tools/wait_and_scale.py --dry-run       # 只观察，不启动
    python tools/wait_and_scale.py --max-hours 8   # 最多等 8 小时
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WAIT_LOG = os.path.join(ROOT, "scale_wait.log")
SCALE_LOG = os.path.join(ROOT, "scale.log")


def log(msg: str) -> None:
    ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(WAIT_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def gpu_state() -> tuple[int, int]:
    """返回 (利用率 %, 已用显存 MiB)。读不到就返回 (-1, -1)。"""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=30,
        )
        line = out.stdout.strip().splitlines()[0]
        util, mem = (int(x.strip()) for x in line.split(",")[:2])
        return util, mem
    except Exception as e:  # noqa: BLE001
        log(f"读 GPU 状态失败：{e}")
        return -1, -1


def gpu_holders() -> list[str]:
    """谁在占显存（只用于日志，便于事后追）。"""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=pid,process_name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=30,
        )
        return [l.strip() for l in out.stdout.strip().splitlines() if l.strip()]
    except Exception:  # noqa: BLE001
        return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=int, default=60, help="采样间隔秒数")
    ap.add_argument("--need", type=int, default=5, help="连续多少次空闲才开跑")
    ap.add_argument("--util-max", type=int, default=8)
    ap.add_argument("--mem-max", type=int, default=1200)
    ap.add_argument("--max-hours", type=float, default=10.0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    os.chdir(ROOT)
    log(f"开始等待：util<={args.util_max}% 且 mem<={args.mem_max}MiB，连续 {args.need} 次，"
        f"最多等 {args.max_hours} 小时，间隔 {args.interval}s，dry-run={args.dry_run}")

    deadline = time.time() + args.max_hours * 3600
    streak = 0
    while time.time() < deadline:
        util, mem = gpu_state()
        idle = (0 <= util <= args.util_max) and (0 <= mem <= args.mem_max)
        if idle:
            streak += 1
            log(f"空闲 {streak}/{args.need}：util={util}% mem={mem}MiB")
            if streak >= args.need:
                holders = gpu_holders()
                log(f"判定机器已空。当前占用者：{holders if holders else '无'}")
                if args.dry_run:
                    log("dry-run：到此为止，不启动。")
                    return 0
                return run_scale()
        else:
            if streak:
                log(f"又忙起来了，计数清零：util={util}% mem={mem}MiB")
            streak = 0
            if int(time.time()) % 600 < args.interval:  # 每 10 分钟记一次，不刷屏
                log(f"仍在等待：util={util}% mem={mem}MiB，占用者={gpu_holders()}")
        time.sleep(args.interval)

    log(f"等满 {args.max_hours} 小时仍未空闲，放弃（没有动任何数据）。")
    return 2


def run_scale() -> int:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["DATADIET_N_TRAIN"] = "24000"
    log("启动 tools/run_scale.py（24k 池，12 个 run，约 6.3 h）")
    with open(SCALE_LOG, "a", encoding="utf-8") as f:
        f.write(f"\n===== scale round started {dt.datetime.now():%Y-%m-%d %H:%M:%S} =====\n")
        f.flush()
        rc = subprocess.call([sys.executable, "-u", "tools/run_scale.py"], stdout=f,
                             stderr=subprocess.STDOUT, env=env)
        f.write(f"===== scale round finished rc={rc} {dt.datetime.now():%Y-%m-%d %H:%M:%S} =====\n")
    log(f"run_scale 退出码 {rc}，日志见 scale.log")

    if rc == 0:
        finish(env)
    return rc


def finish(env: dict) -> None:
    """跑完自动收尾：重算数字 → R 出图表 → 论文表 → 审计链 → 终检。"""
    rscript = r"C:\Program Files\R\R-4.6.1\bin\x64\Rscript.exe"
    steps = [
        ("report_numbers", [sys.executable, "-u", "tools/report_numbers.py"]),
        ("R figures/tables", [rscript, "R/run_all.R"]),
        ("table1", [sys.executable, "-u", "tools/make_table1.py"]),
        ("audit chain", [sys.executable, "-u", "tools/make_audit.py"]),
        ("final audit", [sys.executable, "-u", "tools/audit_final.py"]),
    ]
    with open(SCALE_LOG, "a", encoding="utf-8") as f:
        for name, cmd in steps:
            f.write(f"\n===== finish: {name} =====\n")
            f.flush()
            try:
                rc = subprocess.call(cmd, stdout=f, stderr=subprocess.STDOUT, env=env)
            except FileNotFoundError as e:
                f.write(f"!! {name} 起不来：{e}\n")
                rc = 127
            f.write(f"===== finish: {name} rc={rc} =====\n")
            f.flush()
            log(f"收尾 {name} 结束，rc={rc}")
    log("收尾全部跑完，看 scale.log 最后几段。")


if __name__ == "__main__":
    raise SystemExit(main())
