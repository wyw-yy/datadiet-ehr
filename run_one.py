"""One experiment = one command: pick subset -> train -> evaluate -> log.

    python run_one.py --method nait --ratio 0.30 --seed 1
    python run_one.py --method full --seed 1
    python run_one.py --method nait --ratio 0.30 --seed 1 --smoke      # 200 train / 100 eval items

It writes (and R/ reads):
    results/adapters/<exp_id>/                 LoRA weights
    results/runs/<exp_id>.json                 timing + bookkeeping
    results/preds/<exp_id>_<task>.csv.gz       per-item predictions
    results/metrics_long.csv                   one row per (exp_id, task)
    results/compute.csv                        one row per exp_id

Rows are upserted, so re-running the same experiment replaces its numbers
instead of duplicating them.
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from pathlib import Path

import config as C

PY = sys.executable


def sh(cmd: list[str]) -> None:
    print("  $ " + " ".join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=str(C.PROJ))
    if r.returncode != 0:
        raise SystemExit(f"[run_one] step failed ({r.returncode}): {' '.join(cmd)}")


def upsert(path: Path, key: dict, row: dict, fields: list[str]) -> None:
    rows = []
    if path.exists():
        with open(path, encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
    rows = [r for r in rows if any(str(r.get(k)) != str(v) for k, v in key.items())]
    rows.append({k: row.get(k, "") for k in fields})
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def select_overhead(method: str) -> float:
    """Amortised cost of the selection pass (measured once, stored by the pipeline)."""
    p = C.RESULTS / "select_overhead.json"
    if method == "full":
        return 0.0
    if p.exists():
        with open(p, encoding="utf-8") as f:
            return float(json.load(f).get(method, 0.0))
    return 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--method", required=True, choices=C.METHODS)
    ap.add_argument("--ratio", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--epochs", type=float, default=1.0)
    ap.add_argument("--tasks", default=",".join(C.TASKS))
    ap.add_argument("--smoke", action="store_true", help="200 train rows, 100 eval items")
    ap.add_argument("--limit-train", type=int, default=None)
    ap.add_argument("--limit-eval", type=int, default=None)
    ap.add_argument("--reuse", action="store_true", help="skip training if the adapter exists")
    a = ap.parse_args()

    C.ensure_dirs()
    eid = C.exp_id(a.method, a.ratio, a.seed)
    tasks = [t for t in a.tasks.split(",") if t]
    limit_train = 200 if a.smoke else a.limit_train
    limit_eval = 100 if a.smoke else a.limit_eval
    adapter = C.ADAPTERS / eid

    t0 = time.time()
    print(f"=== {eid}  tasks={tasks}  smoke={a.smoke}", flush=True)

    if a.reuse and adapter.exists():
        print("[run_one] adapter exists, skipping training", flush=True)
        train_s = float(json.load(open(C.RUNS / f"{eid}.json", encoding="utf-8"))["train_seconds"]) \
            if (C.RUNS / f"{eid}.json").exists() else 0.0
    else:
        cmd = [PY, "train.py", "--method", a.method, "--ratio", str(a.ratio),
               "--seed", str(a.seed), "--epochs", str(a.epochs)]
        if limit_train:
            cmd += ["--limit", str(limit_train)]
        # NB: even in smoke mode we keep the adapter - the point of the smoke test is
        # to exercise the adapter -> eval path, which is exactly what would break.
        sh(cmd)
        rec = json.load(open(C.RUNS / f"{eid}.json", encoding="utf-8"))
        train_s = float(rec["train_seconds"])

    eval_s = 0.0
    for task in tasks:
        preds = C.PREDS / f"{eid}_{task}.csv.gz"
        cmd = [PY, "eval.py", "--task", task, "--exp-id", eid,
               "--out", str(preds)]
        if adapter.exists():
            cmd += ["--adapter", str(adapter)]
        if limit_eval:
            cmd += ["--limit", str(limit_eval)]
        te = time.time()
        sh(cmd)
        eval_s += time.time() - te

        acc = None
        n_items = 0
        if preds.exists():
            import gzip
            with gzip.open(preds, "rt", encoding="utf-8") as f:
                rd = list(csv.DictReader(f))
            n_items = len(rd)
            acc = sum(int(r["correct"]) for r in rd) / max(n_items, 1)
        if acc is None:
            raise SystemExit(f"[run_one] {preds} was not written")

        upsert(C.RESULTS / "metrics_long.csv",
               {"exp_id": eid, "task": task},
               {"exp_id": eid, "method": a.method, "ratio": a.ratio, "seed": a.seed,
                "task": task, "value": round(acc, 6), "n_items": n_items,
                "split": "smoke" if a.smoke else "full"},
               ["exp_id", "method", "ratio", "seed", "task", "value", "n_items", "split"])
        print(f"[run_one] {task}: acc={acc:.4f} on {n_items} items", flush=True)

    gpu_hours = (train_s + eval_s) / 3600.0
    upsert(C.RESULTS / "compute.csv",
           {"exp_id": eid},
           {"exp_id": eid, "method": a.method, "ratio": a.ratio, "seed": a.seed,
            "gpu_hours": round(gpu_hours, 4),
            "select_overhead_h": round(select_overhead(a.method), 4),
            "train_seconds": round(train_s, 1), "eval_seconds": round(eval_s, 1)},
           ["exp_id", "method", "ratio", "seed", "gpu_hours", "select_overhead_h",
            "train_seconds", "eval_seconds"])

    print(f"[run_one] {eid} done in {(time.time() - t0) / 60:.1f} min  "
          f"(train {train_s / 60:.1f} + eval {eval_s / 60:.1f})", flush=True)


if __name__ == "__main__":
    main()
