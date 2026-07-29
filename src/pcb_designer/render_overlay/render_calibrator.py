"""Detect the green FR4 PCB region in a kicad-cli render PNG.

Given a render image and the PCB outline in mm, deduce the pixel↔mm mapping
(px_per_mm, image origin offset). Works for both top and bottom renders;
the caller declares which side via `mirrored_x`.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

# HSV thresholds for "green PCB" pixels in kicad-cli renders.
# Empirical sample of v0.0.11 render: FR4 HSV ≈ (105, 106, 74) in PIL 0..255.
# Widen H to 80-125 to also capture mounting hole pads + minor shading.
_H_MIN, _H_MAX = 80, 125
_S_MIN = 40
_V_MIN = 25


@dataclass
class Calibration:
    px_per_mm: float
    x0_px: int       # pixel that corresponds to pcb x_min
    y0_px: int       # pixel that corresponds to pcb y_min
    x1_px: int       # pixel that corresponds to pcb x_max
    y1_px: int       # pixel that corresponds to pcb y_max
    pcb_x0: float
    pcb_y0: float
    pcb_x1: float
    pcb_y1: float
    mirrored_x: bool
    width_px: int
    height_px: int
    # Optional 6-DOF affine [a,b,c,d,e,f] mapping mm→px (px = a·x+b·y+c,
    # d·x+e·y+f). When present it supersedes the axis-aligned mapping: it is
    # derived from real fiducials (the mounting holes) so it absorbs the tiny
    # scale/rotation/shear the green-bbox method can't. mirror is baked in.
    affine: tuple[float, float, float, float, float, float] | None = None
    method: str = "green_bbox"

    def mm_to_px(self, x_mm: float, y_mm: float) -> tuple[int, int]:
        if self.affine is not None:
            a, b, c, d, e, f = self.affine
            return (int(round(a * x_mm + b * y_mm + c)),
                    int(round(d * x_mm + e * y_mm + f)))
        if self.mirrored_x:
            rel_x = self.pcb_x1 - x_mm
        else:
            rel_x = x_mm - self.pcb_x0
        rel_y = y_mm - self.pcb_y0
        return (
            self.x0_px + int(round(rel_x * self.px_per_mm)),
            self.y0_px + int(round(rel_y * self.px_per_mm)),
        )

    def mm_to_px_size(self, w_mm: float, h_mm: float) -> tuple[int, int]:
        return (max(1, int(round(w_mm * self.px_per_mm))),
                max(1, int(round(h_mm * self.px_per_mm))))


def _build_green_mask(img: Image.Image) -> Image.Image:
    """Return a 1-bit mask where green PCB pixels are white."""
    hsv = img.convert("HSV")
    h_band, s_band, v_band = hsv.split()
    h_mask = h_band.point(lambda p: 255 if _H_MIN <= p <= _H_MAX else 0)
    s_mask = s_band.point(lambda p: 255 if p >= _S_MIN else 0)
    v_mask = v_band.point(lambda p: 255 if p >= _V_MIN else 0)
    # Combine: pixel must satisfy all three.
    from PIL import ImageChops
    combined = ImageChops.multiply(h_mask, s_mask)
    combined = ImageChops.multiply(combined, v_mask)
    return combined.convert("1")


def _dominant_range(counts: list[int], min_fraction: float = 0.5) -> tuple[int, int]:
    """Return (lo, hi) — the longest contiguous run of indices whose `counts`
    value is >= peak * min_fraction.

    Useful to reject outliers (e.g. a 1-pixel-wide socket body extending past
    the PCB edge) while keeping the wide rectangular PCB region.
    """
    if not counts:
        return (0, 0)
    peak = max(counts)
    if peak == 0:
        return (0, 0)
    threshold = peak * min_fraction
    best_lo, best_hi, best_len = 0, 0, 0
    cur_lo = None
    for i, c in enumerate(counts):
        if c >= threshold:
            if cur_lo is None:
                cur_lo = i
        else:
            if cur_lo is not None:
                length = i - cur_lo
                if length > best_len:
                    best_lo, best_hi, best_len = cur_lo, i, length
                cur_lo = None
    if cur_lo is not None:
        length = len(counts) - cur_lo
        if length > best_len:
            best_lo, best_hi, best_len = cur_lo, len(counts), length
    return (best_lo, best_hi)


def calibrate(
    render_path: Path,
    pcb_outline_mm: tuple[float, float, float, float],
    *,
    mirrored_x: bool,
) -> Calibration:
    """Detect the PCB green rectangle in `render_path` and return a Calibration."""
    img = Image.open(render_path).convert("RGB")
    width, height = img.size

    mask = _build_green_mask(img)
    bbox = mask.getbbox()
    if bbox is None:
        raise RuntimeError(
            f"No green PCB pixels detected in {render_path}. "
            f"Render might be empty or HSV thresholds need tuning."
        )

    # Initial bbox from PIL.
    x0_px, y0_px, x1_px, y1_px = bbox

    # If the bbox aspect ratio diverges from the PCB outline, a thin protrusion
    # (3D socket body off the board edge) likely contaminated it. Tighten by
    # taking the longest contiguous range of rows/cols above 30% of peak.
    pcb_x0, pcb_y0, pcb_x1, pcb_y1 = pcb_outline_mm
    pcb_w = pcb_x1 - pcb_x0
    pcb_h = pcb_y1 - pcb_y0
    initial_ratio = ((x1_px - x0_px) / pcb_w) / ((y1_px - y0_px) / pcb_h)
    if not (0.95 <= initial_ratio <= 1.05):
        px_mask = mask.load()
        col_counts = [0] * width
        row_counts = [0] * height
        for y in range(height):
            for x in range(width):
                if px_mask[x, y]:
                    col_counts[x] += 1
                    row_counts[y] += 1
        x0c, x1c = _dominant_range(col_counts, min_fraction=0.3)
        y0c, y1c = _dominant_range(row_counts, min_fraction=0.3)
        if (x1c - x0c) > 0 and (y1c - y0c) > 0:
            x0_px, y0_px, x1_px, y1_px = x0c, y0c, x1c, y1c

    bbox_w, bbox_h = x1_px - x0_px, y1_px - y0_px
    if bbox_w <= 0 or bbox_h <= 0:
        raise RuntimeError(
            f"Green range degenerate in {render_path}: "
            f"width={bbox_w}, height={bbox_h}"
        )

    # Sanity check: the detected aspect ratio must match the real PCB.
    px_per_mm_x = bbox_w / pcb_w
    px_per_mm_y = bbox_h / pcb_h
    ratio = max(px_per_mm_x, px_per_mm_y) / min(px_per_mm_x, px_per_mm_y)
    if ratio > 1.05:
        raise RuntimeError(
            f"Detected green bbox aspect ratio diverges from PCB outline "
            f"({px_per_mm_x:.2f} vs {px_per_mm_y:.2f} px/mm — ratio {ratio:.3f}). "
            f"Check HSV thresholds or the render quality."
        )

    px_per_mm = (px_per_mm_x + px_per_mm_y) / 2

    return Calibration(
        px_per_mm=px_per_mm,
        x0_px=x0_px,
        y0_px=y0_px,
        x1_px=x1_px,
        y1_px=y1_px,
        pcb_x0=pcb_x0,
        pcb_y0=pcb_y0,
        pcb_x1=pcb_x1,
        pcb_y1=pcb_y1,
        mirrored_x=mirrored_x,
        width_px=width,
        height_px=height,
    )


def calibrate_from_holes(
    render_path: Path,
    pcb_outline_mm: tuple[float, float, float, float],
    holes_mm: dict[str, tuple[float, float]],
    *,
    mirrored_x: bool,
    drill_dia_mm: float = 2.5,
    min_holes: int = 4,
    fallback: bool = True,
) -> Calibration:
    """Precise calibration from the mounting holes themselves (FASE 2).

    Detects each hole's lighting-invariant dark-bore centre and fits a 6-DOF
    mm→px affine — the exact px/mm derivation the task asks for (verifiable
    fiducials, no hand-tuned numbers). Falls back to the green-bbox `calibrate`
    when fewer than `min_holes` are detected (e.g. boards before v0.1.3).
    """
    from pcb_designer.verify.holes import detect_holes_in_render

    try:
        det = detect_holes_in_render(
            render_path, holes_mm, pcb_outline_mm,
            side=("bottom" if mirrored_x else "top"),
            mirrored=mirrored_x, drill_dia_mm=drill_dia_mm,
        )
    except Exception:
        if fallback:
            return calibrate(render_path, pcb_outline_mm, mirrored_x=mirrored_x)
        raise

    if len(det.detected_px) < min_holes:
        if fallback:
            return calibrate(render_path, pcb_outline_mm, mirrored_x=mirrored_x)
        raise RuntimeError(
            f"calibrate_from_holes: solo {len(det.detected_px)} orificios "
            f"detectados (<{min_holes})"
        )

    a, b, c, d, e, f = det.affine
    x0, y0, x1, y1 = pcb_outline_mm
    img = Image.open(render_path)
    w, h = img.size
    cal = Calibration(
        px_per_mm=det.ppm,
        # px corners kept for any consumer reading them; computed via the affine.
        x0_px=int(round(a * x0 + b * y0 + c)),
        y0_px=int(round(d * x0 + e * y0 + f)),
        x1_px=int(round(a * x1 + b * y1 + c)),
        y1_px=int(round(d * x1 + e * y1 + f)),
        pcb_x0=x0, pcb_y0=y0, pcb_x1=x1, pcb_y1=y1,
        mirrored_x=mirrored_x, width_px=w, height_px=h,
        affine=(a, b, c, d, e, f), method="mounting_holes",
    )
    return cal
