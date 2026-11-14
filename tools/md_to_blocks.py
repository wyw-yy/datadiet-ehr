"""md_to_blocks.py —— 把 Markdown 拆成"块"JSON，供 Word COM 精确排版。

为什么绕这一圈：直接用 HTML 让 Word 转换时，CSS 里的字体/字号会丢（实测 docx 里只有 2 处
楷体、0 张表格）。改成 Python 只负责解析结构，Word 负责排版，格式才可控。

用法：
    .venv\\Scripts\\python.exe tools\\md_to_blocks.py docs/challenge_b/研制报告.md docs/challenge_b/blocks.json
"""

import json
import re
import sys
from pathlib import Path


def parse(md: str, src_dir: Path | None = None) -> list[dict]:
    lines = md.splitlines()
    blocks: list[dict] = []
    i, title_seen = 0, False
    while i < len(lines):
        line = lines[i].rstrip()
        if not line or line.strip() == "---":
            i += 1
            continue
        if line.lstrip().startswith("|"):
            rows = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c or "-") for c in cells):
                    rows.append([c.replace("**", "") for c in cells])
                i += 1
            if rows:
                blocks.append({"type": "table", "rows": rows})
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            level, text = len(m.group(1)), m.group(2).strip().replace("**", "")
            if level == 1 and not title_seen:
                blocks.append({"type": "title", "text": text})
                title_seen = True
            else:
                blocks.append({"type": f"h{min(level, 3)}", "text": text})
            i += 1
            continue
        mc = re.match(r"^::\s*(.*)$", line.strip())
        if mc:
            blocks.append({"type": "p", "text": mc.group(1).replace("**", ""), "center": True})
            i += 1
            continue
        mi = re.match(r"^!\[(.*?)\]\((.+?)\)\s*$", line.strip())
        if mi:
            cap, rel = mi.group(1), mi.group(2)
            abs_path = (src_dir / rel).resolve() if src_dir else Path(rel).resolve()
            blocks.append({"type": "img", "path": str(abs_path), "caption": cap})
            i += 1
            continue
        if line.lstrip().startswith(("- ", "* ")):
            blocks.append({"type": "li", "text": line.lstrip()[2:].replace("**", "")})
            i += 1
            continue
        if line.lstrip().startswith(">"):
            text = line.lstrip().lstrip(">").strip()
            if text:
                blocks.append({"type": "p", "text": text.replace("**", "")})
            i += 1
            continue
        blocks.append({"type": "p", "text": line.strip().replace("**", "")})
        i += 1
    return blocks


if __name__ == "__main__":
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    blocks = parse(src.read_text(encoding="utf-8"), src_dir=src.parent)
    dst.write_text(json.dumps(blocks, ensure_ascii=False, indent=1), encoding="utf-8")
    kinds: dict[str, int] = {}
    for b in blocks:
        kinds[b["type"]] = kinds.get(b["type"], 0) + 1
    print(f"写出 {dst}：{kinds}")
