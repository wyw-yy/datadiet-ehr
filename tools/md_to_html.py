"""md_to_html.py —— 把研制报告 Markdown 转成 Word 友好的 HTML。

为什么不用 python-docx：这台机器 pip 装包不稳（多次卡在索引请求），
而 Word COM 已经验证可用（软著那两份 PDF 就是它导的）。Word 打开 HTML 再另存 docx，
中文字体、字号、表格、页面设置都能带过去，省掉一个依赖。

格式依据通知：正文中文、4 号楷体（14pt）、A4。

用法：
    .venv\\Scripts\\python.exe tools\\md_to_html.py docs/challenge_b/研制报告.md docs/challenge_b/研制报告.html
"""

import html
import re
import sys
from pathlib import Path

CSS = """
@page { size: 21cm 29.7cm; margin: 2.54cm 3.0cm; }
body { font-family: 楷体, KaiTi, serif; font-size: 14pt; line-height: 1.6; }
h1 { font-family: 黑体, SimHei; font-size: 22pt; text-align: center; margin: 18pt 0 12pt; }
h2 { font-family: 黑体, SimHei; font-size: 14pt; margin: 14pt 0 8pt; }
h3 { font-family: 黑体, SimHei; font-size: 12pt; margin: 10pt 0 6pt; }
p  { text-indent: 2em; margin: 0 0 6pt; }
p.li { text-indent: -1.4em; padding-left: 3.4em; }
blockquote { margin: 0 0 6pt; }
table { border-collapse: collapse; width: 100%; font-family: 宋体, SimSun; font-size: 10.5pt; margin: 6pt 0 10pt; }
th { border: 1px solid #888; background: #EDF2F7; padding: 3pt 5pt; font-weight: bold; }
td { border: 1px solid #888; padding: 3pt 5pt; vertical-align: top; }
.sub { font-family: 楷体; font-size: 12pt; text-align: center; margin-bottom: 16pt; }
"""


def inline(text: str) -> str:
    text = html.escape(text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    return text


def table(rows: list[str]) -> str:
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    cells = [c for c in cells if not all(re.fullmatch(r":?-{2,}:?", x or "-") for x in c)]
    if not cells:
        return ""
    out = ["<table>"]
    for i, row in enumerate(cells):
        tag = "th" if i == 0 else "td"
        out.append("<tr>" + "".join(f"<{tag}>{inline(c)}</{tag}>" for c in row) + "</tr>")
    out.append("</table>")
    return "\n".join(out)


def convert(src: Path, dst: Path) -> None:
    lines = src.read_text(encoding="utf-8").splitlines()
    body, i, title_seen = [], 0, False
    while i < len(lines):
        line = lines[i].rstrip()
        if not line or line.strip() == "---":
            i += 1
            continue
        if line.lstrip().startswith("|"):
            block = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                block.append(lines[i])
                i += 1
            body.append(table(block))
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            level, text = len(m.group(1)), m.group(2).strip()
            if level == 1 and not title_seen:
                body.append(f"<h1>{inline(text)}</h1>")
                title_seen = True
            else:
                lv = min(level, 3)
                body.append(f"<h{lv}>{inline(text)}</h{lv}>")
            i += 1
            continue
        if line.lstrip().startswith(("- ", "* ")):
            body.append(f'<p class="li">· {inline(line.lstrip()[2:])}</p>')
            i += 1
            continue
        if line.lstrip().startswith(">"):
            text = line.lstrip().lstrip(">").strip()
            if text:
                body.append(f"<blockquote><p>{inline(text)}</p></blockquote>")
            i += 1
            continue
        body.append(f"<p>{inline(line.strip())}</p>")
        i += 1

    # 不要写 <!DOCTYPE>：Word 会把它当 XML 解析并因为"禁用 DTD"直接报错
    doc = f"""<html><head>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
<title>研制报告</title>
<style>{CSS}</style></head><body>
{chr(10).join(body)}
</body></html>"""
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(doc, encoding="utf-8")
    print(f"写出 {dst}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        raise SystemExit(2)
    convert(Path(sys.argv[1]), Path(sys.argv[2]))
