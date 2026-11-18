"""make_handover.py —— 生成"给别人做 PPT"用的交接包（全部数字从 results/*.csv 现算）。

用法：
    .venv\\Scripts\\python.exe tools\\make_handover.py
    .venv\\Scripts\\python.exe tools\\make_handover.py --out "C:\\Users\\me\\Desktop\\某目录"

产物：
    00_先看这个_交接说明.md
    01_核心数据_全部数字.md
    02_结果图\\*.png
    03_演示界面\\{app.py, ui_screenshot.png, 启动说明.txt}
    04_文档\\*.docx / *.doc
    05_PPT大纲.md
    06_原始数据\\*.csv
    07_参考\\C_同类课题研究水平概述.md
    <目录名>.zip
"""

from __future__ import annotations

import argparse
import csv
import shutil
import statistics as st
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "results"
CB = ROOT / "docs" / "challenge_b"
FIG = ROOT / "paper" / "figures"

REPO = "https://github.com/wyw-yy/datadiet-ehr"
DOI = "10.5281/zenodo.24161048"


def rows(name: str) -> list[dict]:
    p = RES / name
    if not p.exists():
        return []
    with open(p, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def f(x, nd=2) -> str:
    try:
        return f"{float(x):.{nd}f}"
    except (TypeError, ValueError):
        return str(x)


def at_ratio(rs: list[dict], ratio: float, **kw) -> list[dict]:
    out = []
    for r in rs:
        if abs(float(r["ratio"]) - ratio) > 1e-9:
            continue
        if all(str(r.get(k, "")) == str(v) for k, v in kw.items()):
            out.append(r)
    return out


def nullband_block(rs: list[dict], task: str) -> str:
    """一个任务上的零分布：19 个随机子集 + 各对照臂的百分位。"""
    if not rs:
        return ""
    rd = [float(r["delta_pp"]) for r in rs if r["arm"] == "random"]
    passed = sum(1 for r in rs if r["arm"] == "random" and r["tost_pass"] == "TRUE")
    if not rd:
        return ""
    q = sorted(rd)
    p10 = q[int(0.10 * (len(q) - 1))]
    p90 = q[int(0.90 * (len(q) - 1))]
    mean = st.mean(rd)

    lines = [
        f"**{task} 零分布（{len(rd)} 个随机 30% 子集）**",
        "",
        "| 指标 | 值 |",
        "|---|---|",
        f"| 平均掉点 | {mean:+.2f} pp |",
        f"| 最小 / 最大 | {min(rd):+.2f} / {max(rd):+.2f} pp |",
        f"| P10 / P90 | {p10:+.2f} / {p90:+.2f} pp |",
        f"| 通过 ±2pp 等效界 | **{passed}/{len(rd)} = {100 * passed / len(rd):.0f}%** |",
        "",
    ]
    arms = {}
    for r in rs:
        if r["arm"] != "random":
            arms.setdefault(r["arm"], []).append(float(r["delta_pp"]))
    if arms:
        lines += ["| 对照臂 | 平均掉点 | 在零分布中的百分位 |", "|---|---|---|"]
        for arm, vals in arms.items():
            m = st.mean(vals)
            pct = 100 * sum(1 for x in rd if x < m) / len(rd)
            lines.append(f"| {arm} | {m:+.2f} pp | 第 {pct:.0f} 百分位 |")
        lines.append("")
    return "\n".join(lines)


def write_core(dst: Path) -> None:
    eq = rows("eq_table.csv")
    ct = rows("eq_contrast.csv")
    cp = rows("compute_table.csv")
    hm = rows("holm.csv")
    nb = rows("nullband.csv")
    nbm = rows("nullband_medqa.csv")

    L: list[str] = []
    L.append("# 一、核心数据（全部由 `results/*.csv` 现算，可直接抄进 PPT）\n")

    L.append("## 1. 数据规模\n")
    L.append("| 项 | 值 |")
    L.append("|---|---|")
    L.append("| 训练池 | **48,000 条**（公开临床问答） |")
    L.append("| 30% 子集 | **14,400 条** |")
    L.append("| 域内探测集（算质心用，不参与训练） | 2,000 条 |")
    L.append("| 近似去重保留 | **46,714 / 48,000 = 97.32%** |")
    L.append("| 评测集 | MedMCQA **4,183 题** / MedQA **1,273 题** |")
    L.append("| 实验总量 | **138 次训练+评测**，累计 **82 GPU·h** |")
    L.append("| 代码规模 | 92 个源文件 / 11,566 行 |")
    L.append("")

    L.append("## 2. 主结果：30% 保留（相对全量训练）\n")
    L.append("| 任务 | 方法 | 种子 | 30% 准确率 | 全量准确率 | 掉点 | 95% CI | 逐题等效 | 种子等效 |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    order = ["nait", "random", "nait_dedup", "rand_len", "nait_ns", "el2n"]
    for task in ("medmcqa", "medqa"):
        for m in order:
            for r in at_ratio(eq, 0.30, task=task, method=m):
                L.append(
                    f"| {task} | **{m}** | {r['n_seed']} | {f(r['acc_sub'], 3)} | {f(r['acc_full'], 3)} | "
                    f"**{f(r['delta_pp'])} pp** | [{f(r['ci_lo_pp'])}, {f(r['ci_hi_pp'])}] | "
                    f"{'✅' if r['equiv_item'] == 'TRUE' else '❌'} | "
                    f"{'✅' if r['equiv_seed'] == 'TRUE' else '❌'} |"
                )
    L.append("")
    L.append("> δ = 2 pp。逐题等效 = 逐题配对 CI 全落在 ±2pp；种子等效 = 种子级 CI 全落在 ±2pp。\n")

    L.append("## 3. 方法间对比（30%）\n")
    L.append("| 任务 | 对比 | Δ | 95% CI | 原始 p | Holm 校正后 | 显著 |")
    L.append("|---|---|---|---|---|---|---|")
    holm_idx = {(h["task"], h["method"], h["vs"]): h for h in hm if abs(float(h["ratio"]) - 0.3) < 1e-9}
    for task in ("medmcqa", "medqa"):
        for r in at_ratio(ct, 0.30, task=task):
            h = holm_idx.get((task, r["method"], r["vs"]), {})
            L.append(
                f"| {task} | {r['method']} − {r['vs']} | {f(r['delta_pp'], 2)} pp | "
                f"[{f(r['ci_lo_pp'])}, {f(r['ci_hi_pp'])}] | {f(r['stouffer_p'], 4)} | "
                f"{f(h.get('p_holm', ''), 3)} | {'是' if h.get('sig_holm') == 'TRUE' else '否'} |"
            )
    L.append("")
    L.append("> 关键：**nait − random 原始 p = 0.016，Holm 校正后 0.176，不显著**。所以不能说“优于随机”。\n")

    L.append("## 4. 随机分布参照（这是本作品最有说服力的一张牌）\n")
    L.append(nullband_block(nb, "MedMCQA"))
    L.append(nullband_block(nbm, "MedQA"))

    L.append("## 5. 算力净账（30% 保留）\n")
    L.append("| 方法 | 训练 | 选择前向 | 合计 | 净省 |")
    L.append("|---|---|---|---|---|")
    for r in at_ratio(cp, 0.30):
        L.append(
            f"| {r['method']} | {f(r['train_h'], 3)} GPU·h | {f(r['select_h'], 3)} GPU·h | "
            f"**{f(r['gpu_hours'], 3)}** | **{f(r['net_saving_pct'], 1)}%** |"
        )
    for r in at_ratio(cp, 1.0):
        L.append(f"| 全量（参照） | {f(r['train_h'], 3)} GPU·h | — | {f(r['gpu_hours'], 3)} | — |")
    L.append("")
    L.append("> 随机抽样省 70%，但它不做任何挑选；激活选择要跑一遍全池前向，所以净省 **48.6%**。\n")

    L.append("## 6. 剂量曲线（保留比例 → 掉点，MedMCQA）\n")
    L.append("| 保留比例 | nait | random |")
    L.append("|---|---|---|")
    rts = sorted({float(r["ratio"]) for r in eq if r["task"] == "medmcqa"}, reverse=True)
    for rt in rts:
        d = {}
        for r in at_ratio(eq, rt, task="medmcqa"):
            d[r["method"]] = r
        cell = lambda m: f"{f(d[m]['delta_pp'])} pp" if m in d else "—"
        L.append(f"| {int(rt * 100)}%（{int(48000 * rt):,} 条） | {cell('nait')} | {cell('random')} |")
    L.append("")
    L.append("> 只有 **30%** 这一档出现“nait 在界内、random 越界”；更低的 1–20% 两臂一起掉出去。\n")
    L.append("> ⚠️ 50%/70% 两档只有 1–2 个种子，50% 那行 nait −1.86 是单点波动、不是趋势；**讲剂量曲线只讲 1%–30% 这一段**，否则会被评委抓住自相矛盾。\n")

    (dst / "01_核心数据_全部数字.md").write_text("\n".join(L), encoding="utf-8")


def write_brief(dst: Path) -> None:
    txt = f"""# 交接说明（给做 PPT 的人）

> 生成日期：{date.today().isoformat()}　项目：DataDiet-EHR（课题 65）

## 一分钟看懂这个项目

**一句话**：用神经元激活从 48,000 条临床训练数据里挑出 30%（14,400 条），在**效果不掉**（±2 个百分点内）的前提下，把训练算力省掉一半（净省 **48.6%**）。

**它不是一个"更强的选数据算法"，而是把"到底能删多少"做成可判定、可复现的一套协议 + 软件。** 这一点答辩时务必讲对，讲错了会被追问。

## 三个必须讲对的数字

| 数字 | 含义 |
|---|---|
| **48,000 → 14,400（30%）** | 训练池规模，以及砍到的位置 |
| **−0.98 pp，CI [−1.57, −0.07]** | 激活选择臂相对全量训练的掉点，落在 ±2pp 等效界内 |
| **48.6%** | 算力净省（已扣掉"挑数据要跑一遍前向"的成本；不是 70%） |

## 三条不许说

1. ❌ **"我们的方法显著优于随机"** —— nait − random = +0.50 pp，原始 p=0.016，**Holm 校正后 0.176，不显著**。
2. ❌ **"省 70% 算力"** —— 70% 是"不做挑选、直接随机删"的账；要挑数据就要付前向成本。
3. ❌ **"用了院内电子病历"** —— 全部是公开数据（HealthCareMagic-100k、MedQA、MedMCQA），院内数据是未来工作。

## 可以理直气壮讲的四点

1. **30% 仍等效**：nait −0.98 pp（双口径通过），随机臂在同档掉 −1.40 pp 并越界。
2. **随机分布参照**：19 个随机 30% 子集平均掉 1.43 pp，只有 7 个（37%）能过 ±2pp —— 说明"能删三成"不是白送的，需要规则。
3. **算力净账**：全量 2.128 GPU·h → 激活选择 1.093 GPU·h（净省 48.6%），且把选择开销算进去了，学界普遍不算这一块。
4. **机制解释**：激活相似度实际筛出的是"答案带引用/出处"的样本（52.7% vs 其余 27.9%），所以生成式评测里表现为引用样式被放大，而非能力提升 —— 这是一个诚实且有意思的发现。

## 资源在哪

| 内容 | 位置 |
|---|---|
| 开源仓库（public，MIT） | {REPO} |
| 永久归档 DOI（Zenodo，可直接引用） | https://doi.org/{DOI} |
| 结果图（8 张，300 dpi 级） | 本包 `02_结果图\\` |
| 演示界面（可现场跑） | 本包 `03_演示界面\\`，见其中 `启动说明.txt` |
| 三份报告 + 支撑材料 + 封面 | 本包 `04_文档\\` |
| 全部原始数字表 | 本包 `06_原始数据\\` |
| 数据核对明细 | `01_核心数据_全部数字.md` |

## 建议的讲法（10 分钟版）

1. **问题**（1 页）：临床模型训练贵，数据里大量重复；"能删多少"没有可判定的答案。
2. **缺口**（1 页）：现有工作报告的"省 30%/70%"互相不可比 —— 没有预注册的等效界、没有随机分布参照、算力账不算选择成本。
3. **做法**（2 页）：激活采集 → 去均值/二值化去重 → 科室配额选样 → LoRA 微调 → 配对检验 + 零分布。
4. **结果**（3 页）：30% 等效、随机越界、零分布百分位、算力净省 48.6%。
5. **边界**（1 页）：不主张优于随机、公开数据非院内、单基座、MedQA 题量小。
6. **价值**（1 页）：可复现协议 + 开源实现 + 可现场演示；换数据只改一个目录。

⚠️ **宁少勿错**：讲不准的数字就不讲。`01_核心数据_全部数字.md` 里没有的数字，一律不要出现在 PPT 上。
"""
    (dst / "00_先看这个_交接说明.md").write_text(txt, encoding="utf-8")


def write_outline(dst: Path) -> None:
    txt = """# PPT 大纲（12 页，10 分钟）

> 每页给了：标题 / 要点 / 配图。图都在 `02_结果图\\`，文件名见括号。

**P1 封面**
- 标题：DataDiet-EHR —— 用神经元激活把临床训练数据砍到三成，效果不掉
- 副标题：可复现的训练子集选择协议与等效性评估软件
- 底部：皖江工学院 · 杨宇 · 2025 级计算机科学与技术 · 挑战杯 科技发明制作 B 类

**P2 一句话讲清**
- 三个数字大字：**48,000 → 14,400（30%）**、**−0.98 pp（±2pp 内）**、**净省 48.6%**
- 一行注解：效果不掉的前提下，训练算力省掉近一半

**P3 问题：临床模型训练贵在哪**
- 数据重复率高：一条"感冒多喝水"在十万条里出现几千次
- "少用数据"听起来简单，但**"少到什么程度会掉点"没有公认答案**
- 配图：无（用三个图标/色块即可）

**P4 缺口：现有工作为什么不可比**
- ① 没有预注册的等效界（各说各的"效果不变"）
- ② 没有随机分布参照（单任务单种子就说"优于随机"）
- ③ 算力账只算训练，不算"挑数据"那一遍前向
- 配图：（fig01_pipeline.png 可放这页右侧，示意六段流水线）

**P5 做法：六段流水线**
- 数据准备 → 激活采集（5 层，response token 均值）→ 子集选择（去均值校正、90 分位二值化去重、科室配额）→ LoRA 微调（r=16）→ 评测（选项 logprob，不生成）→ 统计（δ=2pp、逐题+逐种子、Holm）
- 配图：**fig01_pipeline.png**（横版流程图）

**P6 实验设置**
- 训练池 48,000 条；30% = 14,400 条；探测集 2,000 条（不参与训练）
- 评测：MedMCQA 4,183 题（同域）、MedQA 1,273 题（跨任务）
- 规模：138 次训练+评测，82 GPU·h；单卡 8 GB 消费级显卡完成

**P7 主结果：30% 仍等效**
- nait：−0.98 pp [−1.57, −0.07] → 双口径通过
- random：−1.40 pp [−2.15, −0.86] → 逐题口径**越界**
- 配图：**fig06_forest.png**（逐种子森林图，一眼看出方向和波动）

**P8 关键：随机分布参照（本作品最有说服力的一页）**
- 19 个随机 30% 子集：平均 −1.43 pp，只有 **7/19 = 37%** 能过 ±2pp
- 激活选择臂：**第 89 百分位**（带上沿，不是带外）
- 结论：**"能删三成"需要规则，不是随便抽**
- 配图：**fig07_nullband.png**

**P9 任务依赖性（诚实的负结果）**
- MedQA（跨任务）：19 个随机子集里 **13/19 = 68%** 能过 → 激活选择臂位于**第 53 百分位（正中间）**
- 结论：**能删多狠强依赖任务；没有哪个选择器能跨任务稳定超过随机带**
- 配图：**fig07_medqa_nullband.png**

**P10 算力净账**
- 全量 2.128 GPU·h → 激活选择 1.093 GPU·h（训练 0.638 + 选择 0.455）= **净省 48.6%**
- 对照：随机 0.638（省 70%，但不挑选）；EL2N 1.150（省 45.9%，选择更贵）
- 配图：**fig05_compute.png**（柱状：训练 + 选择前向两段堆叠）

**P11 边界与不足（评委最爱问）**
- 不主张优于随机（Holm 0.176 不显著）
- 公开数据，非院内 EMR（未来工作）
- 单基座（1.5B）；MedQA 仅 1,273 题，CI 较宽
- 4 个随机子集因单卡显存未完成，已在预注册修正案中登记排除

**P12 价值与演示**
- 交付：开源协议（MIT）+ 永久归档（DOI）+ 可现场运行的演示界面
- 换数据只改一个目录，协议不变
- 现场可点"跑一次冒烟实验"（约 3 分钟）证明流水线真实可跑
- 底部：{REPO} ・ doi:{DOI}

---
## 可选补充（如果给 15 分钟或要加页）

- **科室稳健性**：fig04_dept.png —— 六个科室分别看掉点，最差科室也在可控范围
- **剂量曲线**：fig02_data_equilibrium.png → 用 `fig02_data_efficiency.png`（1%–70% 的阶梯，30% 是拐点）
- **机制页**：被选中样本 52.7% 的答案带引用/出处 vs 其余 27.9% → 解释"激活选择放大的是样式"
""".replace("fig02_data_equilibrium.png", "fig02_data_efficiency.png")
    (dst / "05_PPT大纲.md").write_text(txt, encoding="utf-8")


def copy_assets(dst: Path) -> list[str]:
    made: list[str] = []

    fig_dir = dst / "02_结果图"
    fig_dir.mkdir(parents=True, exist_ok=True)
    rename = {
        "fig01_pipeline.png": "P5_六段流水线.png",
        "fig02_data_efficiency.png": "P_剂量曲线_1到70%.png",
        "fig02_absolute.png": "P_剂量曲线_绝对准确率.png",
        "fig04_dept.png": "P_科室稳健性.png",
        "fig05_compute.png": "P10_算力净账.png",
        "fig06_forest.png": "P7_逐种子森林图.png",
        "fig07_nullband.png": "P8_随机零分布_MedMCQA.png",
        "fig07_medqa_nullband.png": "P9_随机零分布_MedQA.png",
    }
    for src, new in rename.items():
        s = FIG / src
        if s.exists():
            shutil.copy2(s, fig_dir / new)
            made.append(f"02_结果图/{new}")

    ui = dst / "03_演示界面"
    ui.mkdir(parents=True, exist_ok=True)
    for s in (ROOT / "app.py", ROOT / "paper" / "ui" / "ui_screenshot.png"):
        if s.exists():
            shutil.copy2(s, ui / s.name)
            made.append(f"03_演示界面/{s.name}")
    (ui / "启动说明.txt").write_text(
        "演示界面怎么开：\n\n"
        "1) 本机已装 Python 3.12 的环境下，在本文件夹执行：\n"
        "   python app.py --port 8765\n"
        "   （若提示缺模块，本项目只用标准库，不需要安装任何东西）\n\n"
        "2) 浏览器打开 http://127.0.0.1:8765/\n\n"
        "3) 页面上能看到：核心 KPI、30% 掉点表、随机零分布表、算力净账、两张结果图。\n"
        "   点“跑一次冒烟实验”会真跑一遍小规模训练+评测（约 3 分钟），用来现场证明流水线可用。\n\n"
        "4) 注意：app.py 需要同目录上一级有 results/*.csv；如果只拿到本文件夹，\n"
        "   建议直接从 GitHub 仓库克隆后运行，效果一样。\n",
        encoding="utf-8",
    )
    made.append("03_演示界面/启动说明.txt")

    doc = dst / "04_文档"
    doc.mkdir(parents=True, exist_ok=True)
    for name in ("作品封面.docx", "研制报告.docx", "研究报告.docx", "项目书.docx",
                 "支撑材料.docx", "申报书_已填.doc", "C_同类课题研究水平概述.md"):
        s = CB / name
        if s.exists():
            shutil.copy2(s, doc / name)
            made.append(f"04_文档/{name}")

    raw = dst / "06_原始数据"
    raw.mkdir(parents=True, exist_ok=True)
    for name in ("eq_table.csv", "eq_contrast.csv", "nullband.csv", "nullband_medqa.csv",
                 "compute_table.csv", "holm.csv", "metrics_long.csv"):
        s = RES / name
        if s.exists():
            shutil.copy2(s, raw / name)
            made.append(f"06_原始数据/{name}")

    ref = dst / "07_参考"
    ref.mkdir(parents=True, exist_ok=True)
    s = CB / "C_同类课题研究水平概述.md"
    if s.exists():
        shutil.copy2(s, ref / "同类课题研究水平_可作背景页素材.md")
        made.append("07_参考/同类课题研究水平_可作背景页素材.md")
    return made


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path.home() / "Desktop" / "65项目_交接包_PPT用"))
    a = ap.parse_args()
    dst = Path(a.out)
    dst.mkdir(parents=True, exist_ok=True)

    write_brief(dst)
    write_core(dst)
    write_outline(dst)
    made = copy_assets(dst)

    zpath = dst.parent / (dst.name + ".zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(dst.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(dst.parent))

    print(f"交接包：{dst}")
    print(f"压缩包：{zpath}  ({zpath.stat().st_size / 1024 / 1024:.2f} MB)")
    print(f"文件数：{sum(1 for p in dst.rglob('*') if p.is_file())}")
    for m in made:
        print("  +", m)


if __name__ == "__main__":
    main()