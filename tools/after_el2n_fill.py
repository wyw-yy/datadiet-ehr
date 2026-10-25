"""After the EL2N round finishes, fill the 30% arm up to six seeds, then re-run the analysis.

Why: docs/PREREG.md section 5 says the formal run needs six seeds. Round 2 (24k pool)
only has seeds 1-3 for `full` / `nait` / `random` / `rand_len`, which is why four of the
six equivalence cells come out as "cannot judge" under the seed-level criterion.
This script adds seeds 4-6 for the 30% arm only - a bounded ~6 h job that fits in one
night - then regenerates every table, figure and audit from the larger sample.

Chain:
    1. wait until el2n_wait.log says the EL2N round finished (so the two queues never overlap)
    2. tools/night_queue.py --plan fill30        (9 runs: full s4-6 + 3 arms @30% s4-6)
    3. report_numbers -> Rscript R/run_all.R -> make_table1 -> make_audit -> audit_final

Run it as a managed background job:
    .venv\\Scripts\\python.exe tools/after_el2n_fill.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = ROOT / ".venv" / "Scripts" / "python.exe"
RSCRIPT = Path(r"C:\Program Files\R\R-4.6.1\bin\x64\Rscript.exe")
EL2N_LOG = ROOT / "el2n_wait.log"
LOG = ROOT / "fill30_wait.log"
DONE_MARK = "EL2N round finished"

os.environ["DATADIET_N_TRAIN"] = os.environ.get("DATADIET_N_TRAIN", "24000")
os.environ["DATADIET_N_POOL"] = os.environ.get("DATADIET_N_POOL", "24000")
os.environ["PYTHONIOENCODING"] = "utf-8"

# R needs a temp dir it can create files in. When this script is started from a
# harness sandbox, TEMP points at a per-job directory that is deleted before the
# long chain reaches Rscript, and R dies with "cannot create 'R_TempDir'".
# Pinning TMP/TEMP/TMPDIR to a directory inside the repo keeps the chain alive.
TMPDIR = ROOT / "tmp"
TMPDIR.mkdir(parents=True, exist_ok=True)
for _k in ("TMP", "TEMP", "TMPDIR"):
    os.environ[_k] = str(TMPDIR)

POLL_S = 60
MAX_WAIT_MIN = 180


def log(msg: str) -> None:
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run(cmd: list[str], tag: str) -> int:
    log(f"--- {tag}")
    logf = ROOT / f"fill30_{tag.replace(' ', '_')}.log"
    t0 = time.time()
    with open(logf, "a", encoding="utf-8") as fh:
        fh.write(f"\n===== {tag} @ {datetime.now():%Y-%m-%d %H:%M:%S} =====\n")
        fh.flush()
        p = subprocess.run(cmd, cwd=ROOT, stdout=fh, stderr=subprocess.STDOUT)
    log(f"--- {tag} exit={p.returncode} after {(time.time() - t0) / 60:.1f} min")
    return p.returncode


def wait_for_el2n() -> bool:
    deadline = time.time() + MAX_WAIT_MIN * 60
    while time.time() < deadline:
        if EL2N_LOG.exists():
            txt = EL2N_LOG.read_text(encoding="utf-8", errors="replace")
            if DONE_MARK in txt:
                return True
        time.sleep(POLL_S)
    return False


def main() -> int:
    log("waiting for the EL2N round to finish")
    if not wait_for_el2n():
        log(f"EL2N round did not finish within {MAX_WAIT_MIN} min - aborting "
            "(nothing was started, so the machine is left as it was)")
        return 1
    log("EL2N round finished - starting the 6-seed fill at 30%")

    if run([str(PY), "tools/night_queue.py", "--plan", "fill30"], "fill30 queue") != 0:
        log("queue reported a failure - still running the analysis on whatever landed")

    run([str(PY), "tools/report_numbers.py"], "report_numbers")
    run([str(RSCRIPT), "R/run_all.R"], "R analysis")
    run([str(PY), "tools/make_table1.py"], "make_table1")
    run([str(PY), "tools/make_audit.py"], "make_audit")
    run([str(PY), "tools/audit_final.py"], "audit_final")

    log("6-seed fill finished")
    return 0


if __name__ == "__main__":
    sys.exit(main())
