"""post_rigor.py —— 等补跑批次结束后自动做收尾分析，然后关机。

为什么单独写：`resume_rigor.py` 只负责跑那 25 个 run，不含 R 分析与审计；
而 2026-11-05 凌晨那批就是因为"没有脱离会话的收尾"结果空转 15.5 小时。

判据：连续 3 次（间隔 120 s）看不到 `resume_rigor.py` 进程，或 `logs/resume.log`
里出现 `resume finished`。
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import psutil  # noqa: E402

PY = ROOT / ".venv" / "Scripts" / "python.exe"
RSCRIPT = Path(r"C:\Program Files\R\R-4.6.1\bin\x64\Rscript.exe")
LOG = ROOT / "logs" / "post_rigor.log"
RESUME_LOG = ROOT / "logs" / "resume.log"

ENV = dict(os.environ)
ENV.update({
    "PYTHONIOENCODING": "utf-8",
    "DATADIET_N_TRAIN": "48000",
    "DATADIET_N_POOL": "48000",
    "DATADIET_EPOCHS": "1",
    "DATADIET_RATIOS": "0.01,0.05,0.10,0.20,0.30,0.50,0.70",
    "TMP": str(ROOT / "tmp"), "TEMP": str(ROOT / "tmp"), "TMPDIR": str(ROOT / "tmp"),
})


def log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def running(needle: str) -> bool:
    for p in psutil.process_iter(["pid", "cmdline"]):
        try:
            cmd = " ".join(p.info["cmdline"] or [])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if needle in cmd and "post_rigor" not in cmd:
            return True
    return False


def run(cmd, name: str) -> int:
    log(f"start {name}")
    t0 = time.time()
    with open(ROOT / "logs" / f"post_{name}.log", "w", encoding="utf-8") as lf:
        rc = subprocess.run(cmd, cwd=ROOT, stdout=lf, stderr=subprocess.STDOUT, env=ENV).returncode
    log(f"{name} exit={rc} in {(time.time() - t0) / 60:.1f} min")
    return rc


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=int, default=120)
    ap.add_argument("--misses", type=int, default=3)
    ap.add_argument("--max-wait-hours", type=float, default=24.0)
    ap.add_argument("--no-shutdown", action="store_true")
    ap.add_argument("--retry", action="append", default=[],
                    help="补跑失败的 run，格式 method:ratio:seed，可重复")
    a = ap.parse_args()

    log(f"post_rigor up: interval={a.interval}s misses={a.misses} max={a.max_wait_hours}h")

    t0 = time.time()
    miss = 0
    while True:
        done = RESUME_LOG.exists() and "resume finished" in RESUME_LOG.read_text(encoding="utf-8", errors="ignore")
        alive = running("resume_rigor.py")
        if done or not alive:
            miss += 1
            log(f"resume seems done (log_done={done}, alive={alive}), miss {miss}/{a.misses}")
            if miss >= a.misses:
                break
        else:
            miss = 0
        if time.time() - t0 > a.max_wait_hours * 3600:
            log("max wait exceeded, doing the analysis anyway")
            break
        time.sleep(a.interval)

    # 先补跑失败的那几个（OOM 多数是并发抢显存，单独再跑一次基本就过）
    for spec in a.retry:
        m, r, s = spec.split(":")
        eid = f"{m}_r{int(round(float(r) * 100)):02d}_s{s}"
        if (ROOT / "results" / "preds" / f"{eid}_medmcqa.csv.gz").exists() and \
           (ROOT / "results" / "preds" / f"{eid}_medqa.csv.gz").exists():
            log(f"retry {eid}: already has both preds, skip")
            continue
        rc = run([str(PY), "run_one.py", "--method", m, "--ratio", r, "--seed", s,
                  "--epochs", "1", "--reuse"], f"retry_{eid}")
        log(f"retry {eid} rc={rc}")

    steps = [
        ([str(RSCRIPT), "R/run_all.R"], "r_all"),
        ([str(RSCRIPT), "R/08_nullband.R"], "r_nullband"),
        ([str(PY), "tools/report_numbers.py"], "report_numbers"),
        ([str(PY), "tools/make_table1.py"], "make_table1"),
        ([str(PY), "tools/make_audit.py"], "make_audit"),
        ([str(PY), "tools/audit_final.py"], "audit_final"),
        ([str(PY), "tools/audit_runs.py"], "audit_runs"),
    ]
    bad = []
    for cmd, name in steps:
        if run(cmd, name) != 0:
            bad.append(name)

    log(f"post_rigor finished; failed steps: {bad if bad else 'none'}")
    if bad or a.no_shutdown:
        log("not shutting down (failures or --no-shutdown)")
        return
    log("shutting down in 120 s")
    subprocess.run(["shutdown", "/s", "/f", "/t", "120", "/c",
                    "DataDiet-EHR rigor batch finished"], check=False)


if __name__ == "__main__":
    main()