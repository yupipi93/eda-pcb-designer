"""Procedural mockup PIL images for modules whose photo is missing.

Used as a fallback so the compositor never breaks on a missing asset. The
mockup encodes the module name, real dimensions, and a pin-1 marker so the
overlay still validates placement / rotation / scale.
"""
from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

_PALETTE = {
    "sensor":  (40, 90, 160, 220),    # blueish
    "module":  (40, 60, 40, 220),     # FR4-green
    "switch":  (30, 30, 30, 220),     # black
    "connector": (200, 200, 200, 220),  # white-ish
    "default": (80, 80, 100, 220),
}


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size)
    except OSError:
        return ImageFont.load_default()


def render_mock(
    name: str,
    size_px: tuple[int, int],
    anchor_norm: tuple[float, float],
    category: str = "default",
) -> Image.Image:
    """Generate an RGBA mock image of the requested size with module label."""
    w, h = size_px
    fill = _PALETTE.get(category, _PALETTE["default"])

    img = Image.new("RGBA", (w, h), fill)
    draw = ImageDraw.Draw(img)

    # Border so the bbox is unambiguous.
    draw.rectangle((0, 0, w - 1, h - 1), outline=(255, 255, 255, 255), width=2)

    # Pin-1 marker (small white circle).
    ax = int(anchor_norm[0] * w)
    ay = int(anchor_norm[1] * h)
    r = max(3, min(w, h) // 18)
    draw.ellipse((ax - r, ay - r, ax + r, ay + r), fill=(255, 60, 60, 255))

    # Centered name.
    font = _font(max(10, min(w, h) // 6))
    text = name
    try:
        tb = draw.textbbox((0, 0), text, font=font)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
    except AttributeError:
        tw, th = draw.textsize(text, font=font)
    draw.text(((w - tw) / 2, (h - th) / 2), text, fill=(255, 255, 255, 255),
              font=font)

    return img
