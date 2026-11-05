"""resume_rigor.py —— 把 2026-11-05 凌晨断掉的那批补齐。

断掉的原因：`eval.py` 的 `score_batch` 在 bs=16、max_len=1024 时让模型吐出
(B, T, 151936) 的 logits（bf16 约 5 GB），8 GB 卡直接 CUDA OOM；整批 25 个 run
在 random_r30_s14 之后全部死在 eval 上，01:57 训练进程也被拖崩，机器空转到下午。

已修：`score_batch` 用 `logits_to_keep=1` 只算最后位置，并在 `score_chunk` 里
OOM 自动把 bs 减半重试。

本脚本只补缺口：先看 `results/preds/` 里已有的，缺哪个补哪个；
adapter 已在 `models/adapters/<eid>` 的话 `--reuse` 会跳过训练，只补评测。
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = ROOT / ".venv" / "Scripts" / "python.exe"
LOG = ROOT / "logs" / "resume.log"
TASKS = ("medmcqa", "medqa")

# 25 个 run 的计划：random 7-20（零分布）+ 三条对照臂补种子
PLAN: list[tuple[str, float, int]] = []
PLAN += [("random", 0.30, s) for s in range(7, 21)]
PLAN += [("rand_len", 0.30, s) for s in range(2, 6)]
PLAN += [("nait_dedup", 0.30, s) for s in range(2, 6)]
PLAN += [("el2n", 0.30, s) for s in range(2, 5)]


def eid(method: str, ratio: float, seed: int) -> str:
    return f"{method}_r{int(round(ratio * 100)):02d}_s{seed}"


def log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def have_preds(e: str) -> bool:
    return all((ROOT / "results" / "preds" / f"{e}_{t}.csv.gz").exists() for t in TASKS)


def main() -> None:
    todo = [(m, r, s) for (m, r, s) in PLAN if not have_preds(eid(m, r, s))]
    log(f"resume up: {len(PLAN)} planned, {len(PLAN) - len(todo)} already done, {len(todo)} todo")
    ok, fails = 0, []
    t0 = time.time()
    for i, (m, r, s) in enumerate(todo, 1):
        e = eid(m, r, s)
        t1 = time.time()
        log(f"[{i}/{len(todo)}] start {e}  (elapsed {(t1 - t0) / 3600:.1f} h)")
        cmd = [str(PY), "run_one.py", "--method", m, "--ratio", str(r),
               "--seed", str(s), "--epochs", "1", "--reuse"]
        logfile = ROOT / "logs" / f"resume_{e}.log"
        with open(logfile, "w", encoding="utf-8") as lf:
            rc = subprocess.run(cmd, cwd=ROOT, stdout=lf, stderr=subprocess.STDOUT).returncode
        dt = (time.time() - t1) / 60
        if rc == 0 and have_preds(e):
            ok += 1
            log(f"{e}: ok in {dt:.1f} min")
        else:
            fails.append(e)
            log(f"{e}: FAILED rc={rc} in {dt:.1f} min (see logs/resume_{e}.log)")
    log(f"resume finished: ok={ok} failed={len(fails)} {fails if fails else ''}")
    if fails:
        sys.exit(1)


if __name__ == "__main__":
    main()