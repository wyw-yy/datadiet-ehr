"""shutdown_when_idle.py —— 等机器真正闲下来，然后自动关机（用户要求）。

为什么单独一个脚本：训练队列、消融、R 收尾是三个不同的进程，任何一个崩了
都不该把机器一直开着。这个看门狗只认一件事：**还有没有人在干活**。

判定"在干活"的口径（三个都满足才算闲）：
  1. 没有 python 进程跑着本项目的重活（train/run_one/night_queue/chain/
     after_sweep/collect_acts/select_subset/prepare_data/gen_eval）；
  2. 没有 Rscript 在跑；
  3. GPU 利用率 < 5% 且显存占用 < 1500 MiB。
连续 `--idle-checks` 次（默认 5 次 × 60 s）都闲，才关机，中间任何一次忙起来就重新计数。

安全阀：
  * 关机前先执行 `shutdown /a` 清掉可能存在的旧倒计时；
  * 用 `shutdown /s /t 180` —— 三分钟倒计时，屏幕上会提示，反悔就 `shutdown /a`；
  * `--max-wait-hours` 兜底（默认 14 h），到点即使有人在跑也关，避免通宵空转；
  * 关机前把当前进度摘要写进 logs/last_state.txt，第二天醒来能直接看结果。
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LOG = ROOT / "logs" / "shutdown.log"
STATE = ROOT / "logs" / "last_state.txt"

HEAVY = (
    "train.py", "run_one.py", "night_queue", "chain.py", "after_sweep",
    "collect_acts", "select_subset", "prepare_data", "gen_eval",
)


def log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def ps(cmd: str) -> str:
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                             capture_output=True, text=True, timeout=90)
        return out.stdout
    except Exception as e:
        log(f"查进程失败（按'忙'处理）：{e}")
        return "busy-on-error"


def heavy_running() -> bool:
    """用 psutil 直接读进程表。

    原来用 PowerShell 的 `-match` 拼正则查询，引号一乱就返回非空字符串，
    于是"永远在忙"——看门狗一次都没能关机。改成 psutil 后再没有这层转义。
    """
    try:
        import psutil
    except ImportError:
        log("没有 psutil，退回 PowerShell 查询")
        return bool(ps("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "
                       "'*train.py*' } | Select-Object -First 1 -ExpandProperty ProcessId").strip())

    me = os.getpid()
    for pr in psutil.process_iter(["pid", "name", "cmdline"]):
        if pr.info["pid"] == me:
            continue
        name = (pr.info.get("name") or "").lower()
        if name == "rscript.exe":
            return True
        cmdline = " ".join(pr.info.get("cmdline") or [])
        if any(tok in cmdline for tok in HEAVY):
            return True
    return False


def gpu_busy() -> bool:
    out = ps("nvidia-smi --query-gpu=utilization.gpu,memory.used "
             "--format=csv,noheader,nounits")
    try:
        util, mem = [int(x) for x in out.strip().splitlines()[0].split(",")]
    except Exception:
        return False                     # 查不到 GPU 就不拦着关机
    return util >= 5 or mem >= 1500


def write_state() -> None:
    """关机前留一份现场快照，省得第二天还要翻日志。"""
    lines = [f"# 关机快照 {time.strftime('%Y-%m-%d %H:%M:%S')}", ""]
    metrics = ROOT / "results" / "metrics_long.csv"
    if metrics.exists():
        rows = metrics.read_text(encoding="utf-8").splitlines()
        lines += [f"metrics_long.csv: {len(rows) - 1} 行", ""]
        lines += rows[:1] + rows[-8:]
    for name in ("eq_table.csv", "eq_contrast.csv", "compute_table.csv",
                 "holm.csv", "e3_summary.csv"):
        p = ROOT / "results" / name
        lines.append(f"{name}: {'有' if p.exists() else '缺'}")
    runs = sorted((ROOT / "results" / "runs").glob("*.json"))
    lines += ["", f"completed runs: {len(runs)}",
              "last 5: " + ", ".join(p.stem for p in runs[-5:])]
    chain = ROOT / "logs" / "chain_state.json"
    if chain.exists():
        try:
            lines += ["", "chain_state: " + json.dumps(
                json.loads(chain.read_text(encoding="utf-8")), ensure_ascii=False)]
        except Exception:
            pass
    STATE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(f"快照写到 {STATE}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--idle-checks", type=int, default=5)
    ap.add_argument("--seconds", type=int, default=60)
    ap.add_argument("--max-wait-hours", type=float, default=14.0)
    ap.add_argument("--delay", type=int, default=180, help="关机倒计时秒数")
    a = ap.parse_args()

    log(f"看门狗启动：连续 {a.idle_checks} 次（每 {a.seconds}s）空闲就关机，"
        f"最长等 {a.max_wait_hours} h")
    t0 = time.time()
    idle = 0
    while True:
        waited_h = (time.time() - t0) / 3600
        busy = heavy_running() or gpu_busy()
        if busy:
            if idle:
                log(f"又有活干了，重新计数（之前 {idle} 次空闲）")
            idle = 0
        else:
            idle += 1
            log(f"空闲 {idle}/{a.idle_checks}（已等 {waited_h:.1f} h）")
            if idle >= a.idle_checks:
                log("判定：所有活都干完了 → 准备关机")
                break
        if waited_h > a.max_wait_hours:
            log(f"已等 {waited_h:.1f} h，超过上限，照样关机（可能有卡住的进程）")
            break
        time.sleep(a.seconds)

    write_state()
    subprocess.run(["shutdown", "/a"], capture_output=True)   # 清掉旧倒计时
    subprocess.run(["shutdown", "/s", "/t", str(a.delay),
                    "/c", "DataDiet-EHR: all runs finished, shutting down."],
                   capture_output=True)
    log(f"已下达关机命令：{a.delay} 秒后关机（反悔就执行 shutdown /a）")


if __name__ == "__main__":
    main()
