"""chain.py —— 把剩下的实验按顺序跑完，中间留冷却时间（用户 2026-10-26 的要求）。

一台上网本连续满载会热，所以每个 stage 之间停 `--cool` 分钟（默认 15），
并且每个 stage 都记状态到 `logs/chain_state.json`，重启后不会重复跑已完成的 stage。

stage 列表（顺序即执行顺序）：
  e3        —— 3-epoch 那轮（由 tools/after_full_e3.py 在跑，这里只等它的报告落盘）
  gen_medqa —— MedQA 生成式评测（4 个 arm，约 20 min）
  pool48k   —— 48k 池的重跑（归档 24k → 造池 → 采激活 → 选择 → 训练 5 个 run，约 8 h）
  gen48k    —— 48k 池上的生成式评测（4 个 arm，约 20 min）

用法：
    .venv\\Scripts\\python.exe tools\\chain.py            # 跑没完成的 stage
    .venv\\Scripts\\python.exe tools\\chain.py --list     # 只看还有哪些
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
PY = ROOT / ".venv" / "Scripts" / "python.exe"
STATE = ROOT / "logs" / "chain_state.json"
LOG = ROOT / "logs" / "chain.log"

TMP = ROOT / "tmp"
TMP.mkdir(exist_ok=True)
for k in ("TMP", "TEMP", "TMPDIR"):
    os.environ[k] = str(TMP)
os.environ["PYTHONIOENCODING"] = "utf-8"


def log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_state() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {}


def save_state(st: dict) -> None:
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")


def run(cmd, name: str, env_extra: dict | None = None) -> int:
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    log(f"start {name}")
    t0 = time.time()
    with open(ROOT / "logs" / f"chain_{name}.log", "w", encoding="utf-8") as lf:
        p = subprocess.run(cmd, cwd=ROOT, stdout=lf, stderr=subprocess.STDOUT, env=env)
    log(f"{name} exit={p.returncode} in {(time.time() - t0) / 60:.1f} min")
    return p.returncode


def move(src: Path, dst: Path) -> None:
    if src.exists() and not dst.exists():
        shutil.move(str(src), str(dst))
        log(f"archived {src.name} -> {dst.name}")


# ------------------------------------------------------------------ stages
def stage_e3(st) -> int:
    """3-epoch 轮：等 after_full_e3.py 的报告出现即可（它自己会跑队列）。"""
    target = ROOT / "results" / "e3_summary.csv"
    deadline = time.time() + 16 * 3600
    while not target.exists():
        if time.time() > deadline:
            raise TimeoutError("e3 超过 16 小时还没出报告")
        time.sleep(120)
    return 0


def stage_gen_medqa(st) -> int:
    (ROOT / "results" / "gen").mkdir(parents=True, exist_ok=True)
    arms = ["none", "full_s1", "nait_r30_s1", "random_r30_s1"]
    for a in arms:
        rc = run([str(PY), "gen_eval.py", "--task", "medqa", "--limit", "500",
                  "--bs", "8", "--seed", "7", "--adapter", a], f"gen_medqa_{a}",
                 {"DATADIET_RUN_TAG": ""})
        if rc != 0:
            return rc
    return run([str(PY), "tools/gen_report.py", "--task", "medqa"], "gen_medqa_report")


def stage_pool48k(st) -> int:
    """归档 24k 轮 → 造 48k 池 → 采激活 → 选择 → 训练。"""
    move(ROOT / "results", ROOT / "results_round2_24k")
    move(ROOT / "data" / "subsets", ROOT / "subsets_round2_24k")
    move(ROOT / "data" / "processed", ROOT / "processed_round2_24k")
    move(ROOT / "cache" / "acts", ROOT / "acts_round2_24k")
    move(ROOT / "models" / "adapters", ROOT / "adapters_round2_24k")
    for d in ("results", "results/preds", "results/runs", "data/subsets",
              "data/processed", "cache/acts", "models/adapters"):
        (ROOT / d).mkdir(parents=True, exist_ok=True)

    env48 = {"DATADIET_N_TRAIN": "48000", "DATADIET_N_POOL": "48000",
             "DATADIET_RUN_TAG": "", "DATADIET_EPOCHS": "1"}
    steps = [
        ([str(PY), "prepare_data.py", "--pool", "domain"], "48k_prepare", env48),
        ([str(PY), "collect_acts.py", "--split", "train"], "48k_acts_train", env48),
        ([str(PY), "collect_acts.py", "--split", "probe"], "48k_acts_probe", env48),
        ([str(PY), "select_subset.py"], "48k_select", env48),
        ([str(PY), "tools/make_randlen.py"], "48k_randlen", env48),
        # full 1 个种子 + nait/random 各 2 个种子（每 run: full 1 epoch 48k ≈ 3.4 h，30% ≈ 1.0 h）
        ([str(PY), "run_one.py", "--method", "full", "--ratio", "1.0", "--seed", "1", "--epochs", "1"],
         "48k_full_s1", env48),
    ]
    for m in ("nait", "random"):
        for s in (1, 2):
            steps.append(([str(PY), "run_one.py", "--method", m, "--ratio", "0.30",
                           "--seed", str(s), "--epochs", "1"], f"48k_{m}_s{s}", env48))
    for cmd, name, env in steps:
        rc = run(cmd, name, env)
        if rc != 0:
            return rc

    # 归档式重跑最容易漏的一步：派生文件（eq_table / sample_stats / compute_table）
    # 必须在新一轮里重新生成，否则收尾的 audit 会读不到文件而静默失败。
    report = [
        ([str(PY), "tools/report_numbers.py"], "48k_report_numbers"),
        ([str(PY), "tools/export_sample_stats.py"], "48k_sample_stats"),
        (["C:/Program Files/R/R-4.6.1/bin/x64/Rscript.exe", "R/run_all.R"], "48k_r"),
        ([str(PY), "tools/make_table1.py"], "48k_table1"),
    ]
    for cmd, name in report:
        rc = run(cmd, name, env48)
        if rc != 0:
            return rc
    return 0


def stage_gen48k(st) -> int:
    (ROOT / "results" / "gen").mkdir(parents=True, exist_ok=True)
    arms = ["none", "full_s1", "nait_r30_s1", "random_r30_s1"]
    for a in arms:
        rc = run([str(PY), "gen_eval.py", "--task", "medmcqa", "--limit", "500",
                  "--bs", "8", "--seed", "7", "--adapter", a], f"gen48k_{a}",
                 {"DATADIET_RUN_TAG": ""})
        if rc != 0:
            return rc
    return run([str(PY), "tools/gen_report.py", "--task", "medmcqa"], "gen48k_report")


STAGES = [
    ("e3", "3-epoch 轮（9 个 run 已裁成 5 个，正在跑）", stage_e3),
    ("gen_medqa", "MedQA 生成式评测（4 arm，约 20 min）", stage_gen_medqa),
    ("pool48k", "48k 池重跑（造池+采激活+5 个 run，约 8 h）", stage_pool48k),
    ("gen48k", "48k 池生成式评测（4 arm，约 20 min）", stage_gen48k),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--cool", type=int, default=15, help="stage 之间冷却分钟数")
    ap.add_argument("--only", default="", help="只跑某个 stage")
    a = ap.parse_args()

    st = load_state()
    todo = [(n, d, f) for n, d, f in STAGES
            if st.get(n, {}).get("status") != "done" and (not a.only or n == a.only)]
    if a.list:
        for n, d, _ in STAGES:
            s = st.get(n, {}).get("status", "pending")
            print(f"  {n:<12}{s:<10}{d}")
        return

    log(f"chain up: {len(todo)} stage(s) todo, cooldown {a.cool} min")
    for i, (name, desc, fn) in enumerate(todo):
        log(f"=== stage {name}: {desc} ===")
        st.setdefault(name, {})["started"] = time.strftime("%Y-%m-%d %H:%M:%S")
        save_state(st)
        try:
            rc = fn(st)
        except Exception as e:
            rc = -1
            log(f"stage {name} raised: {e}")
        st[name]["rc"] = rc
        st[name]["status"] = "done" if rc == 0 else "failed"
        st[name]["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
        save_state(st)
        log(f"stage {name} -> {st[name]['status']}")
        if i < len(todo) - 1 and a.cool > 0:
            log(f"cooling down {a.cool} min (让机器歇一歇)")
            time.sleep(a.cool * 60)

    log("chain finished")
    run([str(PY), "tools/make_audit.py"], "chain_audit")
    run([str(PY), "tools/audit_final.py"], "chain_audit_final")


if __name__ == "__main__":
    main()
