"""Check that every artifact listed in audit/ARTIFACTS.sha256 still matches.

Why: the fix-a-number workflow is "CSV -> R/Python -> doc", so the failure mode
that actually happens is a CSV being rewritten (new run) while the committed
hash file, tables and docs still describe the old one. This script turns that
into an immediate error instead of a silent inconsistency.

Usage
    python tools/audit_check_manifest.py            # verify hashes
    python tools/audit_check_manifest.py --missing-ok   # only report, exit 0

In CI only *committed* artifacts exist; data/ and models/ are gitignored, so
missing files are reported and (with --missing-ok) do not fail the build.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "audit" / "ARTIFACTS.sha256"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--missing-ok", action="store_true",
                    help="gitignored artifacts (data/, models/) may be absent without failing")
    a = ap.parse_args()

    if not MANIFEST.exists():
        print(f"no manifest at {MANIFEST}")
        return 0

    bad, missing, ok = [], [], 0
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        digest, _, rel = line.partition("  ")
        p = ROOT / rel
        if not p.exists():
            missing.append(rel)
            continue
        if sha256(p) != digest:
            bad.append(rel)
        else:
            ok += 1

    print(f"manifest: {ok} match, {len(bad)} changed, {len(missing)} missing")
    for rel in bad[:20]:
        print(f"  CHANGED  {rel}")
    for rel in missing[:20]:
        print(f"  MISSING  {rel}")

    if bad:
        print("→ 产物变了但清单没更新：重跑 tools/make_audit.py，再更新引用这些数字的文档。")
        return 1
    if missing and not a.missing_ok:
        print("→ 有产物缺失（CI 里正常：data/ 与 models/ 不入库）；本地请先跑流水线。")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
