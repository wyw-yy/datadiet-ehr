"""audit_final.py —— 最后一关：交叉核对所有产物与文档，任何一条不一致就不放行。

前面几个检查器各自看一块（verify = 数据是否干净，audit_run = 数字是否真跑出来的，
audit_deep2 = 有没有陈旧产物/符号翻转/混杂）。这个脚本做**交叉核对**：

    A  sample_stats.csv 是否属于当前训练池
    B  eq_table 的数字是否能由 eq_per_seed 重新聚合出来
    C  RESULTS.md 里的数字是否都能在 results/headline.json 里找到
    D  subsets_randlen.json 的长度匹配是否真的匹配
    E  preds 行数是否与 eq_table 的 n_item 一致
    F  审计链（audit/）是否覆盖所有结果文件

用法：
    .venv\\Scripts\\python.exe tools\\audit_final.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import config as C  # noqa: E402

OK, BAD = "✅", "❌"
fails: list[str] = []


def check(cond: bool, label: str, detail: str = "") -> None:
    print(f"  {OK if cond else BAD} {label}" + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(label)


def read_csv(p: Path) -> list[dict]:
    with open(p, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_jsonl(p: Path) -> list[dict]:
    with open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


print("=" * 74)
print("A. sample_stats.csv 是否属于当前训练池")
print("=" * 74)
pool = read_jsonl(C.PROC / "train.jsonl")[: C.N_POOL]
pool_ids = {r["id"] for r in pool}
ss = read_csv(C.RESULTS / "sample_stats.csv")
ss_ids = {r["id"] for r in ss}
check(len(ss) == len(pool), "行数等于池子大小", f"{len(ss)} vs {len(pool)}")
check(ss_ids <= pool_ids, "id 全部来自当前池子", f"{len(ss_ids - pool_ids)} 个不在池里")
n30_expected = int(round(C.N_POOL * 0.30))
check(sum(int(r["nait_30"]) for r in ss) == n30_expected, f"nait_30 选中 {n30_expected} 条")
subs = json.loads((C.SUBSETS / "subsets.json").read_text(encoding="utf-8"))
check(len(set(subs["nait"]["30"])) == n30_expected, f"subsets.json 里 nait/30 也是 {n30_expected} 条")

print()
print("=" * 74)
print("B. eq_table 的数字能否由 eq_per_seed 重新聚合")
print("=" * 74)
per = read_csv(C.RESULTS / "eq_per_seed.csv")
tab = read_csv(C.RESULTS / "eq_table.csv")
agg = defaultdict(list)
for r in per:
    agg[f"{r['task']}|{r['method']}|{r['ratio']}"].append(float(r["delta_pp"]))
worst = 0.0
for r in tab:
    k = f"{r['task']}|{r['method']}|{r['ratio']}"
    if k not in agg:
        continue
    want = float(np.mean(agg[k]))
    got = float(r["delta_pp"])
    worst = max(worst, abs(want - got))
check(worst < 0.02, "eq_table.delta_pp == mean(per_seed.delta_pp)", f"最大偏差 {worst:.3f}pp")

for r in tab:
    k = f"{r['task']}|{r['method']}|{r['ratio']}"
    n = len(agg.get(k, []))
    if int(r["n_seed"]) != n:
        check(False, f"{k} n_seed 一致", f"{r['n_seed']} vs {n}")
        break
else:
    check(True, "每行的 n_seed 与实际种子数一致")

print()
print("=" * 74)
print("C. 四份文档的数字能否在 results/ 的 CSV/JSON 里找到")
print("=" * 74)
import re
hp = C.RESULTS / "headline.json"
if hp.exists():
    canon = set()

    def add(v) -> None:
        if isinstance(v, bool) or v is None:
            return
        try:
            f = float(v)
        except (TypeError, ValueError):
            return
        canon.update({f"{f:.2f}", f"{f:+.2f}", f"{abs(f):.2f}", f"{f:g}"})

    head = json.loads(hp.read_text(encoding="utf-8"))
    for v in head.values():
        for vv in (v.values() if isinstance(v, dict) else [v]):
            add(vv)

    # 文档里引用的逐种子数字、对比数字也要能溯源
    for r in read_csv(C.RESULTS / "eq_per_seed.csv"):
        for col in ("delta_pp", "ci_lo_pp", "ci_hi_pp", "acc_full", "acc_sub", "mcnemar_p"):
            add(r[col])
    for r in read_csv(C.RESULTS / "eq_contrast.csv"):
        for col in ("delta_pp", "seed_min_pp", "seed_max_pp", "seed_sd_pp", "stouffer_p"):
            add(r[col])
        for tok in re.findall(r"[-+]?\d+\.\d+", r.get("per_seed_pp", "") + " " + r.get("per_seed_p", "")):
            add(tok)
    for r in read_csv(C.RESULTS / "compute_table.csv"):
        for col in ("gpu_hours", "select_overhead_h", "net_saving_pct", "acc"):
            add(r.get(col))
    for r in read_csv(C.RESULTS / "robust.csv"):
        for col in ("delta_pp", "ci_lo_pp", "ci_hi_pp", "acc_full", "acc_sub"):
            add(r.get(col))
    if (C.RESULTS / "select_stats_randlen.json").exists():
        import json as _json
        _rl = _json.loads((C.RESULTS / "select_stats_randlen.json").read_text(encoding="utf-8"))
        for _k, _v in (_rl.get("ratios") or {}).items():
            add(_v.get("len_diff_pct"))
            if _v.get("len_diff_pct") is not None:
                add(abs(float(_v["len_diff_pct"])))

    # 文档里允许出现的"非结果类"小数：
    #   阈值/参数（δ=2.00、cos=0.95）、实测耗时（0.166 s/样本）、功效表里的 t 临界值、
    #   池子规模（12.00 千条 = 12,000）、去重保留率 99.08%，
    #   以及两处**已推导**的数字：0.87 = nait_dedup(−1.18) − nait(−0.31)，
    #   0.97 来自记号 "t(0.975, n−1)" 的分位数，不是数据。
    allowed = {"2.00", "0.95", "0.166", "1.04", "2.58", "1.29", "1.09",
               "12.00", "99.08", "0.92", "0.96", "0.00", "0.87", "0.97",
               # 下面这些是参数/约定，不是实验结果
               "0.30", "0.05", "0.10", "0.20", "0.50", "0.70", "0.90",
               "1.00", "0.99", "0.98", "0.0019", "0.2588",
               # PREREG 的功效表：t(0.975, df) 分位数，查表得来的常数
               "4.30", "2.77", "2.78", "2.57", "2.26"}

    doc_dirs = [ROOT / "RESULTS.md", ROOT / "README.md",
                ROOT / "docs" / "ALIGNMENT.md", ROOT / "docs" / "PREREG.md"]
    all_miss = {}
    for p in doc_dirs:
        if not p.exists():
            continue
        doc = p.read_text(encoding="utf-8")
        nums = set(re.findall(r"-?\d+\.\d{2}", doc))
        miss = sorted(n for n in nums if n not in canon and n.lstrip("+") not in canon
                      and f"{abs(float(n)):.2f}" not in canon and n not in allowed)
        if miss:
            all_miss[p.name] = miss
    check(not all_miss, "四份文档（RESULTS/README/ALIGNMENT/PREREG）无孤立数字",
          f"{sum(len(v) for v in all_miss.values())} 个来源不明：{all_miss}")
else:
    check(False, "results/headline.json 存在")

print()
print("=" * 74)
print("D. rand_len 子集的长度匹配质量")
print("=" * 74)
rp = C.SUBSETS / "subsets_randlen.json"
if rp.exists():
    rl = json.loads(rp.read_text(encoding="utf-8"))["rand_len"]
    lens = {r["id"]: len(r["instruction"]) for r in pool}
    print(f"  {'比例':>4} {'n':>6} {'nait均长':>9} {'rand_len均长':>12} {'差%':>7} {'id合法':>6}")
    allok = True
    for pct in ("10", "20", "30", "50", "70"):
        r_ids = rl.get(pct, [])
        n_ids = subs["nait"][pct]
        ok_ids = set(r_ids) <= pool_ids and len(set(r_ids)) == len(r_ids)
        mr = np.mean([lens[i] for i in r_ids]) if r_ids else 0
        mn = np.mean([lens[i] for i in n_ids])
        d = (mr - mn) / mn * 100
        print(f"  {pct:>3}% {len(r_ids):>6} {mn:>9.1f} {mr:>12.1f} {d:>+7.2f} {str(ok_ids):>6}")
        allok &= ok_ids and len(r_ids) == len(n_ids) and abs(d) < 2.0
    check(allok, "每个比例的条数一致、id 合法、长度差 <2%")
else:
    check(False, "subsets_randlen.json 存在")

print()
print("=" * 74)
print("E. preds 行数是否与 eq_table.n_item 一致")
print("=" * 74)
bad = []
for r in per:
    eid = f"full_s{r['seed']}" if r["method"] == "full" else \
        f"{r['method']}_r{int(round(float(r['ratio']) * 100)):02d}_s{r['seed']}"
    p = C.PREDS / f"{eid}_{r['task']}.csv.gz"
    if not p.exists():
        bad.append((eid, r["task"], "missing"))
        continue
    import gzip
    with gzip.open(p, "rt", encoding="utf-8") as f:
        n = sum(1 for _ in f) - 1
    if n != int(r["n_item"]):
        bad.append((eid, r["task"], f"{n} vs {r['n_item']}"))
check(not bad, "所有 preds 行数 = n_item", f"{len(bad)} 处不符 {bad[:3]}")

print()
print("=" * 74)
print("F. 审计链是否覆盖所有结果文件")
print("=" * 74)
hp2 = ROOT / "audit" / "ARTIFACTS.sha256"
if hp2.exists():
    listed = {line.split("  ", 1)[1] for line in hp2.read_text(encoding="utf-8").splitlines() if "  " in line}
    need = [p for p in (C.RESULTS.glob("*.csv"))] + [C.RESULTS / "headline.json"]
    missing = [p.name for p in need if p.relative_to(ROOT).as_posix() not in listed]
    check(not missing, "结果 CSV 都在 ARTIFACTS.sha256 里", f"缺 {missing[:5]}")
    cm = ROOT / "audit" / "code_manifest.json"
    check(cm.exists(), "code_manifest.json 存在")
    if cm.exists():
        man = json.loads(cm.read_text(encoding="utf-8"))
        check(man["n_files"] >= 40, "代码清单文件数合理", f"{man['n_files']} 个")
else:
    check(False, "audit/ARTIFACTS.sha256 存在")

print()
print("=" * 74)
if fails:
    print(f"{len(fails)} 项未通过：")
    for f_ in fails:
        print("   -", f_)
    sys.exit(1)
print("全部通过。可以拿这批数字写文章。")
