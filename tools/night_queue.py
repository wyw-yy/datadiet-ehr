"""Run a queue of experiments back to back, skipping whatever is already done.

Why a python driver instead of a .bat: the queue is data (a list of
(method, ratio, seed) triples), it can skip finished runs, and it keeps going
after a single failure instead of dying at the first error at 3am.

Usage:
    python tools/night_queue.py                 # the default overnight plan
    python tools/night_queue.py --plan quick    # only the three 30% arms
    python tools/night_queue.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config as C  # noqa: E402

PY = ROOT / ".venv" / "Scripts" / "python.exe"
LOG = ROOT / "night.log"
RUN_LOGS = ROOT / "logs"


def done_ids() -> set[str]:
    p = C.RESULTS / "metrics_long.csv"
    if not p.exists():
        return set()
    out = set()
    with open(p, encoding="utf-8") as f:
        next(f, None)
        for line in f:
            out.add(line.split(",", 1)[0])
    return out


def plan(name: str) -> list[tuple[str, float, int]]:
    """(method, ratio, seed) triples, in priority order."""
    if name == "quick":
        return [("full", 1.0, 1), ("nait", 0.3, 1), ("random", 0.3, 1)]

    if name == "seeds6":
        # 目标：把 30% 这一档从 3 个种子补到 6 个，并加长度匹配对照臂。
        # 顺序上先补 full（最长、也是所有差值的分母），后面全是 3600 条的短 run。
        q: list[tuple[str, float, int]] = []
        for s in (2, 3, 4, 5, 6):
            q.append(("full", 1.0, s))
        for s in (2, 3, 4, 5, 6):
            q.append(("nait", 0.30, s))
        for s in (2, 3, 4, 5, 6):
            q.append(("random", 0.30, s))
        for s in (1, 2, 3, 4, 5, 6):
            q.append(("rand_len", 0.30, s))
        # nait_dedup 在 MedQA 上是单种子的 −1.18pp，补两个种子看是不是噪声
        for s in (2, 3):
            q.append(("nait_dedup", 0.30, s))
        return q

    if name == "scale":
        # "放大池子"那一轮：24k 池、1 epoch、3 种子、4 个臂（12 run）。
        # 假设：池子越大冗余越重，随机基线越吃亏，选择算法才可能拉开差距。
        # 顺序：先跑最长的 full（它是所有差值的分母），再跑三个 30% 臂。
        q: list[tuple[str, float, int]] = []
        for s in (1, 2, 3):
            q.append(("full", 1.0, s))
        for s in (1, 2, 3):
            q += [("nait", 0.30, s), ("random", 0.30, s), ("rand_len", 0.30, s)]
        return q

    if name == "fill30":
        # 按 PREREG 第 5 节：正式跑要 6 个种子。这一轮只补 30% 这一档的 s4–6，
        # 让主终点（子集 vs 全量）从 3 个种子变 6 个。顺序先 full（它是所有差值的分母），
        # 再跑三个 30% 臂（每条 7,200 条，约 20 min）。
        # el2n 保持 3 个种子——它是次要基线，表里会显示 n_seed=3。
        q: list[tuple[str, float, int]] = []
        for s in (4, 5, 6):
            q.append(("full", 1.0, s))
        for s in (4, 5, 6):
            q += [("nait", 0.30, s), ("random", 0.30, s), ("rand_len", 0.30, s)]
        return q

    if name == "epoch3":
        # 3 epoch 那一轮：1 epoch 时连"全量"都可能欠拟合，天花板压着差距。
        # 只跑 3 个臂 x 3 个种子（full / nait@30 / random@30），配 DATADIET_RUN_TAG=e3 隔离 id。
        # 时间账（实测 3.9 samp/s）：full 9000 step ≈ 5.1 h，30% 3000 step ≈ 1.7 h。
        # 3 个 full 种子要 15 h，一夜装不下，所以 full 只跑 1 个种子，
        # 把省下的时间给对比臂（nait/random 各 2 个种子）——判据看的是 nait vs random。
        q: list[tuple[str, float, int]] = [("full", 1.0, 1)]
        for s in (1, 2):
            q += [("nait", 0.30, s), ("random", 0.30, s)]
        return q

    if name == "k48":
        # 48k 池上把对比臂补到 6 个种子：s1/s2 已有，接着 s3..s6。
        # 判据看 nait vs random 的 Stouffer p 与符号一致性，两个种子说不清。
        q: list[tuple[str, float, int]] = []
        for s in (3, 4, 5, 6):
            q += [("nait", 0.30, s), ("random", 0.30, s)]
        return q

    if name == "sweep48k":
        # 48k 池上的剂量-反应扫描（1 个种子）：回答"随机在哪一档掉出等效界"。
        # 30% 与 full 已有 6 个种子，这里只补 10/20/50/70 四个点，两个臂各一条。
        # 时间账（48k 实测 ~5.5 samp/s）：4,800 条约 15 min、24,000 条约 67 min、33,600 条约 95 min。
        q: list[tuple[str, float, int]] = []
        for r in (0.10, 0.20, 0.50, 0.70):
            q += [("nait", r, 1), ("random", r, 1)]
        return q

    if name == "abl48k":
        # 消融：分层配额是不是必要的一环（48k、30%、2 个种子）。
        # no_strat 用全局前 k%，不按科室配额；若它与 nait 打平，说明"分层"这一步没贡献。
        return [("nait_ns", 0.30, s) for s in (1, 2)]

    if name == "el2n":
        # 经典基线：EL2N 打分后保留最难的 30%（Paul et al., 2021）。
        # 只跑 30% 这一档、三个种子——它回答的是"激活选择比经典基线强吗"。
        return [("el2n", 0.30, s) for s in (1, 2, 3)]

    q: list[tuple[str, float, int]] = []
    # 1. the baseline, then the head-to-head at the headline ratio
    q += [("full", 1.0, 1), ("nait", 0.30, 1), ("random", 0.30, 1)]
    # 2. the dose-response curve (where does random break?)
    for r in (0.10, 0.20, 0.50, 0.70):
        q += [("nait", r, 1), ("random", r, 1)]
    # 3. replication seeds for the baseline and the headline point
    for s in (2, 3):
        q += [("full", 1.0, s), ("nait", 0.30, s), ("random", 0.30, s)]
    # 4. the dedup arm, if time remains
    for r in (0.10, 0.30):
        q += [("nait_dedup", r, 1)]
    return q


THREAD_CAP = {          # 训练/评测都不许吃满整机，留出桌面与 I/O 的余量
    "OMP_NUM_THREADS": "4",
    "MKL_NUM_THREADS": "4",
    "OPENBLAS_NUM_THREADS": "4",
    "NUMEXPR_NUM_THREADS": "4",
}


HEAVY_PAT = ("train.py", "night_queue", "select_subset")


def other_heavy_running(own_pid: int | None = None) -> bool:
    r"""有没有别的重活在跑（训练 / 队列 / 选子集）？

    用 psutil 而不是 powershell：Windows 的 .venv/Scripts/python.exe 是个
    转向器，会用"同一条命令行 + 新 pid"再起一个基座 python。所以要沿父进程链
    把"我自己和我的祖先"整体排除，否则队列一启动就把自己当成既有重活。
    """
    me = own_pid if own_pid is not None else os.getpid()
    try:
        import psutil
    except Exception:
        return False
    proc = {}
    for pr in psutil.process_iter(["pid", "ppid", "cmdline"]):
        try:
            proc[pr.info["pid"]] = (pr.info["ppid"], " ".join(pr.info["cmdline"] or []))
        except Exception:
            continue
    mine, cur, seen = set(), me, set()
    while cur and cur not in seen:
        mine.add(cur)
        seen.add(cur)
        cur = proc.get(cur, (0, ""))[0]
    for pid, (_ppid, cmd) in proc.items():
        if pid in mine:
            continue
        if any(pat in cmd for pat in HEAVY_PAT):
            return True
    return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", default="full",
                    choices=["full", "quick", "seeds6", "scale", "el2n", "fill30",
                             "sweep48k", "abl48k",
                             "epoch3", "k48"])
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if not a.dry_run and other_heavy_running(os.getpid()):
        print("[night] 已有训练/队列/选子集进程在跑，拒绝叠加启动（先等它结束）")
        print(f"[night] debug: 我的 pid={os.getpid()}")
        dbg = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
             "Select-Object ProcessId, CommandLine | Format-List | Out-String"],
            capture_output=True, text=True, timeout=60)
        print("[night] debug: 当前 python 进程：")
        print((dbg.stdout or "")[:800])
        raise SystemExit(2)

    have = done_ids()
    items = [t for t in plan(a.plan) if C.exp_id(*t) not in have]
    print(f"[night] {len(items)} runs to do ({len(plan(a.plan)) - len(items)} already done)")

    if a.dry_run:
        for m, r, s in items:
            print("   ", C.exp_id(m, r, s))
        return

    t0 = time.time()
    with open(LOG, "a", encoding="utf-8") as lf:
        lf.write(f"\n===== night queue start {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
    failures = []
    for i, (m, r, s) in enumerate(items, 1):
        eid = C.exp_id(m, r, s)
        cmd = [str(PY), str(ROOT / "run_one.py"), "--method", m,
               "--ratio", str(r), "--seed", str(s),
               "--epochs", os.environ.get("DATADIET_EPOCHS", "1")]
        head = f"[night {i}/{len(items)}] {eid}  ({time.strftime('%H:%M:%S')})"
        print(head, flush=True)
        with open(LOG, "a", encoding="utf-8") as lf:
            lf.write(head + "\n")
        t = time.time()
        # 每个 run 独立日志。不能把父进程的 LOG 句柄传给子进程：外层 PowerShell 也用
        # `*>` 重定向同一个文件，两个写者叠加会让子进程的输出整段丢掉（上一轮就是这样）。
        RUN_LOGS.mkdir(exist_ok=True)
        run_log = RUN_LOGS / f"{eid}.log"
        try:
            env = dict(os.environ)
            for k, v in THREAD_CAP.items():
                env.setdefault(k, v)
            with open(run_log, "w", encoding="utf-8") as lf:
                p = subprocess.run(cmd, cwd=ROOT, stdout=lf, stderr=subprocess.STDOUT, env=env)
            if p.returncode != 0:
                tail = run_log.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-4:]
                raise RuntimeError(f"run_one exit {p.returncode}: " + " | ".join(tail))
        except Exception as e:                                    # keep going
            failures.append((eid, str(e)))
            msg = f"  FAILED {eid}: {e}"
            print(msg, flush=True)
            with open(LOG, "a", encoding="utf-8") as lf:
                lf.write(msg + "\n")
            continue
        print(f"  ok in {(time.time() - t) / 60:.0f} min", flush=True)
        acc = [ln for ln in run_log.read_text(encoding="utf-8", errors="replace").splitlines()
               if "ACCURACY=" in ln]
        with open(LOG, "a", encoding="utf-8") as lf:
            lf.write(f"  ok in {(time.time() - t) / 60:.1f} min; " + " ".join(acc) + "\n")

    total = (time.time() - t0) / 3600
    summary = (f"[night] finished {len(items) - len(failures)}/{len(items)} runs "
               f"in {total:.1f} h; failures={failures}")
    print(summary)
    with open(LOG, "a", encoding="utf-8") as lf:
        lf.write(summary + "\n")


if __name__ == "__main__":
    main()
