"""run_rigor.py —— 预注册（docs/PREREG_NULLBAND.md）要求的那批 run，一次跑完。

批次：
  B. 随机零分布：random @30% 补 seed 7–20（已有 1–6）→ 20 个种子
  A. 补种子    ：rand_len 2–5、nait_dedup 2–5、el2n 2–4
收尾：R 全套重算 → 零分布图 → 报表 → 三套审计。

用法：
  .venv\\Scripts\\python.exe tools\\run_rigor.py --list
  .venv\\Scripts\\python.exe tools\\run_rigor.py
断点续跑：每个 run 都用 --reuse，已存在的 adapter 不会重训，只补评测。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = ROOT / ".venv" / "Scripts" / "python.exe"
RSCRIPT = Path(r"C:\Program Files\R\R-4.6.1\bin\x64\Rscript.exe")
LOG = ROOT / "logs" / "rigor.log"

TMP = ROOT / "tmp"
TMP.mkdir(exist_ok=True)
for k in ("TMP", "TEMP", "TMPDIR"):
    os.environ[k] = str(TMP)
os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["DATADIET_N_TRAIN"] = "48000"
os.environ["DATADIET_N_POOL"] = "48000"
os.environ["DATADIET_EPOCHS"] = "1"
os.environ["DATADIET_RATIOS"] = "0.01,0.05,0.10,0.20,0.30,0.50,0.70"
# 线程限流：笔记本站 GPU 训练时不要被 CPU 抢爆（48k 去重/分词都吃 CPU）
for k in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(k, "4")

RUNS = [("random", 0.30, s) for s in range(7, 21)]          # 14
RUNS += [("rand_len", 0.30, s) for s in range(2, 6)]        # 4
RUNS += [("nait_dedup", 0.30, s) for s in range(2, 6)]      # 4
RUNS += [("el2n", 0.30, s) for s in range(2, 5)]            # 3

POST = [
    ("R_analysis", [str(RSCRIPT), "R/run_all.R"]),
    ("nullband", [str(RSCRIPT), "R/08_nullband.R"]),
    ("report_numbers", [str(PY), "tools/report_numbers.py"]),
    ("make_table1", [str(PY), "tools/make_table1.py"]),
    ("make_audit", [str(PY), "tools/make_audit.py"]),
    ("audit_final", [str(PY), "tools/audit_final.py"]),
    ("audit_runs", [str(PY), "tools/audit_runs.py"]),
]


def log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_step(name: str, cmd: list[str]) -> int:
    log(f"start {name}")
    t0 = time.time()
    with open(ROOT / "logs" / f"rigor_{name}.log", "w", encoding="utf-8") as lf:
        p = subprocess.run(cmd, cwd=ROOT, stdout=lf, stderr=subprocess.STDOUT, env=dict(os.environ))
    mins = (time.time() - t0) / 60
    log(f"{name}: exit={p.returncode} in {mins:.1f} min")
    return p.returncode


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--skip-runs", action="store_true", help="只跑收尾分析，不训练")
    a = ap.parse_args()

    if a.list:
        print(f"{len(RUNS)} 个 run：")
        for m, r, s in RUNS:
            print(f"  {m:<12} r={r:.2f} seed={s}")
        print("收尾：", ", ".join(n for n, _ in POST))
        return

    t_all = time.time()
    log(f"rigor batch up: {len(RUNS)} runs + {len(POST)} post steps; python={PY}")

    failures = []
    if not a.skip_runs:
        for i, (m, r, s) in enumerate(RUNS, 1):
            name = f"{m}_r{int(round(r * 100)):02d}_s{s}"
            cmd = [str(PY), "run_one.py", "--method", m, "--ratio", str(r),
                   "--seed", str(s), "--epochs", "1", "--reuse"]
            rc = run_step(name, cmd)
            if rc != 0:
                failures.append(name)
                log(f"!! {name} failed (rc={rc}) —— 继续下一个，最后统一报告")
            done = time.time() - t_all
            eta = done / i * (len(RUNS) - i) / 3600
            log(f"progress {i}/{len(RUNS)}; elapsed {done / 3600:.1f} h; eta {eta:.1f} h")

    for name, cmd in POST:
        rc = run_step(name, cmd)
        if rc != 0:
            failures.append(name)

    log(f"rigor finished in {(time.time() - t_all) / 3600:.2f} h; failures={failures}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()