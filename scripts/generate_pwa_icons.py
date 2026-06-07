#!/usr/bin/env python3
"""Generate PNG icons for PWA / apple-touch-icon from static/icons/icon.svg."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ICON_DIR = ROOT / "src" / "credit_rewards" / "web" / "static" / "icons"
SVG = ICON_DIR / "icon.svg"
SIZES = {
    "apple-touch-icon.png": 180,
    "icon-192.png": 192,
    "icon-512.png": 512,
}


def _render_with_pillow(size: int, out: Path) -> bool:
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return False

    img = Image.new("RGBA", (size, size), (6, 8, 13, 255))
    draw = ImageDraw.Draw(img)
    pad = size * 0.19
    w = size - pad * 2
    h = w * 0.55
    x0, y0 = pad, size * 0.33
    x1, y1 = x0 + w, y0 + h
    radius = size * 0.07
    stroke = max(2, int(size * 0.027))
    accent = (62, 224, 163, 255)

    draw.rounded_rectangle((x0, y0, x1, y1), radius=radius, outline=accent, width=stroke)
    stripe_y = y0 + h * 0.36
    draw.line((x0, stripe_y, x1, stripe_y), fill=accent, width=stroke)

    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse(
        (size * 0.15, size * 0.05, size * 0.85, size * 0.45),
        fill=(62, 224, 163, 36),
    )
    img = Image.alpha_composite(img, glow)
    img.save(out, format="PNG")
    return True


def main() -> int:
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    for name, px in SIZES.items():
        out = ICON_DIR / name
        if not _render_with_pillow(px, out):
            print("Install Pillow: pip install pillow", file=sys.stderr)
            return 1
        print(f"wrote {out.relative_to(ROOT)} ({px}px)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
