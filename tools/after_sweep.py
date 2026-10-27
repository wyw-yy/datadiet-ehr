"""after_sweep.py —— 等 48k 比例扫描跑完，接着跑"分层配额"消融，再自动收尾。

为什么需要它：`night_queue` 一次只能跑一个 GPU 队列；扫描（8 个 run，约 7 h）
跑完后如果不接人，机器就又空着。这个 supervisor 只做"接下一棒"：

  1. 每 60 s 看有没有 `train.py` 在跑；
  2. 没有 → `night_queue --plan abl48k`（nait_ns @30%，2 个种子）；
  3. 队列结束 → R 重算 → report_numbers → make_table1 → make_audit → audit_final。

消融的问题：把"按科室配额"这一步去掉、直接取全局最高分，结果会不会一样？
若一样，说明分层这环没贡献；若变差，说明"每个科室都得留人"是真实机制。
"""

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
PY = ROOT / ".venv" / "Scripts" / "python.exe"
LOG = ROOT / "logs" / "after_sweep.log"

TMP = ROOT / "tmp"
TMP.mkdir(exist_ok=True)
for k in ("TMP", "TEMP", "TMPDIR"):
    os.environ[k] = str(TMP)
os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["DATADIET_N_TRAIN"] = "48000"
os.environ["DATADIET_N_POOL"] = "48000"
os.environ["DATADIET_RUN_TAG"] = ""
os.environ["DATADIET_EPOCHS"] = "1"


def log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def busy() -> bool:
    ps = (
        "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
        "Where-Object { $_.CommandLine -like '*train.py*' -or $_.CommandLine -like '*night_queue*' } | "
        "Select-Object -First 1 -ExpandProperty ProcessId"
    )
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True, timeout=60)
        return bool(out.stdout.strip())
    except Exception as e:            # 查不清就当还在跑，宁可不启动
        log(f"查进程失败（当作还在跑）：{e}")
        return True


def run(cmd, name):
    log(f"start {name}")
    t0 = time.time()
    with open(ROOT / "logs" / f"as_{name}.log", "w", encoding="utf-8") as lf:
        p = subprocess.run(cmd, cwd=ROOT, stdout=lf, stderr=subprocess.STDOUT)
    log(f"{name} exit={p.returncode} in {(time.time() - t0) / 60:.1f} min")
    return p.returncode


def main() -> None:
    log("supervisor up: 等 48k 扫描队列跑完")
    while busy():
        time.sleep(60)
    log("队列空了，启动消融臂 nait_ns")

    run([str(PY), "tools/night_queue.py", "--plan", "abl48k"], "queue_abl")

    steps = [
        ([str(PY), "tools/export_sample_stats.py"], "stats"),
        (["C:/Program Files/R/R-4.6.1/bin/x64/Rscript.exe", "R/run_all.R"], "r"),
        ([str(PY), "tools/report_numbers.py"], "numbers"),
        ([str(PY), "tools/make_table1.py"], "tables"),
        ([str(PY), "tools/make_audit.py"], "audit"),
        ([str(PY), "tools/audit_final.py"], "audit_final"),
    ]
    for cmd, name in steps:
        run(cmd, name)
    log("全部收尾完成")


if __name__ == "__main__":
    main()
