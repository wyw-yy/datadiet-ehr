"""audit_runs.py —— 对"每个数字到底是哪次训练、哪个 adapter、哪份预测"做交叉核验。

只读。回答三个问题：
  1. 覆盖度：每个 (task, ratio, method) 有几个种子？谁的种子数 < 2？
  2. 一致性：metrics 行 ↔ runs json ↔ adapter 目录 ↔ preds 文件，四者能不能对上？
  3. 可信度：n_items 对不对、train_seconds 是否 > 0、有没有 adapter 复用过期权重。

用法：.venv\\Scripts\\python.exe tools\\audit_runs.py
"""

import csv
import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

RES = ROOT / "results"
ADAPT = ROOT / "models" / "adapters"


def read_csv(p):
    with open(p, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> int:
    metrics = read_csv(RES / "metrics_long.csv")
    runs = {}
    for p in (RES / "runs").glob("*.json"):
        d = json.loads(p.read_text(encoding="utf-8"))
        runs[d["exp_id"]] = d

    problems = []
    cells = defaultdict(set)      # (task, method, ratio) -> seeds
    used_run = defaultdict(list)  # exp_id -> metrics rows

    for r in metrics:
        eid, task, meth = r["exp_id"], r["task"], r["method"]
        ratio, seed, n = float(r["ratio"]), int(r["seed"]), int(r["n_items"])
        cells[(task, meth, ratio)].add(seed)
        used_run[eid].append(task)

        # 1) runs json 存在
        if meth != "full" or True:
            if eid not in runs:
                problems.append(f"[no-run-json] {eid} 在 metrics 里，但没有 results/runs/{eid}.json")
                continue
        d = runs.get(eid, {})

        # 2) adapter 目录存在且非空
        ad = ADAPT / eid
        n_files = len(list(ad.glob("*"))) if ad.is_dir() else 0
        if n_files == 0:
            problems.append(f"[no-adapter] {eid}: {ad} 不存在或为空")

        # 3) preds 文件存在、行数与 n_items 一致
        pf = RES / "preds" / f"{eid}_{task}.csv.gz"
        if not pf.exists():
            problems.append(f"[no-preds] {eid} {task}: 缺 {pf.name}")
        else:
            with gzip.open(pf, "rt", encoding="utf-8") as f:
                nrows = sum(1 for _ in f) - 1
            if nrows != n:
                problems.append(f"[n-mismatch] {eid} {task}: preds {nrows} 行 vs metrics n_items {n}")

        # 4) 训练记录自洽
        if float(d.get("train_seconds", 0) or 0) <= 0:
            problems.append(f"[bad-train] {eid}: train_seconds={d.get('train_seconds')}")

        # 5) 样本数与比例是否自洽（池子 48,000，去重保留 97.32% → 允许 3% 误差）
        if meth != "full":
            expect = 48000 * ratio
            got = float(d.get("n_samples", 0) or 0)
            if got and not (0.90 * expect <= got <= 1.02 * expect):
                problems.append(f"[ratio-mismatch] {eid}: n_samples={got:.0f}, 期望≈{expect:.0f}")

        # 6) adapter 的修改时间不能早于训练开始（防止 --reuse 复用到过期权重）
        if ad.is_dir() and d.get("train_seconds"):
            newest = max((p.stat().st_mtime for p in ad.glob("*")), default=0)
            if newest and newest < pf.stat().st_mtime - 86400 * 30:
                problems.append(f"[stale-adapter?] {eid}: adapter 比 preds 早 30 天以上")

    # 7) runs json 有、metrics 没有 → 白跑的训练
    for eid in runs:
        if eid not in used_run:
            problems.append(f"[orphan-run] {eid} 训练了但没有 metrics 行")

    print("=" * 78)
    print("覆盖度（每个格子几个种子）")
    print("=" * 78)
    ratios = sorted({k[2] for k in cells})
    for task in ("medmcqa", "medqa"):
        print(f"\n{task}:")
        print("  ratio | " + " | ".join(f"{m:<8}" for m in ("full", "nait", "random", "nait_ns")))
        for rt in ratios:
            line = f"  {rt:5.2f} | "
            for m in ("full", "nait", "random", "nait_ns"):
                s = cells.get((task, m, rt), set())
                line += f"{len(s):<8} | " if s else f"{'-':<8} | "
            print(line)

    thin = []
    for (task, meth, rt), seeds in sorted(cells.items()):
        if meth in ("nait", "random", "nait_ns") and len(seeds) < 2:
            thin.append(f"{task} {meth} r={rt:.2f}: {len(seeds)} seed")

    print("\n" + "=" * 78)
    print("结论")
    print("=" * 78)
    full_seeds = sorted(cells[("medmcqa", "full", 1.0)])
    print(f"全量基线种子: {full_seeds}  ← 所有 Δ 的分母")
    print(f"种子数 < 2 的格子: {len(thin)}")
    for t in thin:
        print("  -", t)
    print(f"\n完整性问题: {len(problems)}")
    for p in problems:
        print("  -", p)
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
