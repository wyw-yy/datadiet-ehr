"""make_softcopyright.py —— 生成软著登记要交的两份文件（都可以直接上传）。

中国版权保护中心的计算机软件著作权登记要两份东西：

1. **源程序**：连续的源代码，前 30 页 + 后 30 页（不足 3000 行就全部提交）。
   要求每页不少于 50 行、页眉有软件名称和版本号。
2. **文档**：用户手册或设计说明书，同样前 30 页 + 后 30 页（不足就全部）。

本脚本做的是"把仓库里的东西整理成这两份"：
  * `softcopyright/源程序.txt`  —— 按 50 行一页切好、每页顶部带页眉
  * `softcopyright/说明书.txt`  —— 由 README / PROTOCOL / API / DATA_CARD 拼成
之后交给 `tools/txt_to_pdf.ps1` 用 Word 转 PDF（Word 会重新分页并加页眉）。

用法：
    .venv\\Scripts\\python.exe tools\\make_softcopyright.py
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "softcopyright"
OUT.mkdir(exist_ok=True)

NAME = "DataDiet-EHR 临床训练子集选择与等效性评估软件"
SHORT = "DataDiet-EHR"
VERSION = "V1.0"
HEADER = f"{NAME} {VERSION}"

# 源程序：按"入口 → 数据 → 选择 → 训练 → 评测 → 调度 → 分析"的顺序排，
# 让审查员顺着读能看懂流程（乱序拼文件也能过，但可读性差）。
CODE_FILES = [
    "config.py",
    "prepare_data.py",
    "prepare_mimic.py",
    "collect_acts.py",
    "select_subset.py",
    "train.py",
    "eval.py",
    "gen_eval.py",
    "run_one.py",
    "tools/night_queue.py",
    "tools/chain.py",
    "tools/export_sample_stats.py",
    "tools/paired_stats.py",
    "R/00_setup.R",
    "R/01_equivalence.R",
    "R/02_curve.R",
    "R/03_robustness.R",
    "R/04_compute.R",
    "R/05_multiple.R",
    "R/06_forest.R",
    "R/07_pipeline.R",
    "R/run_all.R",
]

DOC_PARTS = [
    ("一、软件概述", "README.md"),
    ("二、可复现协议", "docs/PROTOCOL.md"),
    ("三、程序接口说明", "docs/API.md"),
    ("四、数据说明", "docs/DATA_CARD.md"),
    ("五、评测与统计口径", "docs/GENERATIVE_EVAL.md"),
]

LINES_PER_PAGE = 50


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def build_source() -> Path:
    lines: list[str] = []
    for rel in CODE_FILES:
        p = ROOT / rel
        if not p.exists():
            continue
        lines.append(f"// ==================== 文件：{rel} ====================")
        lines.extend(read(p).replace("\t", "    ").splitlines())
        lines.append("")
    total = len(lines)

    # 不要在这里插页眉/换页符：Word 的页眉已经带名称与版本号，
    # 手插 "\f" 会让每块多出一张空白页（第一版就是这样变成 139 页的）。
    dst = OUT / "源程序.txt"
    dst.write_text("\n".join(lines), encoding="utf-8")
    print(f"源程序：{len(CODE_FILES)} 个文件 / {total} 行 → {dst}")
    return dst


def md_to_text(md: str) -> str:
    """Markdown → 纯文本：标题去井号、表格保留、图片与链接去掉 URL。"""
    out = []
    for line in md.splitlines():
        s = line.rstrip()
        if re.match(r"^#{1,6}\s", s):
            s = re.sub(r"^#{1,6}\s*", "", s)
            out.append("")
            out.append(s)
            out.append("-" * min(40, max(8, len(s))))
            continue
        s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)
        s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)
        s = s.replace("`", "")
        out.append(s)
    return "\n".join(out)


def build_doc() -> Path:
    parts = [f"{NAME} {VERSION}", "软件说明书（设计说明与用户手册）", ""]
    for title, rel in DOC_PARTS:
        p = ROOT / rel
        if not p.exists():
            continue
        parts.append("")
        parts.append(title)
        parts.append("=" * 30)
        parts.append(md_to_text(read(p)))
    body = "\n".join(parts)
    dst = OUT / "说明书.txt"
    dst.write_text(body, encoding="utf-8")
    print(f"说明书：{len(body.splitlines())} 行 → {dst}")
    return dst


def build_form() -> Path:
    """申请表里要填的字段，先写成一张表，填的时候照抄。"""
    n_files = sum(1 for f in CODE_FILES if (ROOT / f).exists())
    n_lines = sum(len(read(ROOT / f).splitlines()) for f in CODE_FILES if (ROOT / f).exists())
    form = f"""# 软著申请表填写参考

| 字段 | 建议填写 |
|---|---|
| 软件全称 | {NAME} |
| 软件简称 | {SHORT} |
| 版本号 | {VERSION} |
| 开发完成日期 | 2026-10-27 |
| 首次发表日期 | 未发表（勾"未发表"） |
| 开发方式 | 合作开发（3 人）／若只署你自己，选"独立开发" |
| 著作权人 | 见下方"署名与权属" |
| 权利取得方式 | 原始取得 |
| 权利范围 | 全部权利 |
| 软件分类 | 应用软件 → 医疗健康／人工智能 |
| 硬件环境 | 普通 PC；NVIDIA GPU 8 GB 显存（CPU 亦可运行，仅慢） |
| 软件环境 | Windows 11；Python 3.12；R 4.6；PyTorch 2.11 (CUDA 12.8) |
| 编程语言 | Python、R |
| 源程序量 | {n_lines} 行（{n_files} 个文件） |

## 开发目的
把"少用一部分临床训练数据、效果不变"这件事变成可复现的实验流程：
给定一个医学问答训练池，自动采集神经元激活、按激活相似度挑选子集，
训练后与"全量训练"逐题配对比较，输出"这个保留比例是否等效"的统计结论。

## 主要功能
1. 数据整备：多源医学问答/病历统一成 JSONL，按病人切分防泄漏；
2. 激活采集：抽取指定层的隐藏态，只对答案 token 取均值；
3. 子集选择：去均值 → 余弦打分 → 近重复去重 → 按科室分层配额取前 k%；
4. 训练：LoRA 微调，长度分桶批处理，只对答案段计算损失；
5. 评测：选择题按选项 token 概率判定，支持生成式评测与红旗检测；
6. 统计：逐题配对 McNemar、bootstrap 置信区间、TOST、跨种子 Stouffer 合并；
7. 算力核算：把"选择用的前向"计入成本，输出净节省比例。

## 技术特点
- 等效性判定双口径（逐题 / 逐种子），避免把噪声当效应；
- 选择过程可审计：每样本激活得分、子集清单、代码清单均带哈希；
- 换数据集只改一个目录，其余流程不动（协议与数据解耦）。

## 署名与权属（务必先和导师/科研处确认）
- 你自述"全部个人承担、另有两位队友"：属**合作开发**，你排第一开发者；
- 著作权人可写个人，也可写学校。**若使用了学校设备、导师课题经费或职务时间，
  通常应作为职务作品由学校持有**，学生列为开发者——这一点以学校科研处口径为准，
  写错会在校内认定环节被退回。
"""
    dst = OUT / "申请表填写参考.md"
    dst.write_text(form, encoding="utf-8")
    print(f"申请表参考 → {dst}")
    return dst


if __name__ == "__main__":
    build_source()
    build_doc()
    build_form()
    print(json.dumps({"dir": str(OUT)}, ensure_ascii=False))
