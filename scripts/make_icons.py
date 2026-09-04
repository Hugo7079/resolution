"""
識別圖示產生器
==============

概念：**半色調網點由大到小**。

半色調（halftone）是印刷把連續調轉成網點的手法，「網點多細」就是解析度本身 ——
這是設計／印刷的核心語彙，不是外借的比喻。點由左至右遞減，
就是「同一件事看得越來越細」。

標誌單色。強調色留給介面用 —— 標誌不靠顏色撐，辨識度才站得住。

網點天生需要解析度才讀得出來，所以 64px 以下自動降成 2×2：
保住「大小遞減的點」這個概念，而不是糊成一團灰。

幾何參數全部寫在 GEO，改完重跑就同步更新 SVG 與所有尺寸的 PNG。

    python3 scripts/make_icons.py
"""

from __future__ import annotations
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / "web" / "icons"

GEO = {
    "pad":   0.145,   # 四周留白（佔畫布比例）
    "grid":  3,       # 主要版本的網格數
    "big":   0.44,    # 最大點半徑（佔單格邊長比例）
    "small": 0.15,    # 最小點半徑
    # 小尺寸簡化：網點需要解析度才讀得出來，64px 以下降成 2×2
    "simplify_below": 64,
    "grid_small": 2,
    "big_small": 0.42,
    "small_small": 0.19,
}

INK   = "#16161A"   # 近黑，紙本油墨
PAPER = "#FAFAF7"   # 暖白


def _params(size: int) -> tuple[int, float, float]:
    if size < GEO["simplify_below"]:
        return GEO["grid_small"], GEO["big_small"], GEO["small_small"]
    return GEO["grid"], GEO["big"], GEO["small"]


def _dots(size: int) -> list[tuple[float, float, float]]:
    """回傳 (cx, cy, r)。點由左至右遞減。"""
    n, big, small = _params(size)
    pad = GEO["pad"] * size
    span = size - pad * 2
    cell = span / n
    out = []
    for row in range(n):
        for col in range(n):
            t = col / (n - 1) if n > 1 else 0.0
            r = cell * (big + (small - big) * t)
            out.append((pad + col * cell + cell / 2,
                        pad + row * cell + cell / 2, r))
    return out


def render_png(size: int, transparent: bool = False) -> Image.Image:
    img = Image.new("RGBA", (size, size),
                    (0, 0, 0, 0) if transparent else PAPER)
    d = ImageDraw.Draw(img)
    for cx, cy, r in _dots(size):
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=INK)
    return img


def render_svg(size: int = 512) -> str:
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}">',
             f'<rect width="{size}" height="{size}" fill="{PAPER}"/>']
    for cx, cy, r in _dots(size):
        parts.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" fill="{INK}"/>')
    parts.append("</svg>")
    return "\n".join(parts)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "icon.svg").write_text(render_svg(), encoding="utf-8")

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
