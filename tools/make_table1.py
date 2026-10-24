"""从 results/ 的 CSV 生成论文正文表（Table 1 / Table 2 / 附录剂量表）。

只读 CSV，不重新计算任何统计量——表里的每个数字都必须能在
results/eq_table.csv、eq_contrast.csv、compute_table.csv 里原样找到。

用法：
    python tools/make_table1.py            # 写 paper/table1.md
    python tools/make_table1.py --stdout   # 只打印
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"
OUT = ROOT / "paper" / "table1.md"
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TASK_LABEL = {"medmcqa": "MedMCQA（同域）", "medqa": "MedQA（跨任务）"}
METHOD_LABEL = {"nait": "nait（激活选择）", "random": "random（随机）",
                "rand_len": "rand_len（长度匹配随机）", "nait_dedup": "nait_dedup（去重后）"}


def f2(x, nd=2):
    if x is None or pd.isna(x):
        return "—"
    return f"{x:+.{nd}f}".replace("+", "+")


def ci(lo, hi, nd=2):
    if pd.isna(lo) or pd.isna(hi):
        return "—"
    return f"[{lo:+.{nd}f}, {hi:+.{nd}f}]"


def mark(b):
    if isinstance(b, str):
        b = b.strip().upper() == "TRUE"
    if pd.isna(b):
        return "—"
    return "✅" if bool(b) else "❌"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stdout", action="store_true")
    a = ap.parse_args()

    eq = pd.read_csv(RES / "eq_table.csv")
    con = pd.read_csv(RES / "eq_contrast.csv") if (RES / "eq_contrast.csv").exists() else None
    comp = pd.read_csv(RES / "compute_table.csv")

    L: list[str] = []
    L.append("# Table 1 — 30% 保留率下的等效性检验\n")
    L.append("非劣界 δ = 2.0 pp；Δ 为「子集 − 全量」，负数为掉点；"
             "CI 为逐题配对 bootstrap（2000 次，种子固定 7）。\n")
    L.append("| 任务 | 方法 | 种子 | 全量 acc | 子集 acc | Δ (pp) | 95% CI | 逐题等效 | 种子等效 | 种子范围 |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")

    rows = eq[eq["ratio"] == 0.30].copy()
    rows["task_order"] = rows["task"].map({"medmcqa": 0, "medqa": 1}).fillna(9)
    rows["method_order"] = rows["method"].map(
        {"nait": 0, "rand_len": 1, "random": 2, "nait_dedup": 3}).fillna(9)
    rows = rows.sort_values(["task_order", "method_order"])

    for _, r in rows.iterrows():
        seed_range = "—"
        if not pd.isna(r["seed_min_pp"]) and r["n_seed"] > 1:
            seed_range = f"{r['seed_min_pp']:+.2f} ~ {r['seed_max_pp']:+.2f}"
        L.append("| {t} | {m} | {n} | {af:.3f} | {as_:.3f} | {d} | {c} | {ei} | {es} | {sr} |".format(
            t=TASK_LABEL.get(r["task"], r["task"]), m=METHOD_LABEL.get(r["method"], r["method"]),
            n=int(r["n_seed"]), af=r["acc_full"], as_=r["acc_sub"], d=f2(r["delta_pp"]),
            c=ci(r["ci_lo_pp"], r["ci_hi_pp"]), ei=mark(r["equiv_item"]),
            es=mark(r["equiv_seed"]), sr=seed_range))

    if con is not None and len(con):
        L.append("\n# Table 2 — 方法间直接对比（30%）\n")
        L.append("| 任务 | A | B | Δ(A−B) | 逐种子 Δ | 合并 p (Stouffer) | 方向一致 |")
        L.append("|---|---|---|---|---|---|---|")
        cr = con[con["ratio"] == 0.30].copy()
        for _, r in cr.iterrows():
            L.append("| {t} | {a} | {b} | {d} | {ps} | {p} | {ss} |".format(
                t=TASK_LABEL.get(r["task"], r["task"]),
                a=METHOD_LABEL.get(r["method"], r["method"]),
                b=METHOD_LABEL.get(r["vs"], r["vs"]),
                d=f2(r["delta_pp"]),
                ps=str(r.get("per_seed_pp", "")).replace(";", " / "),
                p=("—" if pd.isna(r["stouffer_p"]) else f"{float(r['stouffer_p']):.3f}"),
                ss=mark(r.get("same_sign"))))

    L.append("\n# Table 3 — 算力净账（30%）\n")
    L.append("| 方法 | 训练 | 选择前向 | 合计 (GPU-h) | 净省 |")
    L.append("|---|---|---|---|---|")
    full = comp[comp["method"] == "full"]["gpu_hours"].mean()
    for m in ("nait", "rand_len", "random"):
        z = comp[(comp["method"] == m) & (comp["ratio"] == 0.30)]
        if not len(z):
            continue
        z = z.iloc[0]
        L.append("| {} | 训练 {:.3f} | {:.3f} | **{:.3f}** | **{:.0f}%** |".format(
            METHOD_LABEL.get(m, m), z["train_h"],
            z["select_h"], z["gpu_hours"], z["net_saving_pct"]))
    L.append("| 全量（基线） | 训练 {:.3f} | 0 | {:.3f} | 0% |".format(full, full))

    dose = eq[(eq["method"] == "nait")].copy()
    if len(dose):
        L.append("\n# 附录 A — nait 的剂量-反应\n")
        L.append("| 任务 | 保留 | 种子 | Δ (pp) | 95% CI | 逐题等效 |")
        L.append("|---|---|---|---|---|---|")
        dose["r"] = dose["ratio"].astype(float)
        for _, r in dose.sort_values(["task", "r"]).iterrows():
            L.append("| {} | {:.0f}% | {} | {} | {} | {} |".format(
                TASK_LABEL.get(r["task"], r["task"]), r["r"] * 100, int(r["n_seed"]),
                f2(r["delta_pp"]), ci(r["ci_lo_pp"], r["ci_hi_pp"]), mark(r["equiv_item"])))

    text = "\n".join(L) + "\n"
    if a.stdout:
        print(text)
    else:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(text, encoding="utf-8")
        print(f"写出 {OUT}  ({len(text)} 字符，{len(rows)} 行主表)")


if __name__ == "__main__":
    main()
