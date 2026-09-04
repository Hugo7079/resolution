"""
識別圖示產生器
==============

概念：**同一個方形，被切得越來越細**。

從左上到右下（自然閱讀順序）依序是 1 格 → 4 格 → 4 格 → 16 格，
最細的那一區用強調色標出來 —— 「解析度提高」這件事本身就是標誌。
這也呼應產品裡反覆出現的「格線」：拆解時要數的就是欄數。

幾何參數全部寫在 GEO，改完重跑就同步更新 SVG 與所有尺寸的 PNG。

    python3 scripts/make_icons.py
"""

from __future__ import annotations
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / "web" / "icons"

GEO = {
    "pad":        0.115,   # 四周留白（佔畫布比例）
    # 格縫用「象限邊長的固定比例」而不是「單格邊長的比例」——
    # 後者會讓 4×4 區的縫細到只有 1×1 區的四分之一，密度看起來不一致。
    "gap":        0.030,
    "quadrants": [          # (欄列數, 是否用強調色)
        (1, False),         # 左上：1 格
        (2, False),         # 右上：2×2
        (2, False),         # 左下：2×2
        (4, True),          # 右下：4×4 —— 最高解析度，用強調色
    ],
    "radius":     0.10,    # 圓角（佔單格邊長比例）
    # 小尺寸的視覺簡化：4×4 在 32px 以下會糊成一片，
    # 降成 2×2 才保得住「深色 + 紅角」這個辨識點。
    "simplify_below": 64,
    "quadrants_small": [(1, False), (2, False), (2, False), (2, True)],
}

INK    = "#16161A"   # 近黑，紙本油墨的感覺
ACCENT = "#D9482B"   # 硃紅 —— 只用在最細的那一區
PAPER  = "#FAFAF7"   # 暖白


def _quadrants(size: int) -> list[tuple[int, bool]]:
    return (GEO["quadrants_small"] if size < GEO["simplify_below"]
            else GEO["quadrants"])


def _cells(size: int) -> list[tuple[float, float, float, float, bool]]:
    """算出所有格子的座標。回傳 (x0, y0, x1, y1, 是否強調色)。"""
    pad = GEO["pad"] * size
    span = size - pad * 2
    half = span / 2
    out = []
    for idx, (n, accent) in enumerate(_quadrants(size)):
        qx = pad + (idx % 2) * half
        qy = pad + (idx // 2) * half
        cell = half / n
        gap = half * GEO["gap"]
        for r in range(n):
            for c in range(n):
                x0 = qx + c * cell + gap / 2
                y0 = qy + r * cell + gap / 2
                out.append((x0, y0, x0 + cell - gap, y0 + cell - gap, accent))
    return out


def render_png(size: int, transparent: bool = False) -> Image.Image:
    img = Image.new("RGBA", (size, size),
                    (0, 0, 0, 0) if transparent else PAPER)
    d = ImageDraw.Draw(img)
    pad = GEO["pad"] * size
    unit = (size - pad * 2) / 2 / max(n for n, _ in _quadrants(size))
    rad = max(1, int(unit * GEO["radius"]))
    for x0, y0, x1, y1, accent in _cells(size):
        d.rounded_rectangle([x0, y0, x1, y1], radius=rad,
                            fill=ACCENT if accent else INK)
    return img


def render_svg(size: int = 512) -> str:
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}">',
             f'<rect width="{size}" height="{size}" fill="{PAPER}"/>']
    pad = GEO["pad"] * size
    unit = (size - pad * 2) / 2 / max(n for n, _ in _quadrants(size))
    rad = round(unit * GEO["radius"], 2)
    for x0, y0, x1, y1, accent in _cells(size):
        parts.append(
            f'<rect x="{x0:.2f}" y="{y0:.2f}" width="{x1-x0:.2f}" height="{y1-y0:.2f}" '
            f'rx="{rad}" fill="{ACCENT if accent else INK}"/>')
    parts.append("</svg>")
    return "\n".join(parts)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "icon.svg").write_text(render_svg(), encoding="utf-8")

    # PWA / favicon / Apple touch 需要的尺寸
    for s in (16, 32, 48, 64, 128, 180, 192, 256, 384, 512, 1024):
        render_png(s).convert("RGB").save(OUT / f"icon-{s}.png")

    # maskable（Android 會裁圓角，安全區要留更多）
    big = render_png(1024)
    canvas = Image.new("RGBA", (1024, 1024), PAPER)
    inner = big.resize((820, 820), Image.LANCZOS)
    canvas.paste(inner, (102, 102), inner)
    canvas.convert("RGB").save(OUT / "icon-maskable-512.png")

    print(f"寫入 {OUT}：icon.svg + {len(list(OUT.glob('*.png')))} 個 PNG")


if __name__ == "__main__":
    main()
