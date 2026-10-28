"""make_release.py —— 打一个"可公开/可送审"的成果包。

为什么要这个脚本：仓库里混着三类东西——
  ① 该公开的证据（代码、协议、表格、逐题预测、子集 id、审计哈希）
  ② 不该公开的大件（权重 2.6 GB、激活 358 MB）——但它们可由①+公开数据重建
  ③ 根本不能公开的（MIMIC 派生文本、.venv、日志、临时目录）
手打 zip 迟早会把②③混进去，所以用**白名单**而不是黑名单。

产物：
  dist/datadiet-ehr-v<VERSION>.zip
  dist/datadiet-ehr-v<VERSION>.manifest.txt   （每个文件一行 sha256 + 字节数）

用法：
    .venv\\Scripts\\python.exe tools\\make_release.py            # 默认 1.0.0
    .venv\\Scripts\\python.exe tools\\make_release.py --version 1.0.1
"""

import argparse
import hashlib
import subprocess
import sys
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 只有这些前缀/后缀会进包（白名单）
INCLUDE_FILES = [
    "config.py", "prepare_data.py", "prepare_mimic.py", "collect_acts.py",
    "select_subset.py", "train.py", "eval.py", "gen_eval.py", "run_one.py",
    "README.md", "RESULTS.md", "PLAN.md", "GLOSSARY.md", "LICENSE",
    "CITATION.cff", "requirements-lock.txt", ".gitignore",
]
INCLUDE_DIRS = ["R", "tools", "docs", "paper", "audit", "results", "data/subsets",
                "data/processed", "results_round1_12k", "results_round2_24k"]

# 即便落在白名单目录里也不要（体积或隐私）
DENY_SUFFIX = {".npz", ".safetensors", ".bin", ".pt", ".pth", ".whl", ".pdf"}
DENY_PARTS = {"__pycache__", ".git", ".venv", "raw", "processed_mimic",
              "processed_mimic_fake", "tmp", "models", "cache", "logs", "softcopyright"}
DENY_NAME_PREFIX = ("~$",)


def wanted(p: Path) -> bool:
    rel = p.relative_to(ROOT)
    parts = set(rel.parts)
    if parts & DENY_PARTS:
        return False
    if p.suffix in DENY_SUFFIX:
        return False
    if p.name.startswith(DENY_NAME_PREFIX):
        return False
    return True


def collect() -> list[Path]:
    files: list[Path] = []
    for name in INCLUDE_FILES:
        p = ROOT / name
        if p.exists() and wanted(p):
            files.append(p)
    for d in INCLUDE_DIRS:
        base = ROOT / d
        if not base.exists():
            continue
        for p in sorted(base.rglob("*")):
            if p.is_file() and wanted(p):
                files.append(p)
    return sorted(set(files))


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "unknown"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="1.0.0")
    a = ap.parse_args()

    files = collect()
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    zip_path = dist / f"datadiet-ehr-v{a.version}.zip"
    man_path = dist / f"datadiet-ehr-v{a.version}.manifest.txt"

    total = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in files:
            rel = p.relative_to(ROOT).as_posix()
            z.write(p, rel)
            total += p.stat().st_size

    lines = [
        f"DataDiet-EHR artifact v{a.version}",
        f"built:    {date.today().isoformat()}",
        f"commit:   {git_commit()}",
        f"files:    {len(files)}",
        f"raw size: {total / 1024 / 1024:.1f} MB",
        f"zip size: {zip_path.stat().st_size / 1024 / 1024:.1f} MB",
        "",
        "sha256                                                           bytes  path",
    ]
    for p in files:
        lines.append(f"{sha256(p)}  {p.stat().st_size:>9}  {p.relative_to(ROOT).as_posix()}")
    man_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"包：{zip_path.relative_to(ROOT)}  ({zip_path.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"清单：{man_path.relative_to(ROOT)}  ({len(files)} 个文件)")
    print("\n按目录统计：")
    counted: dict[str, int] = {}
    for p in files:
        top = p.relative_to(ROOT).parts[0]
        counted[top] = counted.get(top, 0) + 1
    for k in sorted(counted, key=lambda x: -counted[x]):
        print(f"  {k:<22}{counted[k]:>5} 个文件")
    if zip_path.stat().st_size > 100 * 1024 * 1024:
        print("\n[警告] 包超过 100 MB，Zenodo 没问题但 GitHub Release 会吃力")


if __name__ == "__main__":
    sys.exit(main())
