"""run_remaining.py —— 把"为了绝对严谨"该补的 5 类实验一次排队跑完。

顺序（先跑最有价值的，再跑长尾）：
  1. 全量基线 seed 2、3            —— 所有 Δ 的分母，最重要（每个约 2.5 h）
  2. 50% / 70% 的 seed 2           —— 把阶梯上半段从 1 种子补到 2 种子（约 4 h）
  3. nait_ns seed 3–6              —— 分层配额消融从 2 种子补到 6（约 2.7 h）
  4. rand_len / nait_dedup @30% s1 —— 48k 轮补齐这两条对照臂（约 1.4 h）
  5. EL2N：打分 + @30% s1          —— 24k 轮的结果不能冒充 48k（约 1.5 h）
  6. 生成式复查（seed 8）          —— 换一套抽样，验证"样式效应"不是抽样偶然（20 min）
  7. 收尾：R 分析 + 报表 + 两套审计

每一步都幂等：`--reuse` 会跳过已存在的 adapter，只补评测；已完成的步骤重跑代价很低。
日志：logs/remaining_<step>.log，总账写 logs/remaining.log。

用法：
    .venv\\Scripts\\python.exe tools\\run_remaining.py            # 全跑
    .venv\\Scripts\\python.exe tools\\run_remaining.py --list     # 只看清单
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = ROOT / ".venv" / "Scripts" / "python.exe"
RSCRIPT = Path(r"C:\Program Files\R\R-4.6.1\bin\x64\Rscript.exe")
LOG = ROOT / "logs" / "remaining.log"

TMP = ROOT / "tmp"
TMP.mkdir(exist_ok=True)
for k in ("TMP", "TEMP", "TMPDIR"):
    os.environ[k] = str(TMP)
os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ.setdefault("DATADIET_N_TRAIN", "48000")
os.environ.setdefault("DATADIET_N_POOL", "48000")
os.environ.setdefault("DATADIET_EPOCHS", "1")
os.environ.setdefault("DATADIET_RATIOS", "0.01,0.05,0.10,0.20,0.30,0.50,0.70")


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run(cmd: list[str], name: str) -> int:
    log(f"start {name}")
    t0 = time.time()
    with open(ROOT / "logs" / f"remaining_{name}.log", "w", encoding="utf-8") as lf:
        p = subprocess.run([str(c) for c in cmd], cwd=ROOT, stdout=lf, stderr=subprocess.STDOUT)
    dt = (time.time() - t0) / 60
    log(f"{name}: exit={p.returncode} ({dt:.1f} min)")
    return p.returncode


def one(method: str, ratio: str, seed: int, tag: str) -> tuple[list[str], str]:
    return ([PY, "run_one.py", "--method", method, "--ratio", ratio,
             "--seed", str(seed), "--epochs", "1", "--reuse"], tag)


def steps() -> list[tuple[list[str], str]]:
    s: list[tuple[list[str], str]] = []

    # 1. 全量基线：给它自己 3 个种子，Δ 才有分母的波动
    for sd in (2, 3):
        s.append(one("full", "1.0", sd, f"full_s{sd}"))

    # 2. 阶梯上半段补第二个种子
    for m in ("nait", "random"):
        for r in ("0.50", "0.70"):
            s.append(one(m, r, 2, f"{m}_r{r}_s2"))

    # 3. 分层配额消融补到 6 个种子
    for sd in (3, 4, 5, 6):
        s.append(one("nait_ns", "0.30", sd, f"nait_ns_s{sd}"))

    # 4. 48k 轮补齐 rand_len / nait_dedup
    s.append(one("rand_len", "0.30", 1, "rand_len_r30_s1"))
    s.append(one("nait_dedup", "0.30", 1, "nait_dedup_r30_s1"))

    # 5. EL2N：先打分（会写 subsets_el2n.json），再训练一次
    s.append(([PY, "tools/el2n_scores.py", "--bs", "16"],
              "el2n_scoring"))
    s.append(one("el2n", "0.30", 1, "el2n_r30_s1"))

    # 6. 生成式复查：换一套抽样（seed 8）
    #    gen_eval 按 tag 命名并且"文件存在就跳过"，所以必须换目录，否则 seed 8 会被当成已完成
    gen8_dir = str(ROOT / "results" / "gen_seed8")
    for arm in ("none", "full_s1", "nait_r30_s1", "random_r30_s1"):
        s.append(([PY, "gen_eval.py", "--task", "medmcqa", "--limit", "500",
                   "--bs", "8", "--seed", "8", "--adapter", arm, "--out-dir", gen8_dir],
                  f"gen8_{arm}"))
    s.append(([PY, "tools/gen_report.py", "--task", "medmcqa", "--gen-dir", gen8_dir],
              "gen8_report"))

    # 7. 收尾
    s.append(([PY, "tools/export_sample_stats.py"], "export_stats"))
    s.append(([RSCRIPT, "R/run_all.R"], "R_analysis"))
    s.append(([PY, "tools/report_numbers.py"], "report_numbers"))
    s.append(([PY, "tools/make_table1.py"], "make_table1"))
    s.append(([PY, "tools/make_audit.py"], "make_audit"))
    s.append(([PY, "tools/audit_final.py"], "audit_final"))
    s.append(([PY, "tools/audit_runs.py"], "audit_runs"))
    return s


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--only", default="", help="只跑名字里含这个子串的步骤")
    a = ap.parse_args()

    plan = steps()
    if a.only:
        plan = [p for p in plan if a.only in p[1]]
    if a.list:
        for cmd, name in plan:
            print(f"  {name:<22}{' '.join(str(c) for c in cmd[-6:])}")
        print(f"\n共 {len(plan)} 步")
        return 0

    log(f"=== 剩余实验开跑，共 {len(plan)} 步 ===")
    fails = []
    for i, (cmd, name) in enumerate(plan, 1):
        log(f"--- [{i}/{len(plan)}] {name} ---")
        rc = run(cmd, name)
        if rc != 0:
            fails.append(name)
            log(f"!! {name} 失败（会继续跑后面的，最后统一报）")
    log(f"=== 结束：{len(plan) - len(fails)}/{len(plan)} 成功；失败={fails} ===")
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
