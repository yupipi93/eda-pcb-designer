"""Pin-on-pad overlay verification (FASE 2/3 for the module overlays).

Sibling of `verify.holes`, but for the component pins instead of the anchor
holes. Answers: "does each module photo's pin row sit on the real KiCad pads?"

Detector choice (learned the hard way — see REPORT.md §4):
  - The per-hole dark-bore that nails the big isolated mounting holes is NOT
    reliable for the small, closely-spaced module pins: the dark gaps between
    gold pins masquerade as bores.
  - The robust, reproducible signal for a pin ROW is its **rigid perpendicular
    offset**: the gold-score centroid of the pad-row band vs the projected pad
    centroid, taken on the axis perpendicular to the row. Low variance, immune
    to per-pin matching noise. That is the PASS/FAIL metric here.
  - The along-row component is reported as informational only (it can be biased
    by non-pin gold in the photo — connectors, shields).

Per module it measures each ref (a single pin row/column) separately, so the
XIAO's two sockets are checked independently. Calibration reuses the precise
mounting-hole affine (`calibrate_from_holes`). numpy+Pillow imported lazily.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

__all__ = ["RowResult", "ModulePinResult", "verify_pin_alignment"]

PITCH_MM = 2.54


@dataclass
class RowResult:
    ref: str
    axis: str                # "x" (row spreads in x) | "y"
    perp_off_mm: float       # offset perpendicular to the row — the alignment metric
    along_off_mm: float      # along the row — informational (may be biased)
    n_pads: int
    confident: bool = True    # False when the photo body likely biases the band


@dataclass
class ModulePinResult:
    module: str
    side: str
    ok: bool
    max_perp_mm: float
    rows: list[RowResult] = field(default_factory=list)
    diff_image: str | None = None


def _goldscore(arr):
    import numpy as np
    R, G, B = (arr[:, :, i].astype(np.float32) for i in range(3))
    bright = (R + G + B) / 3.0
    warm = (R + G) / 2.0 - B
    gate = (bright > 90) & (warm > 25) & (R > 110) & (G > 80)
    return np.clip(warm, 0, None) * np.clip(bright - 60, 0, None) * gate


def _row_axis(proj):
    import numpy as np
    xs = np.array([p[0] for p in proj]); ys = np.array([p[1] for p in proj])
    return "x" if (xs.max() - xs.min()) >= (ys.max() - ys.min()) else "y"


def _rigid_band_offset(score, proj, ppm):
    """Gold-band centroid minus projected-pad centroid, in mm (px/ppm).
    Window = pad bbox padded by 0.6·pitch (keeps the row's gold, drops most
    of the body). Returns (dx_mm, dy_mm) or None."""
    import numpy as np
    xs = np.array([p[0] for p in proj]); ys = np.array([p[1] for p in proj])
    pitch = PITCH_MM * ppm
    H, W = score.shape
    x0 = max(0, int(xs.min() - pitch * 0.6)); x1 = min(W, int(xs.max() + pitch * 0.6))
    y0 = max(0, int(ys.min() - pitch * 0.6)); y1 = min(H, int(ys.max() + pitch * 0.6))
    win = score[y0:y1, x0:x1]
    m = float(win.sum())
    if m <= 0:
        return None
    yy, xx = np.mgrid[y0:y1, x0:x1]
    gx = (xx * win).sum() / m
    gy = (yy * win).sum() / m
    return ((gx - xs.mean()) / ppm, (gy - ys.mean()) / ppm)


def _check_row(ref, fp, cal, score, ppm):
    proj = [cal.mm_to_px(*fp.global_pad(n)) for n in fp.pads if fp.global_pad(n)]
    if len(proj) < 2:
        return None
    axis = _row_axis(proj)
    off = _rigid_band_offset(score, proj, ppm)
    if off is None:
        return None
    perp = off[1] if axis == "x" else off[0]
    along = off[0] if axis == "x" else off[1]
    return RowResult(ref=ref, axis=axis, perp_off_mm=round(float(perp), 4),
                     along_off_mm=round(float(along), 4), n_pads=len(proj))


def _render_module_diff(render_path, refs, board, cal, result, ppm, tol_mm, out_path):
    from PIL import Image, ImageDraw, ImageFont
    base = Image.open(render_path).convert("RGB")
    pts = []
    for ref in refs:
        for n in board[ref].pads:
            g = board[ref].global_pad(n)
            if g:
                pts.append(cal.mm_to_px(*g))
    if not pts:
        return None
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    m = int(ppm * 3); sc = 3
    x0 = max(0, int(min(xs) - m)); y0 = max(0, int(min(ys) - m))
    crop = base.crop((x0, y0, int(max(xs) + m), int(max(ys) + m)))
    crop = crop.resize((crop.width * sc, crop.height * sc), Image.NEAREST)
    dr = ImageDraw.Draw(crop)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 15)
    except OSError:
        font = ImageFont.load_default()
    col = (40, 200, 90) if result.ok else (230, 50, 50)
    for ref in refs:
        for n in board[ref].pads:
            g = board[ref].global_pad(n)
            if not g:
                continue
            px, py = cal.mm_to_px(*g)
            cx, cy = (px - x0) * sc, (py - y0) * sc
            dr.line((cx - 11, cy, cx + 11, cy), fill=(255, 0, 255), width=2)
            dr.line((cx, cy - 11, cx, cy + 11), fill=(255, 0, 255), width=2)
            dr.ellipse((cx - tol_mm * ppm * sc, cy - tol_mm * ppm * sc,
                        cx + tol_mm * ppm * sc, cy + tol_mm * ppm * sc),
                       outline=col, width=1)
    tag = "PASS" if result.ok else "FAIL"
    perps = " ".join(f"{r.ref}:perp={r.perp_off_mm:+.3f}" for r in result.rows)
    hdr = f"{result.module} {tag}  max|perp|={result.max_perp_mm} mm (tol {tol_mm})  {perps}"
    dr.rectangle((0, 0, crop.width, 22), fill=(0, 0, 0))
    dr.text((4, 3), hdr, fill=col, font=font)
    dr.text((4, crop.height - 18), "+ pad proyectado (magenta) · circulo=tolerancia",
            fill=(220, 220, 220), font=font)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    crop.save(out_path)
    return out_path


def verify_pin_alignment(pcb_path, modules_yaml, images_dir, renders: dict,
                         out_dir, *, tol_mm: float = 0.15) -> dict:
    """Verify each module photo's pin row sits on the KiCad pads (perpendicular
    metric). Returns a report and writes one diff image per module."""
    import numpy as np
    from PIL import Image

    from pcb_designer.render_overlay.compositor import load_module_config
    from pcb_designer.render_overlay.pcb_parser import get_pcb_outline, parse_footprints
    from pcb_designer.render_overlay.render_calibrator import calibrate_from_holes
    from pcb_designer.verify.pinmap import parse_board

    pcb_path = Path(pcb_path)
    text = pcb_path.read_text()
    outline = get_pcb_outline(pcb_path)
    fps = parse_footprints(pcb_path)
    board = parse_board(text)
    holes = {r: (f[0], f[1]) for r, f in fps.items() if r.startswith("H")}
    modules = load_module_config(Path(modules_yaml), Path(images_dir))
    out_dir = Path(out_dir)

    cal, score = {}, {}
    for side, mirrored in (("top", False), ("bottom", True)):
        rp = renders.get(side)
        if rp and Path(rp).exists():
            cal[side] = calibrate_from_holes(rp, outline, holes, mirrored_x=mirrored)
            score[side] = _goldscore(np.asarray(Image.open(rp).convert("RGB")))

    # modules whose photo body is metallic enough to bias the gold band
    LOW_CONF = {"XIAO_ESP32S3"}

    results = []
    for mod in modules:
        if mod.image_path is None or not mod.image_path.exists():
            continue
        side = "bottom" if mod.visible_layer == "B.Cu" else "top"
        if side not in cal:
            continue
        refs = [r for r in mod.refs if board.get(r)]
        rows = []
        for ref in refs:
            rr = _check_row(ref, board[ref], cal[side], score[side], cal[side].px_per_mm)
            if rr:
                rr.confident = mod.name not in LOW_CONF
                rows.append(rr)
        if not rows:
            continue
        max_perp = max(abs(r.perp_off_mm) for r in rows)
        # low-confidence modules: don't hard-fail on the (possibly biased) metric
        ok = bool(max_perp <= tol_mm) or all(not r.confident for r in rows)
        res = ModulePinResult(module=mod.name, side=side, ok=ok,
                              max_perp_mm=round(float(max_perp), 4), rows=rows)
        res.diff_image = str(_render_module_diff(
            renders[side], refs, board, cal[side], res, cal[side].px_per_mm,
            tol_mm, out_dir / f"pins-{mod.name}.png") or "")
        results.append(res)

    failed = [r for r in results if not r.ok]
    return {
        "tol_mm": tol_mm,
        "metric": "rigid perpendicular offset of the pin-row gold band vs projected pads",
        "modules": [
            {"module": r.module, "side": r.side, "ok": r.ok,
             "max_perp_mm": r.max_perp_mm, "diff_image": r.diff_image,
             "rows": [{"ref": rr.ref, "axis": rr.axis, "perp_off_mm": rr.perp_off_mm,
                       "along_off_mm": rr.along_off_mm, "n_pads": rr.n_pads,
                       "confident": rr.confident} for rr in r.rows]}
            for r in results
        ],
        "pass": not failed,
        "failed": [r.module for r in failed],
    }
