"""Paired comparison between two runs on the same test items.

Usage:
    python tools/paired_stats.py full_s1_medqa nait_r30_s1_medqa
    python tools/paired_stats.py full_s1_medqa nait_r30_s1_medqa random_r30_s1_medqa

Prints, for each comparison:
  - accuracy of each run
  - the 2x2 table (both right / A only / B only / both wrong)
  - exact McNemar p-value (binom.test on the discordant pairs)
  - paired bootstrap CI for the accuracy difference (2000 resamples over items)

Why paired: the same 1,273 questions are answered by both models, so the
question "is B better than A" only depends on the items where they disagree.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PRED = ROOT / "results" / "preds"
RNG = np.random.default_rng(0)


def load(eid: str) -> pd.DataFrame:
    p = PRED / f"{eid}.csv.gz"
    if not p.exists():
        raise SystemExit(f"missing {p}")
    df = pd.read_csv(p)
    need = {"item_id", "correct"}
    if not need.issubset(df.columns):
        raise SystemExit(f"{p} lacks columns {need - set(df.columns)}")
    return df[["item_id", "correct"]].sort_values("item_id").reset_index(drop=True)


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar via the binomial test on discordant pairs."""
    from math import comb

    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    # two-sided: 2 * P(X <= k), capped at 1
    tail = sum(comb(n, i) for i in range(k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def boot_ci(diff: np.ndarray, B: int = 2000, alpha: float = 0.05) -> tuple[float, float]:
    idx = RNG.integers(0, len(diff), size=(B, len(diff)))
    means = diff[idx].mean(axis=1)
    lo, hi = np.quantile(means, [alpha / 2, 1 - alpha / 2])
    return float(lo), float(hi)


def compare(a: str, b: str) -> None:
    da, db = load(a), load(b)
    if not da["item_id"].equals(db["item_id"]):
        common = set(da["item_id"]) & set(db["item_id"])
        da = da[da["item_id"].isin(common)].reset_index(drop=True)
        db = db[db["item_id"].isin(common)].reset_index(drop=True)
        print(f"  (restricted to {len(common)} common items)")

    ca = da["correct"].to_numpy().astype(int)
    cb = db["correct"].to_numpy().astype(int)
    n = len(ca)

    acc_a, acc_b = ca.mean(), cb.mean()
    both = int(((ca == 1) & (cb == 1)).sum())
    only_a = int(((ca == 1) & (cb == 0)).sum())
    only_b = int(((ca == 0) & (cb == 1)).sum())
    neither = int(((ca == 0) & (cb == 0)).sum())

    d = cb - ca
    lo, hi = boot_ci(d)
    p = mcnemar_exact(only_a, only_b)

    print(f"\n{a}  vs  {b}")
    print(f"  n = {n} items")
    print(f"  acc {a:<18} {acc_a:.4f}")
    print(f"  acc {b:<18} {acc_b:.4f}")
    print(f"  diff (B - A)        {100 * (acc_b - acc_a):+.2f} pp "
          f"[{100 * lo:+.2f}, {100 * hi:+.2f}] 95% CI")
    print(f"  both right {both:>5}   only A {only_a:>5}   only B {only_b:>5}   both wrong {neither:>5}")
    print(f"  McNemar exact p = {p:.4g}")


def main() -> None:
    args = sys.argv[1:]
    if len(args) < 2:
        raise SystemExit(__doc__)
    for other in args[1:]:
        compare(args[0], other)


if __name__ == "__main__":
    main()
