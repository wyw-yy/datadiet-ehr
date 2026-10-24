"""逐条确认上一轮承诺的四项修复是否真的落地（只读，不改任何数据）。

用法： .venv\\Scripts\\python.exe tools\\confirm_fixes.py
每条打印 ✅/❌ 与证据，最后给出总结；任一条失败退出码 1。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"
SUBS = ROOT / "data" / "subsets"
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

fails: list[str] = []


def check(ok: bool, name: str, detail: str) -> None:
    print(f"{'✅' if ok else '❌'} {name}  {detail}")
    if not ok:
        fails.append(name)


# ---------- 修复① sample_stats 用的是当前池子 ----------
print("\n① sample_stats.csv 是当前池子重导的吗")
p = RES / "sample_stats.csv"
if p.exists():
    ss = pd.read_csv(p)
    ids = set(ss["id"].astype(str))
    ids_cur = {json.loads(l)["id"] for l in (ROOT / "data" / "processed" / "train.jsonl").open(encoding="utf-8")}
    check(len(ss) == 12000, "行数 = 12000", f"{len(ss)}")
    check(len(ids & ids_cur) == len(ids), "所有 id 都在当前池子里",
          f"{len(ids & ids_cur)}/{len(ids)} 命中")
    col30 = [c for c in ss.columns if c == "nait_30"]
    if col30:
        n30 = int(ss[col30[0]].fillna(0).astype(bool).sum())
        check(n30 == 3600, "nait_30 选中 3600 条", str(n30))
    st = json.loads((RES / "select_stats.json").read_text(encoding="utf-8"))
    p50 = float(ss["act_score"].median())
    check(abs(p50 - st["score_quantiles"]["p50"]) < 5e-4,
          "score 中位数与 select_stats 一致",
          f"{p50:.6f} vs {st['score_quantiles']['p50']:.6f}")
else:
    check(False, "sample_stats.csv 存在", "缺文件")

# ---------- 修复② R 侧改逐种子 + Stouffer ----------
print("\n② 等价性统计改成逐种子 + Stouffer 了吗")
src = (ROOT / "R" / "01_equivalence.R").read_text(encoding="utf-8", errors="replace")
check("stouffer" in src.lower(), "R 脚本里有 stouffer()", "找到" if "stouffer" in src.lower() else "没找到")
check("eq_per_seed" in src, "会写 eq_per_seed.csv", "")
for f in ("eq_per_seed.csv", "eq_table.csv", "eq_contrast.csv"):
    q = RES / f
    ok = q.exists()
    n = len(pd.read_csv(q)) if ok else 0
    check(ok, f"{f} 存在", f"{n} 行")
ep = pd.read_csv(RES / "eq_per_seed.csv")
n_seed_30 = len(ep[(ep["ratio"] == 0.3) & (ep["task"] == "medmcqa") & (ep["method"] == "nait")])
check(n_seed_30 == 3, "MedMCQA nait@30% 逐种子行数 = 3", str(n_seed_30))
check("equiv_seed" in pd.read_csv(RES / "eq_table.csv").columns, "eq_table 有 equiv_seed 列", "")

# ---------- 修复③ 长度匹配臂 ----------
print("\n③ 长度匹配对照臂 rand_len 备好了吗")
rl = SUBS / "subsets_randlen.json"
check(rl.exists(), "subsets_randlen.json 存在", "")
if rl.exists():
    d = json.loads(rl.read_text(encoding="utf-8"))
    body = d.get("rand_len", {})
    check(sorted(body.keys()) == ["10", "20", "30", "50", "70"],
          "五档比例齐全", str(sorted(body.keys())))
    check(len(body.get("30", [])) == 3600, "30% 档 3600 条", str(len(body.get("30", []))))
    pool_ids = {json.loads(l)["id"] for l in (ROOT / "data" / "processed" / "train.jsonl").open(encoding="utf-8")}
    bad = [i for i in body.get("30", []) if i not in pool_ids]
    check(not bad, "rand_len 的 id 全在训练池里", f"{len(bad)} 个越界")
cfg = (ROOT / "config.py").read_text(encoding="utf-8", errors="replace")
check("rand_len" in cfg, "config.METHODS 里有 rand_len", "")
st_rl = RES / "select_stats_randlen.json"
if st_rl.exists():
    j = json.loads(st_rl.read_text(encoding="utf-8"))
    worst = max(abs(v["len_diff_pct"]) for v in j["ratios"].values())
    check(worst < 2.0, "各档长度差 < 2%", f"最大 {worst:.2f}%")
else:
    check(False, "select_stats_randlen.json 存在", "缺文件")

# ---------- 修复④ 审计链 ----------
print("\n④ 审计链与文档口径")
for f in ("code_manifest.json", "ARTIFACTS.sha256", "selection_log.jsonl"):
    q = ROOT / "audit" / f
    ok = q.exists()
    extra = ""
    if ok and f == "selection_log.jsonl":
        extra = f"{len(q.read_text(encoding='utf-8').strip().splitlines())} 条"
    if ok and f == "ARTIFACTS.sha256":
        extra = f"{len(q.read_text(encoding='utf-8').strip().splitlines())} 个产物"
    check(ok, f"audit/{f} 存在", extra)

proto = (ROOT / "docs" / "PROTOCOL.md").read_text(encoding="utf-8", errors="replace")
check("99.08" in proto and "11,639" not in proto, "PROTOCOL 已改成本池数字", "99.08% 在、旧 11,639 不在")
check("9.5" in proto and "rand_len" in proto, "PROTOCOL 写了 rand_len 臂", "")
check("9.6" in proto, "PROTOCOL 写了统计口径节", "")

print()
if fails:
    print(f"❌ 未通过 {len(fails)} 项：{fails}")
    sys.exit(1)
print("✅ 四项修复全部落地，证据如上。")
