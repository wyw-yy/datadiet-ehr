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


# 需要跑一遍模型才能挑样本的方法：它们没有"免费"的可能，必须显式登记开销。
NEEDS_SELECTION = {"nait", "nait_dedup", "nait_ns", "nait_dp", "nait_dedup_dp", "el2n"}


def select_overhead(method: str) -> float:
    """Amortised cost of the selection pass (measured once, stored by the pipeline).

    这里以前是 `.get(method, 0.0)` + 文件不存在返回 0.0，结果是：归档把
    results/select_overhead.json 搬走后，nait 的选择开销被静默记成 0，
    "净省 48%" 会凭空变成 "净省 70%"。这类静默默认值比报错危险得多，
    所以现在改成：该收钱的方法没登记开销就直接失败。
    """
    if method in ("full", "random", "rand_len"):
        return 0.0                      # 这几个不做前向筛选，确实为 0

    p = C.RESULTS / "select_overhead.json"
    if not p.exists():
        raise SystemExit(
            f"[run_one] 缺 {p}：{method} 需要登记选择前向开销。\n"
            f"         先跑 collect_acts.py + select_subset.py 让它落盘，"
            f"或手动写入 {{\"{method}\": <实测 GPU-h>}}。\n"
            f"         不要默认 0——那会把净省算高（历史事故：48% 被算成 70%）。"
        )
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    if method in NEEDS_SELECTION and method not in data:
        raise SystemExit(
            f"[run_one] {p} 里没有 {method} 的开销（现有键：{sorted(data)}）。\n"
            f"         该方法的子集是用模型挑的，必须把实测耗时写进去。"
        )
    return float(data.get(method, 0.0))


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
    # 显存吃紧时的逃生门：--bs 2 把 batch 降下来（train.py 默认 bs 4）。
    ap.add_argument("--bs", type=int, default=None, help="override train.py batch size")
    ap.add_argument("--grad-accum", type=int, default=None, help="override grad accumulation steps")
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
        if a.bs:
            cmd += ["--bs", str(a.bs)]
            # 保持等效 batch（默认 bs4 × accum2 = 8）：bs 减半就把累积步数翻倍
            cmd += ["--grad-accum", str(a.grad_accum or max(1, 8 // a.bs))]
        elif a.grad_accum:
            cmd += ["--grad-accum", str(a.grad_accum)]
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
