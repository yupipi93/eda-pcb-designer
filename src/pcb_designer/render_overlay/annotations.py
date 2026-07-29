"""Technical-drawing dimension annotations for the photorealistic renders.

Adds thin dimension lines + labels for: PCB outline, anchor zones, mounting
hole spacings, key pin row separations, and per-module bounding boxes. All
geometry is derived from the .kicad_pcb and modules.yaml — annotations stay
correct across PCB iterations without hand-editing this file.

The annotation system is split into "draw_*" primitives (geometric building
blocks) and category-level helpers that pull data from the PCB + YAML.
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageFont

from .render_calibrator import Calibration

# ── Visual style ────────────────────────────────────────────────────────────
COLOR_PCB    = (40, 40, 60, 230)         # dark blue-gray
COLOR_ANCHOR = (200, 80, 180, 230)       # magenta — structural anchor zones
COLOR_HOLE   = (220, 160, 40, 230)       # orange — mounting holes
COLOR_MODULE = (40, 160, 90, 230)        # green — module bounding boxes
COLOR_PIN    = (60, 130, 220, 230)       # blue — pin row separations
LABEL_BG     = (255, 255, 255, 215)
LINE_WIDTH   = 1
ARROW_SIZE   = 5
TICK_LEN     = 5
FONT_SIZE    = 11
LABEL_PAD    = 2

# Project-specific anchor zone constants (mm). Update if the PCB convention
# changes; v0.0.10+ is stable at 10mm left / 20mm right.
LEFT_ANCHOR_INNER_X  = 100.0
RIGHT_ANCHOR_INNER_X = 170.0


def _font(size: int):
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _text_size(draw: ImageDraw.ImageDraw, text: str, font) -> tuple[int, int]:
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    except AttributeError:
        return draw.textsize(text, font=font)


def _draw_arrow(draw, x: float, y: float, dx: float, dy: float,
                size: int = ARROW_SIZE, color=COLOR_PCB) -> None:
    """Filled triangle arrowhead. (dx, dy) is the direction the tip points."""
    length = math.hypot(dx, dy)
    if length == 0:
        return
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    tip = (x, y)
    b1 = (x - size * ux + 0.5 * size * px, y - size * uy + 0.5 * size * py)
    b2 = (x - size * ux - 0.5 * size * px, y - size * uy - 0.5 * size * py)
    draw.polygon([tip, b1, b2], fill=color)


def _draw_label(draw, x: int, y: int, text: str, color=COLOR_PCB,
                anchor: str = "mm") -> None:
    """Text with a white background box. anchor: 2 chars (h, v)
    h ∈ {l, m, r} (left/middle/right of text), v ∈ {t, m, b} (top/middle/bottom)."""
    font = _font(FONT_SIZE)
    tw, th = _text_size(draw, text, font)
    h, v = anchor[0], anchor[1]
    if   h == "l": bx = x
    elif h == "m": bx = x - tw // 2
    elif h == "r": bx = x - tw
    else: bx = x
    if   v == "t": by = y
    elif v == "m": by = y - th // 2
    elif v == "b": by = y - th
    else: by = y
    pad = LABEL_PAD
    draw.rectangle((bx - pad, by - pad, bx + tw + pad, by + th + pad),
                   fill=LABEL_BG)
    draw.text((bx, by), text, fill=color, font=font)


def _dim_h(draw, calib: Calibration, x1_mm: float, x2_mm: float, y_mm: float,
           label: str, color=COLOR_PCB, label_above: bool = True,
           extension_tick: bool = True) -> None:
    """Horizontal dimension line between two PCB X positions at given Y."""
    p1 = calib.mm_to_px(x1_mm, y_mm)
    p2 = calib.mm_to_px(x2_mm, y_mm)
    py = p1[1]
    px1, px2 = sorted((p1[0], p2[0]))
    if extension_tick:
        draw.line([(px1, py - TICK_LEN), (px1, py + TICK_LEN)],
                  fill=color, width=LINE_WIDTH)
        draw.line([(px2, py - TICK_LEN), (px2, py + TICK_LEN)],
                  fill=color, width=LINE_WIDTH)
    draw.line([(px1, py), (px2, py)], fill=color, width=LINE_WIDTH)
    if px2 - px1 > 3 * ARROW_SIZE:
        _draw_arrow(draw, px1, py, -1, 0, color=color)
        _draw_arrow(draw, px2, py, 1, 0, color=color)
    lx = (px1 + px2) // 2
    ly = py - 10 if label_above else py + 10
    _draw_label(draw, lx, ly, label, color=color,
                anchor="mb" if label_above else "mt")


def _dim_v(draw, calib: Calibration, y1_mm: float, y2_mm: float, x_mm: float,
           label: str, color=COLOR_PCB, label_right: bool = True,
           extension_tick: bool = True) -> None:
    """Vertical dimension line at PCB X between two Y values."""
    p1 = calib.mm_to_px(x_mm, y1_mm)
    p2 = calib.mm_to_px(x_mm, y2_mm)
    px = p1[0]
    py1, py2 = sorted((p1[1], p2[1]))
    if extension_tick:
        draw.line([(px - TICK_LEN, py1), (px + TICK_LEN, py1)],
                  fill=color, width=LINE_WIDTH)
        draw.line([(px - TICK_LEN, py2), (px + TICK_LEN, py2)],
                  fill=color, width=LINE_WIDTH)
    draw.line([(px, py1), (px, py2)], fill=color, width=LINE_WIDTH)
    if py2 - py1 > 3 * ARROW_SIZE:
        _draw_arrow(draw, px, py1, 0, -1, color=color)
        _draw_arrow(draw, px, py2, 0, 1, color=color)
    lx = px + 10 if label_right else px - 10
    ly = (py1 + py2) // 2
    _draw_label(draw, lx, ly, label, color=color,
                anchor="lm" if label_right else "rm")


def _bbox_outline(draw, calib: Calibration, x1_mm: float, y1_mm: float,
                  x2_mm: float, y2_mm: float, color, label: str | None = None) -> None:
    """Thin rectangle outline (e.g., module bbox)."""
    p1 = calib.mm_to_px(x1_mm, y1_mm)
    p2 = calib.mm_to_px(x2_mm, y2_mm)
    x_min, x_max = sorted((p1[0], p2[0]))
    y_min, y_max = sorted((p1[1], p2[1]))
    draw.rectangle((x_min, y_min, x_max, y_max), outline=color, width=LINE_WIDTH)
    if label:
        _draw_label(draw, (x_min + x_max) // 2, y_min - 2, label,
                    color=color, anchor="mb")


# ── Category-level annotation helpers ───────────────────────────────────────

def _annotate_pcb_outline(draw, calib, pcb_outline):
    x0, y0, x1, y1 = pcb_outline
    w, h = x1 - x0, y1 - y0
    # Total width: dim line ~6mm ABOVE the PCB top edge
    _dim_h(draw, calib, x0, x1, y0 - 6.0,
           f"PCB {w:.0f} mm", color=COLOR_PCB, label_above=True)
    # Total height: dim line ~6mm to the RIGHT of the PCB right edge
    _dim_v(draw, calib, y0, y1, x1 + 6.0,
           f"{h:.0f} mm", color=COLOR_PCB, label_right=True)


def _annotate_anchors(draw, calib, pcb_outline):
    x0, y0, x1, y1 = pcb_outline
    # Left anchor width — line below the PCB
    left_w = LEFT_ANCHOR_INNER_X - x0
    _dim_h(draw, calib, x0, LEFT_ANCHOR_INNER_X, y1 + 4.0,
           f"L:{left_w:.0f}", color=COLOR_ANCHOR, label_above=False)
    # Right anchor width
    right_w = x1 - RIGHT_ANCHOR_INNER_X
    _dim_h(draw, calib, RIGHT_ANCHOR_INNER_X, x1, y1 + 4.0,
           f"R:{right_w:.0f}", color=COLOR_ANCHOR, label_above=False)
    # Electronic zone width (one step further from PCB)
    elec_w = RIGHT_ANCHOR_INNER_X - LEFT_ANCHOR_INNER_X
    _dim_h(draw, calib, LEFT_ANCHOR_INNER_X, RIGHT_ANCHOR_INNER_X, y1 + 10.0,
           f"electronic zone {elec_w:.0f}", color=COLOR_ANCHOR,
           label_above=False)


def _annotate_mounting_holes(draw, calib, footprints):
    holes = {ref: footprints[ref] for ref in footprints if ref.startswith("H")}
    if not holes:
        return

    # Cluster by anchor side
    left = sorted([r for r in holes if holes[r][0] < LEFT_ANCHOR_INNER_X],
                  key=lambda r: holes[r][1])
    right = sorted([r for r in holes if holes[r][0] > RIGHT_ANCHOR_INNER_X],
                   key=lambda r: (holes[r][1], holes[r][0]))

    # Left anchor: vertical pair separation
    if len(left) >= 2:
        a, b = left[0], left[-1]
        xa, ya = holes[a][:2]
        _, yb = holes[b][:2]
        _dim_v(draw, calib, ya, yb, xa - 3.0,
               f"{a}-{b} {abs(yb - ya):.0f}", color=COLOR_HOLE,
               label_right=False)

    # Right anchor: assume 2x2 — horizontal pair (top row) + vertical pair
    if len(right) >= 4:
        # Group by Y
        by_y: dict[float, list[str]] = {}
        for r in right:
            by_y.setdefault(round(holes[r][1], 2), []).append(r)
        ys = sorted(by_y.keys())
        # Horizontal spacing in TOP row
        top = sorted(by_y[ys[0]], key=lambda r: holes[r][0])
        if len(top) >= 2:
            xa, ya = holes[top[0]][:2]
            xb, _ = holes[top[-1]][:2]
            _dim_h(draw, calib, xa, xb, ya - 3.0,
                   f"{abs(xb - xa):.0f}", color=COLOR_HOLE, label_above=True)
        # Vertical spacing between rows (left column)
        bot = sorted(by_y[ys[-1]], key=lambda r: holes[r][0])
        if top and bot:
            xa, ya = holes[top[0]][:2]
            _, yb = holes[bot[0]][:2]
            _dim_v(draw, calib, ya, yb, xa - 3.0,
                   f"{abs(yb - ya):.0f}", color=COLOR_HOLE,
                   label_right=False)


def _annotate_xiao_socket_separation(draw, calib, footprints, pcb_outline):
    if "U1" not in footprints or "U5" not in footprints:
        return
    x1, y1 = footprints["U1"][:2]
    x2, _ = footprints["U5"][:2]
    # Above the PCB top edge, between the PCB-outline dim and the board
    y0 = pcb_outline[1]
    _dim_h(draw, calib, x1, x2, y0 - 2.0,
           f"U1↔U5 {abs(x2 - x1):.2f}", color=COLOR_PIN, label_above=True)


def _annotate_modules(draw, calib, modules, footprints, side: str):
    """Draw a thin bbox + size label around each visible module."""
    target_layer = "F.Cu" if side == "top" else "B.Cu"
    for mod in modules:
        if mod.visible_layer != target_layer:
            continue
        if mod.anchor_ref not in footprints:
            continue
        # Resolve image center (same logic as compositor for consistency)
        from .compositor import _compute_image_center_mm
        cx, cy, _rot = _compute_image_center_mm(mod, footprints)
        w_mm, h_mm = mod.real_size_mm
        # After image_rotation_deg, the IMAGE's effective dims may swap when
        # the rotation is 90° or 270°. Account for that so the bbox visualizes
        # the ACTUAL footprint of the module image on the PCB.
        eff_rot = (mod.image_rotation_deg - footprints[mod.anchor_ref][2]) % 180
        if abs(eff_rot - 90) < 1:
            w_mm, h_mm = h_mm, w_mm
        x_min = cx - w_mm / 2
        y_min = cy - h_mm / 2
        x_max = cx + w_mm / 2
        y_max = cy + h_mm / 2
        label = f"{mod.name} {mod.real_size_mm[0]:.1f}×{mod.real_size_mm[1]:.1f}"
        _bbox_outline(draw, calib, x_min, y_min, x_max, y_max,
                      color=COLOR_MODULE, label=label)


# ── Public entry point ──────────────────────────────────────────────────────

def draw_annotations(
    base: Image.Image,
    calib: Calibration,
    pcb_outline_mm: tuple[float, float, float, float],
    footprints: dict,
    modules: list,
    *,
    side: str = "top",
    categories: tuple[str, ...] = ("pcb", "anchors", "holes", "modules", "pins"),
) -> None:
    """Annotate the rendered image with dimension lines + labels.

    Categories (any subset of the default):
      pcb      → overall PCB outline width × height
      anchors  → left/right anchor widths + electronic zone width
      holes    → mounting hole spacings within each anchor cluster
      modules  → thin bbox + size label per visible module
      pins     → key pin row separations (e.g. XIAO U1↔U5)

    `side` is "top" or "bottom" — annotations use the same Calibration so
    mirroring is handled automatically.
    """
    draw = ImageDraw.Draw(base)
    if "pcb" in categories:
        _annotate_pcb_outline(draw, calib, pcb_outline_mm)
    if "anchors" in categories:
        _annotate_anchors(draw, calib, pcb_outline_mm)
    if "holes" in categories:
        _annotate_mounting_holes(draw, calib, footprints)
    if "pins" in categories:
        _annotate_xiao_socket_separation(draw, calib, footprints, pcb_outline_mm)
    if "modules" in categories:
        _annotate_modules(draw, calib, modules, footprints, side)
