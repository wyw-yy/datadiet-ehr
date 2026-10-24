"""make_randlen.py —— 生成「长度匹配的随机子集」（对照臂 rand_len）。

为什么要这个臂：
    审计发现 nait 选中的样本平均比池子长 12.3%（188.1 vs 166.8 字符）。
    也就是说"激活得分"里掺了"偏爱长文本"的成分。
    如果 rand_len（同样长度分布、但随机挑）与 nait 表现一样，
    那"激活选择"的真实解释就要降级为"长度/信息量代理"。
    这条对照是审稿人一定会问的（见 docs/PREREG.md §6）。

做法：
    对每个保留比例 r：
      1. 取 nait 在该比例下选中的样本 id，统计它们的长度十分位分布；
      2. 在池子里按同样的十分位配额随机抽样（不重复，seed 固定）；
      3. 输出与 subsets.json 相同结构，供 train.py 直接读。

用法：
    .venv\\Scripts\\python.exe tools\\make_randlen.py
    .venv\\Scripts\\python.exe tools\\make_randlen.py --seed 7 --check
输出：
    data/subsets/subsets_randlen.json
    results/select_stats_randlen.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import config as C  # noqa: E402

N_BINS = 20


def read_jsonl(p: Path) -> list[dict]:
    with open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--check", action="store_true", help="只校验长度分布是否匹配")
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)
    pool = read_jsonl(C.PROC / "train.jsonl")[: C.N_POOL]
    ids = [r["id"] for r in pool]
    lens = np.array([len(r["instruction"]) for r in pool], dtype=float)
    pos = {sid: i for i, sid in enumerate(ids)}

    # 用池子自己的长度分位切桶，保证每桶样本量可比
    edges = np.quantile(lens, np.linspace(0, 1, N_BINS + 1))
    edges[-1] = np.inf
    bins = np.digitize(lens, edges[1:-1])          # 0..N_BINS-1
    members = [np.where(bins == b)[0] for b in range(N_BINS)]

    subs_p = C.SUBSETS / "subsets.json"
    if not subs_p.exists():
        raise SystemExit(f"missing {subs_p} - run select_subset.py first")
    subs = json.loads(subs_p.read_text(encoding="utf-8"))
    if "nait" not in subs:
        raise SystemExit("subsets.json has no 'nait' entry")

    out_subs: dict[str, dict[str, list[str]]] = {"rand_len": {}}
    report = {"seed": args.seed, "n_bins": N_BINS, "edges": [float(e) for e in edges[:-1]],
              "pool_mean_len": float(lens.mean()), "ratios": {}}

    for pct, sel_ids in sorted(subs["nait"].items(), key=lambda kv: int(kv[0])):
        sel_idx = np.array([pos[s] for s in sel_ids if s in pos], dtype=int)
        want = np.bincount(bins[sel_idx], minlength=N_BINS)   # 目标：每个长度桶要多少条

        chosen: list[int] = []
        for b in range(N_BINS):
            need = int(want[b])
            if need <= 0:
                continue
            cand = np.setdiff1d(members[b], np.array(chosen, dtype=int), assume_unique=False)
            if len(cand) >= need:
                pick = rng.choice(cand, size=need, replace=False)
            else:
                pick = cand                                    # 桶不够就全要，差额后面补
            chosen.extend(int(x) for x in pick)

        # 数量兜底：差额从剩余样本里随机补齐（极少触发）
        if len(chosen) < len(sel_idx):
            rest = np.setdiff1d(np.arange(len(pool)), np.array(chosen, dtype=int))
            extra = rng.choice(rest, size=len(sel_idx) - len(chosen), replace=False)
            chosen.extend(int(x) for x in extra)

        chosen_ids = [ids[i] for i in sorted(set(chosen))]
        out_subs["rand_len"][pct] = chosen_ids

        cl = lens[[pos[i] for i in chosen_ids]]
        report["ratios"][pct] = {
            "n": len(chosen_ids),
            "nait_mean_len": float(lens[sel_idx].mean()),
            "randlen_mean_len": float(cl.mean()),
            "len_diff_pct": float((cl.mean() - lens[sel_idx].mean()) / lens[sel_idx].mean() * 100),
            "bin_counts_nait": want.tolist(),
            "bin_counts_randlen": np.bincount(bins[[pos[i] for i in chosen_ids]], minlength=N_BINS).tolist(),
        }

    out_p = C.SUBSETS / "subsets_randlen.json"
    if args.check and out_p.exists():
        old = json.loads(out_p.read_text(encoding="utf-8"))
        same = old.get("rand_len") == out_subs["rand_len"]
        print(f"{'✅' if same else '❌'} 重跑结果与磁盘上的一致（seed={args.seed}）")
        rep = json.loads((C.RESULTS / "select_stats_randlen.json").read_text(encoding="utf-8"))
        report = rep

    if not args.check:
        out_p.write_text(json.dumps(out_subs, ensure_ascii=False), encoding="utf-8")
        (C.RESULTS / "select_stats_randlen.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n池子平均长度 {lens.mean():.1f} 字符")
    print(f"{'比例':>4} {'n':>6} {'nait均长':>10} {'rand_len均长':>13} {'差%':>8}")
    for pct, rr in sorted(report["ratios"].items(), key=lambda kv: int(kv[0])):
        print(f"{pct:>4}% {rr['n']:>6} {rr['nait_mean_len']:>10.1f} "
              f"{rr['randlen_mean_len']:>13.1f} {rr['len_diff_pct']:>+8.2f}")
    print(f"\n{'已写出' if not args.check else '已校验'}：{out_p.relative_to(ROOT)}")
    print("  → train.py --method rand_len 即可用")


if __name__ == "__main__":
    main()
