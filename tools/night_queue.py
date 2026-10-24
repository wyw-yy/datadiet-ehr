"""Run a queue of experiments back to back, skipping whatever is already done.

Why a python driver instead of a .bat: the queue is data (a list of
(method, ratio, seed) triples), it can skip finished runs, and it keeps going
after a single failure instead of dying at the first error at 3am.

Usage:
    python tools/night_queue.py                 # the default overnight plan
    python tools/night_queue.py --plan quick    # only the three 30% arms
    python tools/night_queue.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config as C  # noqa: E402

PY = ROOT / ".venv" / "Scripts" / "python.exe"
LOG = ROOT / "night.log"


def done_ids() -> set[str]:
    p = C.RESULTS / "metrics_long.csv"
    if not p.exists():
        return set()
    out = set()
    with open(p, encoding="utf-8") as f:
        next(f, None)
        for line in f:
            out.add(line.split(",", 1)[0])
    return out


def plan(name: str) -> list[tuple[str, float, int]]:
    """(method, ratio, seed) triples, in priority order."""
    if name == "quick":
        return [("full", 1.0, 1), ("nait", 0.3, 1), ("random", 0.3, 1)]

    if name == "seeds6":
        # 目标：把 30% 这一档从 3 个种子补到 6 个，并加长度匹配对照臂。
        # 顺序上先补 full（最长、也是所有差值的分母），后面全是 3600 条的短 run。
        q: list[tuple[str, float, int]] = []
        for s in (2, 3, 4, 5, 6):
            q.append(("full", 1.0, s))
        for s in (2, 3, 4, 5, 6):
            q.append(("nait", 0.30, s))
        for s in (2, 3, 4, 5, 6):
            q.append(("random", 0.30, s))
        for s in (1, 2, 3, 4, 5, 6):
            q.append(("rand_len", 0.30, s))
        # nait_dedup 在 MedQA 上是单种子的 −1.18pp，补两个种子看是不是噪声
        for s in (2, 3):
            q.append(("nait_dedup", 0.30, s))
        return q

    q: list[tuple[str, float, int]] = []
    # 1. the baseline, then the head-to-head at the headline ratio
    q += [("full", 1.0, 1), ("nait", 0.30, 1), ("random", 0.30, 1)]
    # 2. the dose-response curve (where does random break?)
    for r in (0.10, 0.20, 0.50, 0.70):
        q += [("nait", r, 1), ("random", r, 1)]
    # 3. replication seeds for the baseline and the headline point
    for s in (2, 3):
        q += [("full", 1.0, s), ("nait", 0.30, s), ("random", 0.30, s)]
    # 4. the dedup arm, if time remains
    for r in (0.10, 0.30):
        q += [("nait_dedup", r, 1)]
    return q


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", default="full", choices=["full", "quick", "seeds6"])
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    have = done_ids()
    items = [t for t in plan(a.plan) if C.exp_id(*t) not in have]
    print(f"[night] {len(items)} runs to do ({len(plan(a.plan)) - len(items)} already done)")

    if a.dry_run:
        for m, r, s in items:
            print("   ", C.exp_id(m, r, s))
        return

    t0 = time.time()
    with open(LOG, "a", encoding="utf-8") as lf:
        lf.write(f"\n===== night queue start {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
    failures = []
    for i, (m, r, s) in enumerate(items, 1):
        eid = C.exp_id(m, r, s)
        cmd = [str(PY), str(ROOT / "run_one.py"), "--method", m,
               "--ratio", str(r), "--seed", str(s), "--epochs", "1"]
        head = f"[night {i}/{len(items)}] {eid}  ({time.strftime('%H:%M:%S')})"
        print(head, flush=True)
        with open(LOG, "a", encoding="utf-8") as lf:
            lf.write(head + "\n")
        t = time.time()
        try:
            with open(LOG, "a", encoding="utf-8") as lf:
                p = subprocess.run(cmd, cwd=ROOT, stdout=lf, stderr=subprocess.STDOUT)
            if p.returncode != 0:
                raise RuntimeError(f"run_one exit {p.returncode}")
        except Exception as e:                                    # keep going
            failures.append((eid, str(e)))
            msg = f"  FAILED {eid}: {e}"
            print(msg, flush=True)
            with open(LOG, "a", encoding="utf-8") as lf:
                lf.write(msg + "\n")
            continue
        print(f"  ok in {(time.time() - t) / 60:.0f} min", flush=True)
        with open(LOG, "a", encoding="utf-8") as lf:
            lf.write(f"  ok in {(time.time() - t) / 60:.1f} min\n")

    total = (time.time() - t0) / 3600
    summary = (f"[night] finished {len(items) - len(failures)}/{len(items)} runs "
               f"in {total:.1f} h; failures={failures}")
    print(summary)
    with open(LOG, "a", encoding="utf-8") as lf:
        lf.write(summary + "\n")


if __name__ == "__main__":
    main()
