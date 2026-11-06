"""post_rigor.py —— 等补跑批次结束后自动做收尾分析，然后关机。

为什么单独写：`resume_rigor.py` 只负责跑那 25 个 run，不含 R 分析与审计；
而 2026-11-05 凌晨那批就是因为"没有脱离会话的收尾"结果空转 15.5 小时。

v2 的两处加固（2026-11-05 22:10 审查后加）：
  1. **完整性闸门**：收尾分析前先核 25 个 run 的两份 preds 是否都在。缺了就
     不分析、不关机，改成重新拉起 resume_rigor（最多 --max-relaunch 次）。
     旧版本会在 resume 被杀、数据只跑了一半时照样分析、照样关机 —— 那会把
     "半截数据算出来的数字"留成最终结果。
  2. **自愈**：用 WMI 之外的普通 Popen 拉起 resume —— 因为本进程已由 WMI
     `Win32_Process.Create` 启动，不在 DSH 的 job 对象里，子进程同样不受
     关 DSH 影响。
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
RESUME_RELAUNCH_LOG = ROOT / "logs" / "resume_relaunch.log"

# 预注册的 25 个补充 run（与 tools/resume_rigor.py 的 PLAN 保持一致）
PLAN = (
    [("random", 0.30, s) for s in range(7, 21)]
    + [("rand_len", 0.30, s) for s in range(2, 6)]
    + [("nait_dedup", 0.30, s) for s in range(2, 6)]
    + [("el2n", 0.30, s) for s in range(2, 5)]
)

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


def eid_of(method: str, ratio: float, seed: int) -> str:
    return f"{method}_r{int(round(ratio * 100)):02d}_s{seed}"


def missing_runs() -> list[str]:
    """返回还缺 preds 的 exp_id（两个 task 任一缺失都算缺）。"""
    out = []
    for m, r, s in PLAN:
        eid = eid_of(m, r, s)
        ok = all((ROOT / "results" / "preds" / f"{eid}_{t}.csv.gz").exists()
                 for t in ("medmcqa", "medqa"))
        if not ok:
            out.append(eid)
    return out


def resume_stalled(minutes: float) -> bool:
    """resume 进程还在、但日志超过 minutes 分钟没动 —— 说明它卡死了。

    2026-11-06 的事故就是这样：显卡驱动在 22:43 重置（事件 nvlddmkm 153 刷了几十次），
    训练进程卡在 CUDA 调用里不返回也不退出，resume_rigor 一直"存活"，于是
    post_rigor 的 alive 判据永远为真，谁也没发现整批在 00:13 就已经全失败了 ——
    机器又空转 18 小时。之后必须用"日志有没有往前走"判活，不能只看进程在不在。
    """
    if not RESUME_LOG.exists():
        return False
    return (time.time() - RESUME_LOG.stat().st_mtime) / 60.0 > minutes


def kill_resume_tree() -> None:
    for p in psutil.process_iter(["pid", "cmdline"]):
        try:
            cmd = " ".join(p.info["cmdline"] or [])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if "resume_rigor.py" in cmd and "post_rigor" not in cmd:
            try:
                for ch in p.children(recursive=True):
                    ch.kill()
                p.kill()
                log(f"killed stalled resume pid={p.pid}")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass


def relaunch_resume() -> None:
    cmd = f'cd /d "{ROOT}" && "{PY}" tools\\resume_rigor.py >> "{RESUME_RELAUNCH_LOG}" 2>&1'
    log(f"relaunching resume_rigor (log -> {RESUME_RELAUNCH_LOG.name})")
    subprocess.Popen(["cmd", "/c", cmd], env=ENV, cwd=str(ROOT),
                     creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)


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
    ap.add_argument("--max-relaunch", type=int, default=5)
    ap.add_argument("--stall-minutes", type=float, default=30.0,
                    help="resume 进程在、但日志这么久没动，就当作卡死并重启")
    ap.add_argument("--heartbeat-minutes", type=float, default=10.0)
    ap.add_argument("--no-shutdown", action="store_true")
    ap.add_argument("--retry", action="append", default=[],
                    help="补跑失败的 run，格式 method:ratio:seed，可重复")
    a = ap.parse_args()

    log(f"post_rigor up: interval={a.interval}s misses={a.misses} max={a.max_wait_hours}h "
        f"plan={len(PLAN)} runs")

    t0 = time.time()
    miss = 0
    relaunches = 0
    give_up = False
    last_beat = time.time()

    while True:
        # 只看日志最后一行：整个文件里搜 "resume finished" 会被上一轮的旧记录骗到
        # （2026-11-06 18:02 就撞了：重启后第一轮读到的还是 00:13 那行"finished"）。
        done = False
        if RESUME_LOG.exists():
            tail = [ln for ln in RESUME_LOG.read_text(encoding="utf-8", errors="ignore").splitlines()
                    if ln.strip()]
            done = bool(tail) and "resume finished" in tail[-1]
        alive = running("resume_rigor.py")
        if alive and resume_stalled(a.stall_minutes):
            log(f"resume alive but log frozen > {a.stall_minutes:.0f} min -> treat as dead")
            kill_resume_tree()
            alive = False
        if done or not alive:
            miss += 1
            log(f"resume idle (log_done={done}, alive={alive}), miss {miss}/{a.misses}")
            if miss >= a.misses:
                gap = missing_runs()
                if not gap:
                    log("completeness gate: all 25 runs have both preds -> analysis")
                    break
                log(f"completeness gate: {len(gap)} run(s) missing, e.g. {gap[:4]}")
                if relaunches >= a.max_relaunch:
                    log(f"relaunch budget exhausted ({relaunches}); analysing incomplete data, "
                        f"will NOT shut down")
                    give_up = True
                    break
                relaunch_resume()
                relaunches += 1
                miss = 0
        else:
            miss = 0
        if time.time() - last_beat > a.heartbeat_minutes * 60:
            gap_now = len(missing_runs())
            log(f"heartbeat: alive={alive} missing={gap_now}/{len(PLAN)} "
                f"{(time.time() - t0) / 3600:.1f} h elapsed")
            last_beat = time.time()
        if time.time() - t0 > a.max_wait_hours * 3600:
            log("max wait exceeded, doing the analysis anyway (no shutdown)")
            give_up = True
            break
        time.sleep(a.interval)

    # 补跑仍然失败的那几个（OOM 多数是并发抢显存，单独再跑一次基本就过）
    for spec in a.retry:
        m, r, s = spec.split(":")
        eid = eid_of(m, float(r), int(s))
        if not (ROOT / "results" / "preds" / f"{eid}_medmcqa.csv.gz").exists() or \
           not (ROOT / "results" / "preds" / f"{eid}_medqa.csv.gz").exists():
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

    still_missing = missing_runs()
    log(f"post_rigor finished; failed steps: {bad if bad else 'none'}; "
        f"missing runs: {len(still_missing)}")
    if bad or give_up or still_missing or a.no_shutdown:
        log("not shutting down (failures / incomplete / --no-shutdown)")
        return
    log("shutting down in 120 s")
    subprocess.run(["shutdown", "/s", "/f", "/t", "120", "/c",
                    "DataDiet-EHR rigor batch finished"], check=False)


if __name__ == "__main__":
    main()