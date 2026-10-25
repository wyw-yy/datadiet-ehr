"""Wait for the GPU to be free, then run the EL2N baseline round unattended.

Why this exists: the laptop is shared with a local llama-server (ollama) that
holds ~6.4 GiB whenever its model is loaded. Starting a 7.7 GiB training job
"when GPU memory is enough" therefore cannot be a fixed clock time - it has to
be a watched condition. This script is that condition, plus the whole chain
that used to be run by hand:

    1. wait until used VRAM <= IDLE_MIB for STREAK consecutive polls
    2. tools/el2n_scores.py           (forward pass over the pool -> scores + subsets)
    3. tools/night_queue.py --plan el2n   (3 runs: el2n @30%, seeds 1-3)
    4. finish chain: report_numbers -> Rscript R/run_all.R -> make_table1
                     -> make_audit -> audit_final

Everything is appended to el2n_wait.log so the run can be reconstructed later.
Run detached:
    Start-Process .venv\\Scripts\\python.exe -ArgumentList "tools\\wait_then_el2n.py" -WindowStyle Hidden
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
LOG = ROOT / "el2n_wait.log"

# The 24k round ran with this env var; train.jsonl holds 24,000 rows and the
# subsets must be cut from that same pool, otherwise "30%" means 12k*0.3.
os.environ["DATADIET_N_TRAIN"] = os.environ.get("DATADIET_N_TRAIN", "24000")
os.environ["DATADIET_N_POOL"] = os.environ.get("DATADIET_N_POOL", "24000")
os.environ["PYTHONIOENCODING"] = "utf-8"

POLL_S = 60          # seconds between checks
IDLE_MIB = 800       # "free enough": training needs ~7.7 GiB of 8.15 GiB
STREAK = 3           # consecutive idle polls required (avoids catching a gap between loads)


def log(msg: str) -> None:
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def gpu_used_mib() -> int | None:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=20,
        ).stdout.strip().splitlines()
        return int(out[0]) if out else None
    except Exception:
        return None


def run(cmd: list[str], tag: str) -> int:
    log(f"--- {tag}: {' '.join(Path(c).name if i == 0 else c for i, c in enumerate(cmd))}")
    t0 = time.time()
    p = subprocess.run(cmd, cwd=ROOT)
    dt = time.time() - t0
    log(f"--- {tag} exit={p.returncode} after {dt / 60:.1f} min")
    return p.returncode


def main() -> int:
    log("watcher started; waiting for the GPU to go idle")
    streak = 0
    while True:
        used = gpu_used_mib()
        if used is None:
            log("nvidia-smi failed; retrying")
            streak = 0
        elif used <= IDLE_MIB:
            streak += 1
            log(f"idle {streak}/{STREAK} (used {used} MiB)")
            if streak >= STREAK:
                log(f"GPU is free ({used} MiB) - starting the EL2N round")
                break
        else:
            if streak:
                log(f"busy again (used {used} MiB); streak reset")
            streak = 0
        time.sleep(POLL_S)

    # 1) score the pool and write data/subsets/subsets_el2n.json
    if run([str(PY), "tools/el2n_scores.py"], "el2n scoring") != 0:
        log("scoring failed - stopping (nothing downstream can run)")
        return 1

    # 2) three training runs
    if run([str(PY), "tools/night_queue.py", "--plan", "el2n"], "el2n queue") != 0:
        log("queue reported a failure - continuing to the analysis anyway, "
            "because partial results are still worth summarising")

    # 3) the usual finish chain; each step is allowed to fail without killing the rest
    run([str(PY), "tools/report_numbers.py"], "report_numbers")
    run([r"C:\Program Files\R\R-4.6.1\bin\x64\Rscript.exe", "R/run_all.R"], "R analysis")
    run([str(PY), "tools/make_table1.py"], "make_table1")
    run([str(PY), "tools/make_audit.py"], "make_audit")
    run([str(PY), "tools/audit_final.py"], "audit_final")

    log("EL2N round finished")
    return 0


if __name__ == "__main__":
    sys.exit(main())
