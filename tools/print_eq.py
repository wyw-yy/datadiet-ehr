"""Print the headline tables from results/*.csv in a readable form.

Usage:
    python tools/print_eq.py [ratio]
"""
import csv
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
RES = ROOT / "results"


def rows(name: str) -> list[dict]:
    with open(RES / name, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main() -> int:
    ratio = float(sys.argv[1]) if len(sys.argv) > 1 else 0.30
    print(f"== eq_table.csv  ratio={ratio} ==")
    print(f"{'task':8s} {'method':11s} {'n':>2s} {'full':>7s} {'sub':>7s} {'delta':>7s} "
          f"{'95% CI (item)':>18s} {'95% CI (seed)':>18s} {'item':>5s} {'seed':>5s}")
    for r in rows("eq_table.csv"):
        if abs(float(r["ratio"]) - ratio) > 1e-9:
            continue
        print(f"{r['task']:8s} {r['method']:11s} {r['n_seed']:>2s} "
              f"{float(r['acc_full']):7.4f} {float(r['acc_sub']):7.4f} "
              f"{float(r['delta_pp']):7.2f} "
              f"[{float(r['ci_lo_pp']):6.2f},{float(r['ci_hi_pp']):6.2f}] "
              f"[{float(r['ci_seed_lo_pp']):6.2f},{float(r['ci_seed_hi_pp']):6.2f}] "
              f"{r['equiv_item']:>5s} {r['equiv_seed']:>5s}")

    print(f"\n== eq_contrast.csv  ratio={ratio} ==")
    print(f"{'task':8s} {'method':11s} {'vs':11s} {'delta':>7s} {'stouffer_p':>10s}")
    for r in rows("eq_contrast.csv"):
        if abs(float(r["ratio"]) - ratio) > 1e-9:
            continue
        print(f"{r['task']:8s} {r['method']:11s} {r['vs']:11s} "
              f"{float(r['delta_pp']):7.2f} {float(r['stouffer_p']):10.4f}")

    print(f"\n== compute_table.csv  ratio={ratio} ==")
    for r in rows("compute_table.csv"):
        if abs(float(r["ratio"]) - ratio) > 1e-9:
            continue
        print(f"{r['method']:11s} train={float(r['train_h']):.3f} "
              f"select={float(r['select_h']):.3f} total={float(r['gpu_hours']):.3f} "
              f"net={float(r['net_saving_pct']):5.1f}% acc={r['acc']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
