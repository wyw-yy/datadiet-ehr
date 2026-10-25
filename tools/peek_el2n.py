"""Print a short summary of the EL2N selection (dept mix + score spread).

Usage: python tools/peek_el2n.py
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATS = ROOT / "results" / "select_stats_el2n.json"
SUBS = ROOT / "data" / "subsets" / "subsets_el2n.json"


def main() -> int:
    if not STATS.exists() or not SUBS.exists():
        print(f"missing: stats={STATS.exists()} subsets={SUBS.exists()}")
        return 1
    st = json.loads(STATS.read_text(encoding="utf-8"))
    print("== select_stats_el2n.json 顶层键 ==")
    print(list(st))
    for key in ("n_pool", "n_scored", "score_p50", "score_p10", "score_p90"):
        if key in st:
            print(f"{key} = {st[key]}")
    dist = st.get("dept_counts") or st.get("dept_dist") or {}
    if dist:
        tot = sum(dist.values()) or 1
        print("== 选中子集的科室分布 ==")
        for k, v in sorted(dist.items(), key=lambda kv: -kv[1]):
            print(f"  {k:8s} {v:6d}  {100.0 * v / tot:5.1f}%")

    subs = json.loads(SUBS.read_text(encoding="utf-8"))
    ratios = sorted(subs.get("el2n", {}), key=lambda r: int(r))
    print("== 子集规模 ==")
    for r in ratios:
        print(f"  {r}% -> {len(subs['el2n'][r])} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
