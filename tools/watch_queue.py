"""watch_queue.py —— 队列跑批期间的实时看板（不依赖子进程日志）

背景：night_queue.py 用 subprocess.run(stdout=父进程日志句柄) 传句柄，
外层 PowerShell 又 `*>` 重定向同一个文件，子进程的 print 落不进盘。
所以进度改从"事实来源"读：
  - results/metrics_long.csv 里已完成的 exp_id（每完成一个 run 会 upsert 两行）
  - 正在跑的进程命令行（train.py --method X --ratio R --seed S）
  - results/runs/*.json 的训练耗时与样本数
  - nvidia-smi 的利用率/显存

用法：
  python tools/watch_queue.py            # 打印一次
  python tools/watch_queue.py --watch    # 每 30 秒刷新，Ctrl+C 退出
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
RESULTS = PROJ / "results"

# seeds6 计划里"这一轮要跑"的 17 个 run（与 night_queue.py --plan seeds6 剩下列表一致）
PLAN = [("full", 1.0, s) for s in (4, 5, 6)]
PLAN += [(m, 0.30, s) for m in ("nait", "random") for s in (4, 5, 6)]
PLAN += [("rand_len", 0.30, s) for s in (1, 2, 3, 4, 5, 6)]
PLAN += [("nait_dedup", 0.30, s) for s in (2, 3)]


def exp_id(method: str, ratio: float, seed: int) -> str:
    return f"full_s{seed}" if method == "full" else f"{method}_r{int(round(ratio * 100)):02d}_s{seed}"


def done_ids() -> set[str]:
    p = RESULTS / "metrics_long.csv"
    if not p.exists():
        return set()
    with open(p, newline="", encoding="utf-8") as f:
        return {r["exp_id"] for r in csv.DictReader(f)}


def current_run() -> str | None:
    """从进程命令行里找正在跑的 train.py，返回 exp_id。"""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
             "Select-Object -ExpandProperty CommandLine"],
            capture_output=True, text=True, timeout=20,
        ).stdout
    except Exception:
        return None
    for line in out.splitlines():
        if "train.py" not in line:
            continue
        kw = {}
        parts = line.split()
        for i, tok in enumerate(parts):
            if tok.startswith("--") and i + 1 < len(parts):
                kw[tok[2:]] = parts[i + 1]
        if "method" in kw and "seed" in kw:
            try:
                return exp_id(kw["method"], float(kw.get("ratio", 1.0)), int(kw["seed"]))
            except ValueError:
                return None
    return None


def gpu() -> str:
    try:
        return subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,power.draw",
             "--format=csv,noheader"],
            capture_output=True, text=True, timeout=20,
        ).stdout.strip()
    except Exception:
        return "(nvidia-smi 不可用)"


def runs_table() -> list[dict]:
    rows = []
    d = RESULTS / "runs"
    if not d.exists():
        return rows
    for p in sorted(d.glob("*.json"), key=lambda q: q.stat().st_mtime):
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        rows.append({
            "exp_id": j.get("exp_id", p.stem),
            "samples": j.get("n_samples"),
            "min": round(float(j.get("train_seconds", 0)) / 60, 1),
        })
    return rows


def bar(done: int, total: int, width: int = 34) -> str:
    fill = int(width * done / max(total, 1))
    return "[" + "#" * fill + "." * (width - fill) + f"] {done}/{total}"


def render() -> None:
    done = done_ids()
    finished = [exp_id(*p) for p in PLAN if exp_id(*p) in done]
    cur = current_run()
    print("=" * 64)
    print(f"队列 seeds6  {bar(len(finished), len(PLAN))}")
    print(f"GPU: {gpu()}")
    print(f"当前: {cur or '(空闲 / 正在起下一个)'}")
    todo = [exp_id(*p) for p in PLAN if exp_id(*p) not in done]
    print(f"剩余 {len(todo)} 个: {', '.join(todo[:6])}{' …' if len(todo) > 6 else ''}")
    rows = runs_table()
    if rows:
        print("\n最近完成的 run：")
        for r in rows[-5:]:
            print(f"  {r['exp_id']:<20} {str(r['samples']):>6} 条  {r['min']:>5} min")
    print("=" * 64)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--watch", action="store_true", help="每 30 秒刷新")
    ap.add_argument("--seconds", type=int, default=30)
    a = ap.parse_args()
    if not a.watch:
        render()
        return
    try:
        while True:
            subprocess.run("cls", shell=True)
            render()
            time.sleep(a.seconds)
    except KeyboardInterrupt:
        print("\n(停止刷新)")


if __name__ == "__main__":
    sys.exit(main())
