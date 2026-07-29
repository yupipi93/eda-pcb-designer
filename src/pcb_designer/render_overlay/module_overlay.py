"""Scale, rotate, and prepare a single module image for paste on a render.

The compositor passes the image_center_in_pcb_mm (resolved from positioning
mode) — render_module always centers the image on that point and rotates
around the same point. No per-module anchor_norm: the YAML's body_offset_mm
already encodes where the image center sits relative to the footprint
origin.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from .mock_image import render_mock
from .render_calibrator import Calibration

_BG_TOLERANCE = 35      # max per-channel distance from corner sample to count as bg
_BG_SAMPLE_SIZE = 8     # corner patch size in px used to estimate background colour


@dataclass
class ModuleSpec:
    name: str
    image_path: Path | None
    real_size_mm: tuple[float, float]
    image_rotation_deg: float       # CCW positive (PIL convention)
    visible_layer: str
    category: str = "default"


def _estimate_background_color(img: Image.Image) -> tuple[int, int, int]:
    """Median of the 4 corner patches — assumes product photo style backdrop."""
    w, h = img.size
    s = _BG_SAMPLE_SIZE
    samples: list[tuple[int, int, int]] = []
    for cx, cy in ((0, 0), (w - s, 0), (0, h - s), (w - s, h - s)):
        patch = img.crop((cx, cy, cx + s, cy + s)).convert("RGB")
        for px in patch.getdata():
            samples.append(px)
    rs = sorted(p[0] for p in samples)
    gs = sorted(p[1] for p in samples)
    bs = sorted(p[2] for p in samples)
    mid = len(rs) // 2
    return (rs[mid], gs[mid], bs[mid])


def _strip_background(img: Image.Image) -> Image.Image:
    """Make pixels matching the photo's backdrop transparent."""
    img = img.convert("RGBA")
    bg_r, bg_g, bg_b = _estimate_background_color(img)
    pixels = img.load()
    w, h = img.size
    tol = _BG_TOLERANCE
    for y in range(h):
        for x in range(w):
            r, g, b, _a = pixels[x, y]
            if (abs(r - bg_r) <= tol and
                abs(g - bg_g) <= tol and
                abs(b - bg_b) <= tol):
                pixels[x, y] = (r, g, b, 0)
    return img


def _has_usable_alpha(img: Image.Image) -> bool:
    """True if the image already encodes transparency (RGBA with alpha=0 in
    at least one corner)."""
    if img.mode != "RGBA":
        return False
    alpha = img.getchannel("A")
    w, h = img.size
    for x, y in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        if alpha.getpixel((x, y)) < 16:
            return True
    return False


def _load_module_image(spec: ModuleSpec, target_px: tuple[int, int]) -> Image.Image:
    if spec.image_path and spec.image_path.exists():
        try:
            raw = Image.open(spec.image_path)
            img = raw.convert("RGBA")
        except Exception:
            img = render_mock(spec.name, target_px, (0.5, 0.5), spec.category)
        else:
            if not _has_usable_alpha(img):
                img = _strip_background(img)
    else:
        img = render_mock(spec.name, target_px, (0.5, 0.5), spec.category)
    return img


def render_module(
    spec: ModuleSpec,
    pcb_rotation_deg: float,
    calib: Calibration,
) -> tuple[Image.Image, tuple[int, int]]:
    """Return (rgba_canvas, center_xy_in_canvas) ready for paste.

    The image is sized to spec.real_size_mm × px_per_mm, rotated by the
    combined angle, and centered on a square canvas. The returned center is
    where the caller should map the PCB image-center position.
    """
    w_mm, h_mm = spec.real_size_mm
    target_px = calib.mm_to_px_size(w_mm, h_mm)
    img = _load_module_image(spec, target_px)
    img = img.resize(target_px, Image.LANCZOS)

    w_px, h_px = img.size

    # Square canvas large enough to hold any rotation without clipping.
    diag = int((w_px ** 2 + h_px ** 2) ** 0.5) + 4
    canvas = Image.new("RGBA", (diag * 2, diag * 2), (0, 0, 0, 0))
    cx, cy = diag, diag
    canvas.paste(img, (cx - w_px // 2, cy - h_px // 2), img)

    # Compose rotations. The PCB rotation is the footprint orientation; the
    # image_rotation_deg compensates for the image's native orientation vs the
    # PCB rot=0 convention (pin row along +Y, pin 1 at top).
    # KiCad rot is CW with +Y down → PIL rotate(positive) is CCW → flip sign.
    #
    # The bottom photo is rendered READABLE (no left-right mirror): the B.Cu
    # footprints are placed so pad1/Vin physically lands where the bottom-
    # mounted breakout's Vin is (the footprints were rotated 180° to undo the
    # bottom-mount pin-order reversal — see place_components PLACEMENTS, ERRATA
    # §9). With that copper fix, the readable photo (Vin at top) sits over the
    # matching pads — readable AND faithful at once. Only POSITION is X-mirrored
    # (by the calibrator's mm_to_px). — sensor-orientation fix 2026-06-16.
    pil_rot = -pcb_rotation_deg + spec.image_rotation_deg
    canvas = canvas.rotate(pil_rot, resample=Image.BICUBIC, expand=False)

    return canvas, (cx, cy)
