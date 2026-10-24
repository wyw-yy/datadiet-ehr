"""run_scale.py —— 一条命令跑"放大池子"那一轮（A 计划）

做什么：
  1. 把上一轮（12k 池）的产物整体归档，避免 exp_id 撞号；
  2. 用更大的 N_TRAIN 重建训练池（默认 24,000）；
  3. 重新采激活、选子集、生成长度匹配对照；
  4. 跑 12 个 run（full ×3、nait/random/rand_len @30% ×3）；
  5. 收尾：重算 headline → R 出图 → 论文表 → 审计。

为什么这么设计：
  - 池子越大冗余越重，随机基线越吃亏 —— 这是"激活选择优于随机"唯一可能显形的设定；
  - 1 epoch 而不是 3 epoch：3 epoch 会让 full 从 33 min 涨到 100 min，一晚上装不下；
  - 归档而不是加前缀：R 与所有审计脚本都默认读 `results/`，归档后零改动。

用法：
    python tools/run_scale.py --dry-run      # 只打印，不动任何文件
    python tools/run_scale.py               # 真跑（约 7 小时）
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / ".venv" / "Scripts" / "python.exe"
RSCRIPT = Path(r"C:\Program Files\R\R-4.6.1\bin\x64\Rscript.exe")

# 归档去向（上一轮 12k 池）
ARCHIVE = [
    ("results", "results_round1_12k"),
    ("data/subsets", "data/subsets_round1_12k"),
    ("data/processed", "data/processed_round1_12k"),
    ("cache/acts", "cache/acts_round1_12k"),
    ("models/adapters", "models/adapters_round1_12k"),
]

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def show(cmd: list[str]) -> str:
    return " ".join(str(c) for c in cmd)


def run(cmd: list[str], env: dict[str, str], dry: bool, title: str) -> None:
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)
    print("  $ " + show(cmd))
    if dry:
        return
    r = subprocess.run([str(c) for c in cmd], cwd=ROOT, env=env)
    if r.returncode != 0:
        print(f"\n[X] 这一步失败（exit={r.returncode}），停在这里。")
        sys.exit(r.returncode)


def archive(dry: bool) -> None:
    print("\n" + "=" * 70)
    print("  [0/6] 归档上一轮（12k 池）的产物")
    print("=" * 70)
    for src, dst in ARCHIVE:
        s, d = ROOT / src, ROOT / dst
        if not s.exists():
            print(f"  跳过 {src}（不存在）")
            continue
        if d.exists():
            print(f"  [X] {dst} 已存在，先手动处理，避免覆盖数据")
            sys.exit(2)
        print(f"  {src:22s} -> {dst}")
        if not dry:
            shutil.move(str(s), str(d))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", type=int, default=24000, help="新的 full 池大小（默认 24000）")
    ap.add_argument("--seeds", default="1,2,3")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-archive", action="store_true", help="不归档（危险：会和上一轮撞号）")
    a = ap.parse_args()

    env = dict(os.environ)
    env["DATADIET_N_TRAIN"] = str(a.pool)
    env["DATADIET_N_POOL"] = str(a.pool)
    env["PYTHONIOENCODING"] = "utf-8"

    est_full = a.pool * 33 / 12000           # 12k 池实测 33 min/epoch
    est_arm = est_full * 0.3
    runs = 3 + 3 * 3
    hours = (3 * est_full + 9 * est_arm) / 60
    print(f"池子 {a.pool}，1 epoch；预计 full 约 {est_full:.0f} min/run，"
          f"30% 约 {est_arm:.0f} min/run，{runs} 个 run 合计约 {hours:.1f} h")

    if not a.no_archive:
        archive(a.dry_run)

    run([PY, "prepare_data.py", "--pool", "domain", "--seed", "42"], env, a.dry_run,
        "[1/6] 重建训练池（N_TRAIN=%d）" % a.pool)
    run([PY, "collect_acts.py", "--split", "train"], env, a.dry_run, "[2/6] 采训练池激活")
    run([PY, "collect_acts.py", "--split", "probe"], env, a.dry_run, "[3/6] 采 probe 激活")
    run([PY, "select_subset.py"], env, a.dry_run, "[4/6] 打分 + 分层选子集")
    run([PY, "tools/make_randlen.py"], env, a.dry_run, "[5/6] 生成长度匹配对照臂")
    run([PY, "tools/night_queue.py", "--plan", "scale"], env, a.dry_run,
        "[6/6] 队列：12 个 run（full×3 + 3 臂 @30% ×3）")
    if a.dry_run:
        print("  （注：dry-run 时 results/ 还没归档，队列会显示 '0 runs to do (12 already done)'；"
              "真跑时归档后 results/ 是空的，就会显示 12 个待跑。）")

    print("\n" + "=" * 70)
    print("  收尾（队列跑完后执行）")
    print("=" * 70)
    for cmd, title in (
        ([PY, "tools/report_numbers.py"], "重算 headline"),
        ([RSCRIPT, "R/run_all.R"], "R 出图与表"),
        ([PY, "tools/make_table1.py"], "论文表"),
        ([PY, "tools/make_audit.py"], "刷新审计清单"),
        ([PY, "tools/audit_final.py"], "六段交叉核对"),
    ):
        print(f"  $ {show(cmd)}   # {title}")
    print("\n或者直接双击 finish_round.bat。")


if __name__ == "__main__":
    main()
