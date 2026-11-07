"""photo_to_pdf.py —— 把手机拍的纸质材料（签章页/身份证）转成可上传的 PDF。

软著上传的硬要求：
  · PDF 格式，一页一张纸（多页就一个 PDF 多页）
  · A4 纵向、内容完整、四角不裁切、清晰可读
  · 不能拉伸变形（等比缩放，空白补白）

做四件事：
  1. 找到纸张外轮廓（暗像素包围盒），裁掉桌面/背景；
  2. 估算倾斜角并转正（-6°~+6° 逐 0.5° 试，取文字行最"平"的角度）；
  3. 提白底（灰底压掉，纸面提到接近纯白），文字变深；
  4. 等比缩放进 A4 300 dpi 页面，居中，存 PDF。

用打包的 Pillow 跑（项目 venv 里没有 PIL）：
  "C:\\Users\\yang'yu\\.dsh\\dsh-runtimes\\dsh-primary-runtime\\dependencies\\python\\python.exe" tools\\photo_to_pdf.py <图片...> -o out.pdf
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageOps, ImageStat

A4_300 = (2480, 3508)   # A4 @ 300 dpi


def _deskew_score(img: Image.Image) -> float:
    """越小越"正"：把图压成单列，文字行的投影会形成尖峰；歪了尖峰就糊。"""
    small = img.resize((img.width // 4, img.height // 4), Image.BILINEAR).convert("L")
    px = small.load()
    w, h = small.size
    rows = []
    for y in range(h):
        s = 0
        for x in range(0, w, 2):
            s += 255 - px[x, y]
        rows.append(s)
    # 相邻行差分的绝对值和：横平竖直时差分大（黑白突变），歪了就平滑
    return -sum(abs(rows[i + 1] - rows[i]) for i in range(len(rows) - 1))


def deskew(img: Image.Image, limit: float = 6.0, step: float = 0.5) -> Image.Image:
    best, best_img = None, img
    a = -limit
    while a <= limit + 1e-9:
        r = img.rotate(a, resample=Image.BICUBIC, expand=False, fillcolor=(255, 255, 255))
        sc = _deskew_score(r)
        if best is None or sc < best:
            best, best_img = sc, r
        a += step
    return best_img


def crop_paper(img: Image.Image, margin: int = 12) -> Image.Image:
    """用暗像素找纸张范围；纯色背景（桌面）比纸暗或亮都行，靠"内容包围盒"。"""
    g = img.convert("L")
    # 阈值取自适应：纸是亮区，文字/表格线是暗区
    hist = g.histogram()
    total = sum(hist)
    acc, thr = 0, 128
    for v, c in enumerate(hist):          # 取 5% 分位作暗阈值
        acc += c
        if acc >= total * 0.05:
            thr = v
            break
    mask = g.point(lambda p: 255 if p < thr else 0)
    bbox = mask.getbbox()
    if not bbox:
        return img
    l, t, r, b = bbox
    l, t = max(0, l - margin), max(0, t - margin)
    r, b = min(img.width, r + margin), min(img.height, b + margin)
    # 太小的 bbox 说明阈值失效，放弃裁切
    if (r - l) * (b - t) < 0.25 * img.width * img.height:
        return img
    return img.crop((l, t, r, b))


def lift_paper(img: Image.Image) -> Image.Image:
    """灰底提白：把 90 分位亮度当纸色，超过它的压成纯白，其余按比例拉黑。"""
    g = img.convert("L")
    vals = sorted(g.getdata())
    paper = vals[int(len(vals) * 0.90)] or 235
    lut = []
    for v in range(256):
        if v >= paper:
            lut.append(255)
        else:
            lut.append(max(0, int(v * 255 / max(1, paper) * 0.92)))
    out = g.point(lut)
    return ImageOps.autocontrast(out, cutoff=0)


def to_a4(img: Image.Image) -> Image.Image:
    page = Image.new("RGB", A4_300, "white")
    w, h = img.size
    scale = min((A4_300[0] * 0.94) / w, (A4_300[1] * 0.96) / h)
    nw, nh = int(w * scale), int(h * scale)
    img = img.resize((nw, nh), Image.LANCZOS)
    page.paste(img, ((A4_300[0] - nw) // 2, (A4_300[1] - nh) // 2))
    return page


def convert(paths: list[Path], out: Path) -> None:
    pages = []
    for p in paths:
        img = Image.open(p)
        img = ImageOps.exif_transpose(img).convert("RGB")
        before = img.size
        img = crop_paper(img)
        img = deskew(img)
        img = lift_paper(img).convert("RGB")
        page = to_a4(img)
        pages.append(page)
        print(f"  {p.name}: {before[0]}x{before[1]} -> 裁切 {img.size[0]}x{img.size[1]} -> A4")
    pages[0].save(out, "PDF", resolution=300.0, save_all=True, append_images=pages[1:])
    print(f"PDF: {out}  {out.stat().st_size / 1024:.0f} KB  {len(pages)} 页")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="+")
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()
    paths = [Path(x) for x in a.images]
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        sys.exit("找不到：" + ", ".join(missing))
    convert(paths, Path(a.out))


if __name__ == "__main__":
    main()