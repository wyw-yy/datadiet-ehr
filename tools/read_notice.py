"""把通知/规范的纯文本按句子断行打印出来（Word 导出的 txt 整篇是一行）。"""
import re
import sys
from pathlib import Path

BASE = Path(r"C:\Users\yang'yu\Desktop\codetest\_notice_txt")


def show(path: Path, start: int = 0, end: int | None = None) -> None:
    t = path.read_text(encoding="utf-8")
    t = t.split("===== TABLES =====")[0]
    t = re.sub(r"[\r\n]+", "", t)
    t = t.replace("。", "。\n").replace("；", "；\n").replace("）", "）\n")
    t = re.sub(r"\n{2,}", "\n", t)
    print(f"===== {path.name} (总 {len(t)} 字) =====")
    print(t[start:end] if end else t[start:])


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "notice"
    a = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    b = int(sys.argv[3]) if len(sys.argv) > 3 else None
    if name == "notice":
        f = BASE / "关于组织开展皖江工学院第五届“挑战杯”大学生课外学术科技作品竞赛的通知.txt"
    elif name == "spec":
        f = BASE / "附件3：皖江工学院第五届“挑战杯”大学生课外学术科技作品竞赛作品提交规范要求.txt"
    elif name == "form":
        f = BASE / "附件2：皖江工学院第五届“挑战杯”大学生课外学术科技作品竞赛作品申报书.txt"
    else:
        raise SystemExit("unknown doc")
    show(f, a, b)
