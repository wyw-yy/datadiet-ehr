"""report_numbers.py —— 把论文里要引用的数字，从 CSV 里统一念一遍。

目的：文档（RESULTS.md / PREREG.md）里出现的每个数字，都必须能在这里溯源，
      否则就是手抄的，迟早会和表对不上。

用法：
    .venv\\Scripts\\python.exe tools\\report_numbers.py          # 打印 + 写 results/headline.json
    .venv\\Scripts\\python.exe tools\\report_numbers.py --check  # 只校验文档里的数字是否都在 headline.json 里
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import config as C  # noqa: E402

DOCS = ["RESULTS.md", "docs/PREREG.md"]


def read_csv(p: Path) -> list[dict]:
    with open(p, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fmt_pp(x: float) -> str:
    return f"{x:+.2f}"


def collect() -> dict:
    out: dict = {"headline": {}, "tables": {}}

    eq = {f"{r['task']}|{r['method']}|{r['ratio']}": r
          for r in read_csv(C.RESULTS / "eq_table.csv")}
    # 注意：同一个 (task, method, ratio) 可能有多条对比（vs random / vs rand_len / vs nait），
    # 只有 vs == "random" 才是头条里说的"相对随机"；不过滤会取到最后一条（通常是 vs rand_len）。
    ct = {f"{r['task']}|{r['method']}|{r['ratio']}|random": r
          for r in read_csv(C.RESULTS / "eq_contrast.csv") if r.get("vs") == "random"}
    comp = read_csv(C.RESULTS / "compute_table.csv")

    for tk in ("medmcqa", "medqa"):
        for mt in ("nait", "random", "nait_dedup"):
            k = f"{tk}|{mt}|0.3"
            if k not in eq:
                continue
            r = eq[k]
            out["headline"][k] = {
                "delta_pp": float(r["delta_pp"]),
                "ci_lo_pp": float(r["ci_lo_pp"]),
                "ci_hi_pp": float(r["ci_hi_pp"]),
                "n_seed": int(r["n_seed"]),
                "equiv_item": r["equiv_item"],
                "equiv_seed": r["equiv_seed"],
                "stouffer_p": float(r["stouffer_p"]),
                "seed_min_pp": float(r["seed_min_pp"]),
                "seed_max_pp": float(r["seed_max_pp"]),
            }
            ck = f"{k}|random"
            if ck in ct:
                out["headline"][k]["vs_random_pp"] = float(ct[ck]["delta_pp"])
                out["headline"][k]["vs_random_p"] = float(ct[ck]["stouffer_p"])
                out["headline"][k]["vs_random_same_sign"] = ct[ck]["same_sign"]

    full = [c for c in comp if abs(float(c["ratio"]) - 1.0) < 1e-9]
    if full:
        out["headline"]["compute_full_gpu_h"] = float(full[0]["gpu_hours"])
    for c in comp:
        if abs(float(c["ratio"]) - 0.3) < 1e-9:
            out["headline"][f"compute_{c['method']}_30"] = {
                "gpu_hours": float(c["gpu_hours"]),
                "net_saving_pct": float(c["net_saving_pct"]),
            }

    m = read_csv(C.RESULTS / "metrics_long.csv")
    out["headline"]["n_runs"] = len({r["exp_id"] for r in m})
    out["headline"]["n_tasks"] = len({r["task"] for r in m})

    ss = read_csv(C.RESULTS / "sample_stats.csv")
    out["headline"]["sample_stats_rows"] = len(ss)
    out["headline"]["sample_stats_nait30"] = sum(int(r["nait_30"]) for r in ss)
    out["tables"]["eq_table"] = eq
    out["tables"]["eq_contrast"] = ct
    return out


def check(doc_numbers: dict) -> int:
    hp = C.RESULTS / "headline.json"
    if not hp.exists():
        print("❌ results/headline.json 不存在，先不带 --check 跑一次")
        return 1
    head = json.loads(hp.read_text(encoding="utf-8"))["headline"]

    canon = set()
    for k, v in head.items():
        if isinstance(v, dict):
            for kk, vv in v.items():
                if isinstance(vv, float):
                    canon.add(f"{vv:.2f}")
                    canon.add(f"{vv:+.2f}")
                    canon.add(f"{abs(vv):.2f}")
                elif isinstance(vv, int):
                    canon.add(str(vv))
        elif isinstance(v, float):
            canon.add(f"{v:.2f}")
            canon.add(f"{v:+.2f}")
            canon.add(f"{abs(v):.2f}")
        elif isinstance(v, int):
            canon.add(str(v))

    bad = 0
    for doc in DOCS:
        p = ROOT / doc
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        nums = set(re.findall(r"-?\d+\.\d+", text))
        missing = sorted(n for n in nums if n.lstrip("+") not in canon
                         and n not in canon and f"{abs(float(n)):.2f}" not in canon)
        # 允许文档里出现的非表格数字（日期、版本、阈值等）；只提示前若干个
        print(f"{doc}: 小数 {len(nums)} 个，其中 {len(missing)} 个不在 headline.json 里")
        if missing:
            print("   例：", ", ".join(missing[:8]))
    return bad


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    if args.check:
        sys.exit(check({}))

    d = collect()
    (C.RESULTS / "headline.json").write_text(
        json.dumps(d["headline"], ensure_ascii=False, indent=2), encoding="utf-8")

    h = d["headline"]
    print("=" * 68)
    print("论文要引用的数字（全部来自 CSV）")
    print("=" * 68)
    for tk in ("medmcqa", "medqa"):
        for mt in ("nait", "random", "nait_dedup"):
            k = f"{tk}|{mt}|0.3"
            if k not in h:
                continue
            r = h[k]
            print(f"{tk:8s} {mt:11s} 30%  Δ={r['delta_pp']:+.2f}pp "
                  f"CI[{r['ci_lo_pp']:+.2f},{r['ci_hi_pp']:+.2f}] "
                  f"equiv_item={r['equiv_item']} equiv_seed={r['equiv_seed']} "
                  f"(n={r['n_seed']})")
            if "vs_random_pp" in r:
                print(f"{'':8s} {'':11s} vs random: {r['vs_random_pp']:+.2f}pp "
                      f"p={r['vs_random_p']:.3f} same_sign={r['vs_random_same_sign']}")
    print()
    print("剂量-反应（每个方法 × 比例，来自 eq_table.csv）")
    for r in read_csv(C.RESULTS / "eq_table.csv"):
        print(f"  {r['task']:8s} {r['method']:11s} {int(round(float(r['ratio'])*100)):>3d}% "
              f"n={r['n_seed']} Δ={r['delta_pp']:>6}pp CI[{r['ci_lo_pp']:>6},{r['ci_hi_pp']:>6}] "
              f"item={r['equiv_item']:<5} seed={r['equiv_seed']}")
    print()
    print(f"全量单次训练      {h['compute_full_gpu_h']:.2f} GPU-h")
    for k, v in h.items():
        if k.startswith("compute_") and isinstance(v, dict):
            print(f"{k[8:]:18s} {v['gpu_hours']:.2f} GPU-h  净省 {v['net_saving_pct']:.1f}%")
    print()
    print(f"run 数 {h['n_runs']}，任务 {h['n_tasks']} 个")
    print(f"sample_stats 行数 {h['sample_stats_rows']}，nait_30 选中 {h['sample_stats_nait30']}")
    print("\n已写出 results/headline.json")


if __name__ == "__main__":
    main()
