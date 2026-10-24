"""make_audit.py —— 生成审计链：代码清单 / 产物哈希 / 选择过程日志。

提案 02④ 要求「子集选择过程须可审计」。这个脚本产出三份东西：

    audit/code_manifest.json   每个 .py/.R/.bat 的 sha256 + 大小 + 修改时间
    audit/ARTIFACTS.sha256     关键产物的 sha256sum 格式清单（可 diff、可传给审稿人）
    audit/selection_log.jsonl  每一次子集选择的输入哈希、参数、输出哈希

用法：
    .venv\\Scripts\\python.exe tools\\make_audit.py
    .venv\\Scripts\\python.exe tools\\make_audit.py --check   # 只校验不写
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import config as C  # noqa: E402

AUDIT = ROOT / "audit"
CODE_EXT = {".py", ".R", ".bat", ".ps1", ".json", ".toml", ".txt"}
SKIP_DIRS = {".venv", "cache", "results", "data", "models", "__pycache__", ".git", "audit"}


def sha256(p: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def code_files() -> list[Path]:
    out = []
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.relative_to(ROOT).parts[:-1]):
            continue
        if p.suffix in CODE_EXT:
            out.append(p)
    return sorted(out)


def artifact_files() -> list[Path]:
    pats = [
        (C.PROC, "*.jsonl"),
        (C.SUBSETS, "*.json"),
        (ROOT / "cache" / "acts", "*.npz"),
        (C.RESULTS, "*.csv"),
        (C.RESULTS, "*.json"),
        (C.RESULTS / "preds", "*.csv.gz"),
        (C.RESULTS / "runs", "*.json"),
        (ROOT / "paper" / "figures", "*.png"),
    ]
    out = []
    for d, pat in pats:
        if d.exists():
            out.extend(sorted(d.glob(pat)))
    return out


def selection_log() -> list[dict]:
    """把 select_stats*.json + subsets*.json 拆成「每方法每比例一行」的审计记录。"""
    recs = []
    for stats_p in sorted(C.RESULTS.glob("select_stats*.json")):
        suffix = stats_p.stem.replace("select_stats", "")
        subs_p = C.SUBSETS / f"subsets{suffix}.json"
        stats = json.loads(stats_p.read_text(encoding="utf-8"))
        acts_train = ROOT / "cache" / "acts" / "acts_train.npz"
        acts_probe = ROOT / "cache" / "acts" / f"acts_probe{suffix}.npz"
        if not acts_probe.exists():
            acts_probe = ROOT / "cache" / "acts" / "acts_probe.npz"
        sq = stats.get("score_quantiles") or {}
        pq = stats.get("pair_cosine_quantiles") or {}
        base = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "suffix": suffix or "(default)",
            "probe_split": stats.get("probe_split"),
            "n_train": stats.get("n_train"),
            "n_probe": stats.get("n_probe"),
            "layers": stats.get("layers"),
            "dedup_cos": stats.get("dedup_cos"),
            "dedupe_kept": stats.get("dedupe_kept"),
            "dedupe_kept_pct": stats.get("dedupe_kept_pct"),
            "score_p50": sq.get("p50"),
            "score_max": sq.get("max"),
            "pair_cos_p50": pq.get("p50"),
            "pair_cos_p99": pq.get("p99"),
            "dept_counts": stats.get("dept_counts"),
            "acts_train_sha256": sha256(acts_train) if acts_train.exists() else None,
            "acts_probe_sha256": sha256(acts_probe) if acts_probe.exists() else None,
            "subsets_sha256": sha256(subs_p) if subs_p.exists() else None,
            "stats_sha256": sha256(stats_p),
        }
        sizes = stats.get("subset_sizes") or {}
        for method, per_ratio in sizes.items():
            if not isinstance(per_ratio, dict):
                continue
            for ratio, n in per_ratio.items():
                recs.append({**base, "method": method, "ratio": ratio, "n_selected": n})
    return recs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只校验已有清单，不重写")
    args = ap.parse_args()

    AUDIT.mkdir(exist_ok=True)

    # ---------- 1. 代码清单 ----------
    codes = code_files()
    manifest = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "project": str(ROOT),
        "python": sys.version.split()[0],
        "n_files": len(codes),
        "files": [
            {
                "path": str(p.relative_to(ROOT)).replace("\\", "/"),
                "sha256": sha256(p),
                "size": p.stat().st_size,
                "mtime": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(p.stat().st_mtime)),
            }
            for p in codes
        ],
    }
    body = json.dumps(manifest["files"], sort_keys=True).encode()
    manifest["manifest_sha256"] = hashlib.sha256(body).hexdigest()

    # ---------- 2. 产物哈希 ----------
    arts = artifact_files()
    lines = [f"{sha256(p)}  {p.relative_to(ROOT).as_posix()}" for p in arts]

    # ---------- 3. 选择日志 ----------
    recs = selection_log()

    if args.check:
        have_manifest = (AUDIT / "code_manifest.json").exists()
        have_hash = (AUDIT / "ARTIFACTS.sha256").exists()
        old = {}
        if have_hash:
            for line in (AUDIT / "ARTIFACTS.sha256").read_text(encoding="utf-8").splitlines():
                if "  " in line:
                    h, _, p = line.partition("  ")
                    old[p] = h
        now = {p.relative_to(ROOT).as_posix(): l.split("  ")[0] for p, l in zip(arts, lines)}
        changed = [k for k in now if k in old and old[k] != now[k]]
        added = [k for k in now if k not in old]
        removed = [k for k in old if k not in now]
        print(f"code_manifest.json   {'✅ 存在' if have_manifest else '❌ 缺失'}")
        print(f"ARTIFACTS.sha256     {'✅ 存在' if have_hash else '❌ 缺失'}  （{len(old)} 条）")
        print(f"产物现状             {len(now)} 个")
        print(f"  变化 {len(changed)}  新增 {len(added)}  消失 {len(removed)}")
        for k in changed[:10]:
            print(f"    ~ {k}")
        ok = have_manifest and have_hash and not changed and not removed
        print("结果：" + ("✅ 审计链完整，产物未变" if ok else "⚠️ 审计链需要重跑 tools/make_audit.py"))
        sys.exit(0 if ok else 1)

    (AUDIT / "code_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (AUDIT / "ARTIFACTS.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with open(AUDIT / "selection_log.jsonl", "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"代码清单   {len(codes):4d} 个文件 → audit/code_manifest.json")
    print(f"           manifest_sha256 = {manifest['manifest_sha256'][:16]}…")
    print(f"产物哈希   {len(arts):4d} 个文件 → audit/ARTIFACTS.sha256")
    print(f"选择日志   {len(recs):4d} 条记录 → audit/selection_log.jsonl")
    if recs:
        r0 = recs[0]
        print(f"           例：suffix={r0['suffix']} ratio={r0['ratio']} "
              f"n={r0['n_selected']} dedupe_kept={r0['dedupe_kept_pct']}%")


if __name__ == "__main__":
    main()
