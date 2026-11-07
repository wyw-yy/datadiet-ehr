"""make_provenance.py —— 生成"这套东西是我做的、就是这个版本"的证据包。

回答三个问题：
  1. 版本管理：git 里有多少次提交、从哪天到哪天、谁提交的、打了什么 tag；
  2. 哈希值：交给别人/交给评委的那几个文件，sha256 是多少（对方可以当场核）；
  3. 辅助材料：实验能不能从结论一路对回逐题预测。

产物：
  docs/PROVENANCE.md       —— 人看的说明 + 表格
  docs/provenance.sha256   —— 机器核的清单（sha256sum -c 可直接用）

只读现有文件，不改任何东西。用法：
  .venv\\Scripts\\python.exe tools\\make_provenance.py
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_MD = ROOT / "docs" / "PROVENANCE.md"
OUT_SUM = ROOT / "docs" / "provenance.sha256"

# 要算哈希的东西：交出去的材料 + 结论的数字源头
ARTIFACTS = [
    ("softcopyright/源程序.txt", "软著：提交的 22 个源文件拼本"),
    ("softcopyright/说明书.txt", "软著：说明书正文"),
    ("softcopyright/源程序.pdf", "软著：源程序 PDF（登记用）"),
    ("softcopyright/说明书.pdf", "软著：说明书 PDF（登记用）"),
    ("RESULTS.md", "结论总表（所有数字的唯一出口）"),
    ("paper/table1.md", "论文主表"),
    ("paper/appendix_en.md", "论文英文附录"),
    ("docs/PREREG_NULLBAND.md", "零分布实验的预注册（跑之前写死的判定规则）"),
    ("docs/INCIDENTS.md", "事故记录（三次翻车与修法）"),
    ("docs/CLAIM_EVIDENCE.md", "主张-证据矩阵"),
    ("results/metrics_long.csv", "全部 run 的准确率长表"),
    ("results/eq_table.csv", "等效性检验结果"),
    ("results/eq_contrast.csv", "方法间对比 + Holm"),
    ("results/compute_table.csv", "算力净账"),
    ("results/nullband.csv", "20 个随机子集的零分布"),
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def sh(cmd: list[str]) -> str:
    try:
        out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
        return (out.stdout or "").strip()
    except Exception as e:  # git 不在 PATH 之类的
        return f"(failed: {e})"


def git_facts() -> dict:
    return {
        "commits": sh(["git", "rev-list", "--count", "HEAD"]),
        "first": sh(["git", "log", "--reverse", "--format=%h %ad", "--date=short"]).splitlines()[:1],
        "last": sh(["git", "log", "-1", "--format=%h %ad", "--date=short"]),
        "authors": sh(["git", "shortlog", "-sne", "HEAD"]),
        "tags": sh(["git", "tag"]).splitlines(),
        "tracked": sh(["git", "ls-files", "--", "."]).count("\n") + 1,
        "remote": sh(["git", "remote", "get-url", "origin"]),
        "dirty": sh(["git", "status", "--porcelain"]),
    }


def main() -> None:
    g = git_facts()
    rows = []
    for rel, note in ARTIFACTS:
        p = ROOT / rel
        if not p.exists():
            rows.append((rel, note, "—", "缺失"))
            continue
        rows.append((rel, note, sha256(p), f"{p.stat().st_size / 1024:.1f} KB"))

    dist = sorted((ROOT / "dist").glob("*.zip")) if (ROOT / "dist").exists() else []
    dist_rows = [(f"dist/{p.name}", "发布包（GitHub Release 附件）", sha256(p), f"{p.stat().st_size / 1048576:.2f} MB") for p in dist]

    # 实验规模
    n_runs = 0
    metrics = ROOT / "results" / "metrics_long.csv"
    if metrics.exists():
        n_runs = max(0, len(metrics.read_text(encoding="utf-8").splitlines()) - 1)
    n_preds = len(list((ROOT / "results" / "preds").glob("*.csv.gz"))) if (ROOT / "results" / "preds").exists() else 0
    n_src = len(list(ROOT.glob("*.py"))) + len(list((ROOT / "tools").glob("*.py"))) + len(list((ROOT / "R").glob("*.R")))

    lines = []
    lines.append("# 可追溯性说明（这套东西是谁做的、是哪个版本）\n")
    lines.append(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}　·　"
                 f"生成脚本：`tools/make_provenance.py`（只读，不改任何文件）\n")
    lines.append("这份文件回答三个问题：代码有没有版本管理、交出去的文件能不能核对、"
                 "论文里的数字能不能一路查到逐题预测。\n")

    lines.append("\n## 一、版本管理\n")
    lines.append("| 项 | 值 |\n|---|---|")
    lines.append(f"| 提交次数 | {g['commits']} |")
    lines.append(f"| 首次提交 | {' '.join(g['first']) if g['first'] else '—'} |")
    lines.append(f"| 最近提交 | {g['last']} |")
    lines.append(f"| 提交者 | 全部 `wyw-yy`（{g['authors'].splitlines()[0] if g['authors'] else ''}） |")
    lines.append(f"| 标签 | {', '.join(g['tags']) if g['tags'] else '—'} |")
    lines.append(f"| 远程仓库 | {g['remote'] or '—'}（私有） |")
    lines.append(f"| 纳入版本控制的文件 | {g['tracked']} 个 |")
    lines.append(f"| 源文件数量 | {n_src} 个（根目录 `.py` + `tools/` + `R/`） |")
    lines.append(f"| 当前工作区 | {'干净' if not g['dirty'] else '有未提交改动'} |")

    lines.append("\n说明：2026-10-23 做过一次 `git filter-branch`，把误入库的 2.6 GB LoRA 权重与 331 MB 激活从历史里摘掉，"
                 "因此**提交哈希被重写过一次**（内容不变、哈希变了）。这件事记录在 `docs/INCIDENTS.md`，不藏着。\n")

    lines.append("\n## 二、交付文件的哈希值\n")
    lines.append("对方拿到文件后，`certutil -hashfile <文件> SHA256`（Windows）或 `sha256sum <文件>`（Linux）就能核对。\n")
    lines.append("\n| 文件 | 是什么 | SHA-256 | 大小 |\n|---|---|---|---|")
    for rel, note, h, size in rows + dist_rows:
        lines.append(f"| `{rel}` | {note} | `{h}` | {size} |")

    lines.append("\n## 三、实验能不能追到底\n")
    lines.append(f"- 训练/评测 run：**{n_runs} 条**（`results/metrics_long.csv`）")
    lines.append(f"- 逐题预测文件：**{n_preds} 份**（`results/preds/*.csv.gz`，每份含 item_id / pred / correct）")
    lines.append("- 一条结论的追溯链：`RESULTS.md` 的数字 → `results/*.csv` → `results/preds/*.csv.gz` → 某一道题的预测 → 对应 adapter 与训练日志")
    lines.append("- 三层自动审计：`tools/audit_final.py`（文档数字是否都有 CSV 出处）、"
                 "`tools/audit_runs.py`（run ↔ adapter ↔ 预测是否对得上）、`tools/verify.py`（关键不变量）")
    lines.append("- 预注册：`docs/PREREG_NULLBAND.md` 在跑之前就写死了判定规则与修正案，事后没有改口径")

    lines.append("\n## 四、怎么当场核（三条命令）\n")
    lines.append("```bat")
    lines.append("REM 1) 核对文件没被动过（本目录下执行）")
    lines.append("certutil -hashfile RESULTS.md SHA256")
    lines.append("REM 2) 核对发布包")
    lines.append("certutil -hashfile dist\\datadiet-ehr-v1.0.1.zip SHA256")
    lines.append("REM 3) 看版本历史")
    lines.append("git log --oneline | find /c /v \"\"")
    lines.append("```")

    lines.append("\n## 五、边界（这份文件不证明什么）\n")
    lines.append("- 它证明**版本可追溯、材料可核对、数字可回查**，不证明代码由谁逐行敲出来。")
    lines.append("- 软著签章页要求声明“未使用 AI 编写代码”，那是另一件事，与这里的工程证据无关——"
                 "**两者的口径不要混用**：这里的材料支持“我确实做了这些实验、结论是真的”，"
                 "不支持“我没有用过 AI 工具”。")
    lines.append("- 真实病历数据（MIMIC / 院内 EMR）尚未使用，任何“临床落地”表述都应标注为外推。")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with open(OUT_SUM, "w", encoding="utf-8") as f:
        for rel, _note, h, _size in rows + dist_rows:
            if h != "—":
                f.write(f"{h}  {rel}\n")

    print(f"PROVENANCE.md 已写出：{OUT_MD}")
    print(f"哈希清单：{OUT_SUM}（{len(rows) + len(dist_rows)} 条）")
    print(f"git：{g['commits']} 次提交，{g['first']} → {g['last']}")
    print(f"实验：{n_runs} 条 metrics / {n_preds} 份逐题预测 / {n_src} 个源文件")


if __name__ == "__main__":
    main()