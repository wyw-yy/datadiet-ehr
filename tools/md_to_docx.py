"""md_to_docx.py —— 把研制报告 Markdown 转成符合竞赛格式的 docx。

格式依据挑战杯通知：正文中文、4 号楷体、A4。这里：
  · 一级标题 三号黑体居中（16pt）
  · 二级标题 四号黑体（14pt）
  · 三级标题 小四黑体（12pt）
  · 正文 四号楷体（14pt），首行缩进 2 字符，1.5 倍行距
  · 表格 五号宋体（10.5pt），带表头底纹
  · 页脚居中页码

用法：
    .venv\\Scripts\\python.exe tools\\md_to_docx.py docs/challenge_b/研制报告.md docs/challenge_b/研制报告.docx
"""

import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

KAI = "楷体"
HEI = "黑体"
SONG = "宋体"


def set_font(run, name: str, size: float, bold: bool = False) -> None:
    run.font.name = name
    run.font.size = Pt(size)
    run.bold = bold
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)


def add_body(doc: Document, text: str) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.first_line_indent = Pt(28)  # 2 个四号字
    p.paragraph_format.line_spacing = 1.5
    p.paragraph_format.space_after = Pt(6)
    # 处理 **粗体**
    for i, chunk in enumerate(re.split(r"(\*\*[^*]+\*\*)", text)):
        if not chunk:
            continue
        if chunk.startswith("**") and chunk.endswith("**"):
            set_font(p.add_run(chunk[2:-2]), HEI, 14, bold=True)
        else:
            set_font(p.add_run(chunk), KAI, 14)


def add_heading(doc: Document, text: str, level: int) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(12 if level == 2 else 6)
    p.paragraph_format.space_after = Pt(8)
    if level == 1:
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_font(p.add_run(text), HEI, 16, bold=True)
    elif level == 2:
        set_font(p.add_run(text), HEI, 14, bold=True)
    else:
        set_font(p.add_run(text), HEI, 12, bold=True)


def shade(cell, hex_color: str = "EDF2F7") -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tcPr.append(shd)


def add_table(doc: Document, rows: list[str]) -> None:
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    cells = [c for c in cells if not all(re.fullmatch(r":?-{2,}:?", x or "-") for x in c)]
    if not cells:
        return
    n = len(cells[0])
    t = doc.add_table(rows=len(cells), cols=n)
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, row in enumerate(cells):
        for j in range(n):
            cell = t.cell(i, j)
            cell.text = ""
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(2)
            txt = row[j] if j < len(row) else ""
            txt = txt.replace("**", "")
            set_font(p.add_run(txt), SONG, 10.5, bold=(i == 0))
            if i == 0:
                shade(cell)
    doc.add_paragraph()


def add_page_number(doc: Document) -> None:
    footer = doc.sections[0].footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = footer.add_run()
    for instr in ("begin", "PAGE", "end"):
        if instr == "PAGE":
            fld = OxmlElement("w:instrText")
            fld.set(qn("xml:space"), "preserve")
            fld.text = " PAGE "
            run._r.append(fld)
        else:
            f = OxmlElement("w:fldChar")
            f.set(qn("w:fldCharType"), instr)
            run._r.append(f)


def convert(md_path: Path, out_path: Path) -> None:
    lines = md_path.read_text(encoding="utf-8").splitlines()
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    for attr in ("top_margin", "bottom_margin"):
        setattr(sec, attr, Cm(2.54))
    for attr in ("left_margin", "right_margin"):
        setattr(sec, attr, Cm(3.0))

    add_page_number(doc)

    i = 0
    title_done = False
    while i < len(lines):
        line = lines[i].rstrip()
        if not line or line.strip() in ("---",):
            i += 1
            continue

        if line.startswith("|"):
            block = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                block.append(lines[i])
                i += 1
            add_table(doc, block)
            continue

        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            level = len(m.group(1))
            text = m.group(2).strip()
            if level == 1 and not title_done:
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                p.paragraph_format.space_before = Pt(24)
                set_font(p.add_run(text), HEI, 22, bold=True)
                title_done = True
            else:
                add_heading(doc, text, level if level <= 3 else 3)
            i += 1
            continue

        if line.lstrip().startswith(("- ", "* ")):
            text = line.lstrip()[2:]
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Pt(28)
            p.paragraph_format.line_spacing = 1.5
            for chunk in re.split(r"(\*\*[^*]+\*\*)", "· " + text):
                if not chunk:
                    continue
                if chunk.startswith("**") and chunk.endswith("**"):
                    set_font(p.add_run(chunk[2:-2]), HEI, 14, bold=True)
                else:
                    set_font(p.add_run(chunk), KAI, 14)
            i += 1
            continue

        if line.lstrip().startswith(">"):
            text = line.lstrip().lstrip(">").strip()
            if text:
                add_body(doc, text)
            i += 1
            continue

        add_body(doc, line.strip())
        i += 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))
    print(f"写出 {out_path}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        raise SystemExit(2)
    convert(Path(sys.argv[1]), Path(sys.argv[2]))
