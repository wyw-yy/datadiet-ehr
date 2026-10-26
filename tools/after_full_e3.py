"""after_full_e3.py —— 等 3-epoch 队列跑完后自动收尾（无人值守）。

为什么要单独写：`night_queue` 已被我停掉（因为它排的 9 个 run 要 25 h，装不下一夜）。
现在只有一个 `full_s1_e3` 在跑，跑完以后需要有人接着启动 4 个 30% 臂。

流程：
  1. 每 60 s 看一次：还有没有 `train.py` 进程在跑；
  2. 没有 → 跑 `night_queue --plan epoch3`（会自动跳过已完成的 id）；
  3. 队列结束 → 跑 `tools/e3_report.py` 出 3-epoch 的对比表；
  4. 把指标行、预测、图一起写进 `logs/e3_finish.log`。
"""

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PY = ROOT / ".venv" / "Scripts" / "python.exe"
LOG = ROOT / "logs" / "e3_finish.log"

# R 在脱离会话的进程里会因为没有可用临时目录而崩（cannot create 'R_TempDir'）
TMP = ROOT / "tmp"
TMP.mkdir(exist_ok=True)
for k in ("TMP", "TEMP", "TMPDIR"):
    os.environ[k] = str(TMP)

os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["DATADIET_RUN_TAG"] = "e3"
os.environ["DATADIET_EPOCHS"] = "3"
os.environ["DATADIET_N_TRAIN"] = "24000"
os.environ["DATADIET_N_POOL"] = "24000"


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def train_running():
    """有没有 train.py 在跑（用 wmic 的替代品 Get-CimInstance）。"""
    ps = (
        "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
        "Where-Object { $_.CommandLine -like '*train.py*' } | "
        "Select-Object -First 1 -ExpandProperty ProcessId"
    )
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True, timeout=60)
        return bool(out.stdout.strip())
    except Exception as e:                      # 查不清就当还在跑，宁可不启动
        log(f"查进程失败（当作还在跑）：{e}")
        return True


def run(cmd, name):
    log(f"start {name}: {' '.join(str(c) for c in cmd)}")
    with open(ROOT / "logs" / f"e3_{name}.log", "w", encoding="utf-8") as lf:
        p = subprocess.run(cmd, cwd=ROOT, stdout=lf, stderr=subprocess.STDOUT)
    log(f"{name} exit={p.returncode}")
    return p.returncode


def main():
    log("supervisor up: 等 full_s1_e3 跑完")
    while train_running():
        time.sleep(60)
    log("没有 train.py 在跑了，启动 4 个 30% 臂")

    run([str(PY), "tools/night_queue.py", "--plan", "epoch3"], "queue")
    run([str(PY), "tools/e3_report.py", "--json"], "report")
    log("全部收尾完成")


if __name__ == "__main__":
    main()
