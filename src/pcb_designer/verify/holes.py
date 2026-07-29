"""Mounting-hole (anchor-hole) verification — geometric + CV + visual diff.

Three complementary methods, applied to MT1 v0.1.3's six M2 anchor holes
(H1..H6). Each answers a different question, ordered by source priority
(FASE 1: drill/design > datasheet > standard footprint):

  G — Geométrico  : ¿están los orificios del DISEÑO (.kicad_pcb) en la posición
                    y con el Ø de la ground-truth?  (PASS/FAIL exacto por orificio
                    + verificación de las separaciones del patrón de anclaje.)
                    Fuente de verdad PRIMARIA — texto puro, sin pcbnew.

  V — Visión      : detecta el centro real de cada anillo dorado en el render
                    (calibración por la caja verde del PCB + refinado mean-shift
                    del centroide dorado), ajusta una afín mm→px de 6 DOF y mide:
                      · residual de ajuste completo (consistencia intra-render)
                      · error leave-one-out (predice cada orificio con los otros
                        5 → un orificio mal colocado salta como atípico, sin
                        circularidad).

  D — Diff visual : imagen de comprobación por cara (+ montaje de recortes por
                    orificio) con el círculo ESPERADO (verde=PASS / rojo=FAIL),
                    su centro (+) y el centro DETECTADO (x), y la desviación mm.

`parse_design_holes` / `check_holes_geometric` / `load_holes_groundtruth`
son texto puro (stdlib + PyYAML) y corren en cualquier sitio. La parte de
visión (`detect_holes_in_render`, `render_*`) importa numpy + Pillow de forma
perezosa, así que la verificación geométrica no depende de ellos.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

__all__ = [
    "DesignHole", "HolesGroundTruth", "HoleFinding", "HoleDetection",
    "parse_design_holes", "get_pcb_outline", "load_holes_groundtruth",
    "check_holes_geometric", "detect_holes_in_render", "check_holes_cv",
    "render_holes_diff", "render_hole_crops", "verify_holes",
]


# ── data ─────────────────────────────────────────────────────────────────────
@dataclass
class DesignHole:
    ref: str
    x: float
    y: float
    drill_dia: float | None
    pad_dia: float | None
    layer: str
    library: str
    descr: str = ""


@dataclass
class HolesGroundTruth:
    holes: dict[str, dict]            # ref -> {x, y, group, [pos_tol], [dia_tol]}
    outline: tuple[float, float, float, float]
    screw: str
    drill_dia: float
    pad_dia: float
    pos_tol: float
    dia_tol: float
    cv_tol: float
    spacings: list[dict] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    def pos_tol_for(self, ref: str) -> float:
        return float(self.holes.get(ref, {}).get("pos_tol", self.pos_tol))

    def dia_tol_for(self, ref: str) -> float:
        return float(self.holes.get(ref, {}).get("dia_tol", self.dia_tol))


@dataclass
class HoleFinding:
    ref: str
    check: str                       # "geometric" | "spacing" | "cv"
    ok: bool
    message: str
    deviation_mm: float | None = None
    severity: str = "critical"       # critical | warning | info
    detail: str = ""


@dataclass
class HoleDetection:
    side: str
    ppm: float                       # px per mm (from the fitted affine)
    affine: list[float]              # [a,b,c,d,e,f] : px = (a*x+b*y+c, d*x+e*y+f)
    expected_mm: dict[str, tuple[float, float]]
    detected_px: dict[str, tuple[float, float]]      # true centre (dark bore)
    full_resid_mm: dict[str, float]  # |detected - affine(expected)|, intra-render
    loo_err_mm: dict[str, float]     # |detected - affine_fit_on_other_5(expected)|
    gold_shift_mm: dict[str, float] = field(default_factory=dict)  # gold centroid vs bore (lighting bias)
    method: str = "dark_bore"        # center estimator actually used per hole
    not_found: list[str] = field(default_factory=list)

    def mm_to_px(self, x: float, y: float) -> tuple[float, float]:
        a, b, c, d, e, f = self.affine
        return (a * x + b * y + c, d * x + e * y + f)


# ── design parsing (text-only, no pcbnew) ────────────────────────────────────
_FP_OPEN = re.compile(r"\(footprint\s+\"([^\"]+)\"")
_REF_RE = re.compile(r'\(property\s+"Reference"\s+"([^"]+)"')
_AT_RE = re.compile(r"\(at\s+(-?\d+\.?\d*)\s+(-?\d+\.?\d*)(?:\s+(-?\d+\.?\d*))?\s*\)")
_LAYER_RE = re.compile(r'\(layer\s+"([^"]+)"\)')
_DESCR_RE = re.compile(r'\(descr\s+"([^"]*)"')
_DRILL_RE = re.compile(r"\(drill\s+([\d.]+)")
_SIZE_RE = re.compile(r"\(size\s+([\d.]+)\s+([\d.]+)\)")
_EDGE_RECT_RE = re.compile(
    r"\(gr_rect\s*\(start\s+(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\)\s*"
    r"\(end\s+(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\)"
    r"[\s\S]*?layer\s+\"Edge\.Cuts\""
)


def _iter_footprint_blocks(text: str):
    for m in _FP_OPEN.finditer(text):
        start = m.start()
        depth = 0
        i = start
        while i < len(text):
            c = text[i]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    yield m.group(1), text[start:i + 1]
                    break
            i += 1


def _pad_subblock(block: str) -> str | None:
    """Return the main `(pad ...)` sub-block of a footprint.

    `MountingHole_*_Pad_Via` footprints contain several pads: the anchor
    pad plus a ring of small stitching vias — and KiCad 9 libraries
    serialise the vias FIRST, so "first pad" would report the Ø0.5 via
    drill instead of the real Ø2.5 anchor drill. Pick the pad with the
    largest drill (falling back to the first pad when none declare one).
    """
    pads: list[str] = []
    idx = block.find("(pad ")
    while idx >= 0:
        depth = 0
        j = idx
        while j < len(block):
            if block[j] == "(":
                depth += 1
            elif block[j] == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        pads.append(block[idx:j + 1] if j < len(block) else block[idx:])
        idx = block.find("(pad ", j + 1)
    if not pads:
        return None

    def drill_of(pad: str) -> float:
        m = _DRILL_RE.search(pad)
        return float(m.group(1)) if m else -1.0

    return max(pads, key=drill_of)


def get_pcb_outline(text: str) -> tuple[float, float, float, float]:
    """(x0, y0, x1, y1) of the first Edge.Cuts rectangle (min/max ordered)."""
    m = _EDGE_RECT_RE.search(text)
    if not m:
        raise ValueError("No Edge.Cuts rectangle found in board text")
    x0, y0, x1, y1 = (float(g) for g in m.groups())
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def parse_design_holes(text: str, ref_prefix: str = "H") -> dict[str, DesignHole]:
    """Parse mounting-hole footprints (ref starting with `ref_prefix`).

    The footprint's own `(at X Y)` is the FIRST `(at ...)` in its block (it
    precedes the property/pad sub-blocks). Pad drill/size come from the single
    thru-hole pad of the MountingHole footprint.
    """
    out: dict[str, DesignHole] = {}
    for library, block in _iter_footprint_blocks(text):
        ref_m = _REF_RE.search(block)
        if not ref_m:
            continue
        ref = ref_m.group(1)
        if not ref.startswith(ref_prefix):
            continue
        at = _AT_RE.search(block)        # footprint origin = first (at ...)
        layer = _LAYER_RE.search(block)
        if not (at and layer):
            continue
        descr = _DESCR_RE.search(block)
        # drill + pad size must come from INSIDE the (pad ...) sub-block — a
        # bare search would otherwise hit the Reference's font `(size 0.8 0.8)`.
        pad_txt = _pad_subblock(block)
        drill = _DRILL_RE.search(pad_txt) if pad_txt else None
        size = _SIZE_RE.search(pad_txt) if pad_txt else None
        out[ref] = DesignHole(
            ref=ref,
            x=float(at.group(1)),
            y=float(at.group(2)),
            drill_dia=float(drill.group(1)) if drill else None,
            pad_dia=min(float(size.group(1)), float(size.group(2))) if size else None,
            layer=layer.group(1),
            library=library,
            descr=descr.group(1) if descr else "",
        )
    return out


def load_holes_groundtruth(path: str | Path) -> HolesGroundTruth:
    data = yaml.safe_load(Path(path).read_text())
    meta = data.get("meta", {})
    outline = tuple(meta.get("pcb_outline_mm", [0, 0, 0, 0]))
    return HolesGroundTruth(
        holes=data.get("holes", {}),
        outline=outline,                      # type: ignore[arg-type]
        screw=str(data.get("screw", "?")),
        drill_dia=float(data.get("drill_dia_mm", 0.0)),
        pad_dia=float(data.get("pad_dia_mm", 0.0)),
        pos_tol=float(meta.get("pos_tol_mm", 0.10)),
        dia_tol=float(meta.get("dia_tol_mm", 0.10)),
        cv_tol=float(meta.get("cv_tol_mm", 0.30)),
        spacings=data.get("expected_spacings", []),
        meta=meta,
    )


# ── G: geometric check (design vs ground truth) ──────────────────────────────
def check_holes_geometric(design: dict[str, DesignHole],
                          gt: HolesGroundTruth) -> list[HoleFinding]:
    findings: list[HoleFinding] = []

    # Per-hole presence / position / diameter.
    for ref, spec in gt.holes.items():
        d = design.get(ref)
        if d is None:
            findings.append(HoleFinding(
                ref=ref, check="geometric", ok=False,
                message=f"{ref}: AUSENTE en el diseño (esperado en {spec['x']},{spec['y']})",
            ))
            continue
        ex, ey = float(spec["x"]), float(spec["y"])
        dev = math.hypot(d.x - ex, d.y - ey)
        pos_tol = gt.pos_tol_for(ref)
        pos_ok = dev <= pos_tol
        # diameter checks (drill + pad), if both sides declare them
        dia_msgs = []
        dia_ok = True
        if d.drill_dia is not None and gt.drill_dia:
            ddev = abs(d.drill_dia - gt.drill_dia)
            if ddev > gt.dia_tol_for(ref):
                dia_ok = False
                dia_msgs.append(f"taladro Ø{d.drill_dia} vs {gt.drill_dia} (Δ{ddev:.2f})")
        if d.pad_dia is not None and gt.pad_dia:
            pdev = abs(d.pad_dia - gt.pad_dia)
            if pdev > gt.dia_tol_for(ref):
                dia_ok = False
                dia_msgs.append(f"pad Ø{d.pad_dia} vs {gt.pad_dia} (Δ{pdev:.2f})")
        ok = pos_ok and dia_ok
        msg = (f"{ref}: posición y Ø correctos (Δpos={dev:.3f} mm)" if ok
               else f"{ref}: "
                    + ("posición fuera de tolerancia " if not pos_ok else "")
                    + (" · ".join(dia_msgs) if dia_msgs else ""))
        findings.append(HoleFinding(
            ref=ref, check="geometric", ok=ok, message=msg, deviation_mm=dev,
            detail=(f"diseño=({d.x},{d.y}) esperado=({ex},{ey}) "
                    f"tol={pos_tol} mm · grupo={spec.get('group','?')} · "
                    f"lib={d.library.split(':')[-1]} drill=Ø{d.drill_dia} pad=Ø{d.pad_dia}"),
        ))

    # Extra holes in the design that the ground truth doesn't list.
    for ref in design:
        if ref not in gt.holes:
            findings.append(HoleFinding(
                ref=ref, check="geometric", ok=False, severity="warning",
                message=f"{ref}: orificio en el diseño que NO está en la ground-truth",
                detail=f"diseño=({design[ref].x},{design[ref].y})",
            ))

    # Pattern spacings.
    for sp in gt.spacings:
        a, b = sp["a"], sp["b"]
        da, db = design.get(a), design.get(b)
        if not da or not db:
            continue
        axis = sp.get("axis", "x")
        got = abs((da.x - db.x) if axis == "x" else (da.y - db.y))
        want = float(sp["mm"])
        dev = abs(got - want)
        ok = dev <= gt.pos_tol * 2  # spacing combines two positions → 2× tol
        findings.append(HoleFinding(
            ref=f"{a}-{b}", check="spacing", ok=ok, deviation_mm=dev,
            message=(f"{a}-{b} separación {axis.upper()}={got:.2f} mm (esperado {want})"
                     if ok else
                     f"{a}-{b} separación {axis.upper()}={got:.2f} mm ≠ {want} (Δ{dev:.2f})"),
        ))

    return findings


# ── V: computer-vision detection on the render ───────────────────────────────
def _green_bbox(arr):
    import numpy as np
    from PIL import Image
    im = Image.fromarray(arr).convert("HSV")
    h, s, v = [np.asarray(c) for c in im.split()]
    mask = (h >= 80) & (h <= 125) & (s >= 40) & (v >= 25)
    xs = np.where(mask.any(axis=0))[0]
    ys = np.where(mask.any(axis=1))[0]
    if len(xs) == 0 or len(ys) == 0:
        raise RuntimeError("no green PCB pixels detected")
    return int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())


def _goldness(arr):
    """Score map for warm/bright copper-pad pixels (gold ring of a hole)."""
    import numpy as np
    R, G, B = (arr[:, :, i].astype(np.float32) for i in range(3))
    bright = (R + G + B) / 3.0
    warm = (R + G) / 2.0 - B
    gate = (bright > 90) & (warm > 25) & (R > 110) & (G > 80)
    return np.clip(warm, 0, None) * np.clip(bright - 60, 0, None) * gate


def _meanshift_centroid(score, cx, cy, ppm):
    """Lock onto the dominant gold blob near (cx,cy): shrink the window over a
    few iterations so neighbouring copper can't bias the centroid. Returns the
    refined (x,y) in px, or None if no gold lies near the seed."""
    import numpy as np
    H, W = score.shape
    for rad in (ppm * 2.4, ppm * 1.8, ppm * 1.5):
        x0 = max(0, int(cx - rad)); x1 = min(W, int(cx + rad) + 1)
        y0 = max(0, int(cy - rad)); y1 = min(H, int(cy + rad) + 1)
        win = score[y0:y1, x0:x1]
        m = float(win.sum())
        if m <= 0:
            return None
        yy, xx = np.mgrid[y0:y1, x0:x1]
        cx = float((xx * win).sum() / m)
        cy = float((yy * win).sum() / m)
    return (cx, cy)


def _dark_bore_centroid(bright, cx, cy, ppm, drill_dia):
    """Lighting-invariant true hole centre: centroid of the dark drilled bore
    enclosed by the gold ring. The bore is rotationally symmetric, so its
    centroid is unbiased by the directional shading that pulls a gold-ring
    centroid ~1 mm off-centre. Seeded at the gold centroid, re-centred twice."""
    import numpy as np
    H, W = bright.shape
    r = max(4.0, drill_dia / 2 * ppm * 1.6)
    for _ in range(2):
        x0 = max(0, int(cx - r)); x1 = min(W, int(cx + r) + 1)
        y0 = max(0, int(cy - r)); y1 = min(H, int(cy + r) + 1)
        sub = bright[y0:y1, x0:x1]
        yy, xx = np.mgrid[y0:y1, x0:x1]
        disk = ((xx - cx) ** 2 + (yy - cy) ** 2) <= r * r
        w = np.clip(60.0 - sub, 0, None) * disk    # darker → heavier
        m = float(w.sum())
        if m <= 0:
            return None
        cx = float((xx * w).sum() / m)
        cy = float((yy * w).sum() / m)
    return (cx, cy)


def _fit_affine(src, dst):
    """Least-squares 6-DOF affine mm->px. Returns (M 2x3, residuals px)."""
    import numpy as np
    n = len(src)
    A = np.zeros((2 * n, 6))
    b = np.zeros(2 * n)
    for i, ((xm, ym), (xp, yp)) in enumerate(zip(src, dst)):
        A[2 * i] = [xm, ym, 1, 0, 0, 0]
        A[2 * i + 1] = [0, 0, 0, xm, ym, 1]
        b[2 * i] = xp
        b[2 * i + 1] = yp
    sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    M = sol.reshape(2, 3)
    res = np.array([np.hypot(*(M @ [xm, ym, 1.0] - [xp, yp]))
                    for (xm, ym), (xp, yp) in zip(src, dst)])
    return M, res


def detect_holes_in_render(render_path: str | Path,
                           expected_mm: dict[str, tuple[float, float]],
                           outline: tuple[float, float, float, float],
                           *, side: str, mirrored: bool,
                           drill_dia_mm: float = 2.5) -> HoleDetection:
    """Detect each expected hole's true centre and fit a mm→px affine.

    Per hole: coarse green-bbox calibration seeds the location → mean-shift on
    the gold-ring score locks onto the pad → dark-bore centroid refines to the
    lighting-invariant true centre. The affine is fit on every detected hole;
    per-hole full-fit residual, leave-one-out error and the gold-vs-bore
    lighting shift are reported.
    """
    import numpy as np
    from PIL import Image

    arr = np.asarray(Image.open(render_path).convert("RGB"))
    bright = (arr[:, :, 0].astype(np.float32) + arr[:, :, 1] + arr[:, :, 2]) / 3.0
    bx0, bx1, by0, by1 = _green_bbox(arr)
    x0, y0, x1, y1 = outline
    ppm0 = ((bx1 - bx0) / (x1 - x0) + (by1 - by0) / (y1 - y0)) / 2.0

    def coarse(xm, ym):
        relx = (x1 - xm) if mirrored else (xm - x0)
        return (bx0 + relx * ppm0, by0 + (ym - y0) * ppm0)

    score = _goldness(arr)
    refs, src, dst = [], [], []
    gold_shift: dict[str, float] = {}
    not_found: list[str] = []
    for ref, (xm, ym) in expected_mm.items():
        seed = coarse(xm, ym)
        gold = _meanshift_centroid(score, seed[0], seed[1], ppm0)
        if gold is None:
            not_found.append(ref)
            continue
        bore = _dark_bore_centroid(bright, gold[0], gold[1], ppm0, drill_dia_mm)
        c = bore if bore is not None else gold     # bore is truth; gold fallback
        gold_shift[ref] = float(np.hypot(gold[0] - c[0], gold[1] - c[1]) / ppm0)
        refs.append(ref); src.append((xm, ym)); dst.append(c)

    if len(refs) < 3:
        raise RuntimeError(
            f"{render_path}: solo {len(refs)} orificios detectados (<3); "
            f"no se puede ajustar la afín. No detectados: {not_found}"
        )

    M, res = _fit_affine(src, dst)
    ppm = (np.hypot(M[0, 0], M[1, 0]) + np.hypot(M[0, 1], M[1, 1])) / 2.0

    full_resid = {refs[i]: float(res[i] / ppm) for i in range(len(refs))}
    loo = {}
    for i, ref in enumerate(refs):
        if len(refs) <= 3:
            loo[ref] = full_resid[ref]
            continue
        s2 = [src[j] for j in range(len(refs)) if j != i]
        d2 = [dst[j] for j in range(len(refs)) if j != i]
        M2, _ = _fit_affine(s2, d2)
        pred = M2 @ [src[i][0], src[i][1], 1.0]
        loo[ref] = float(np.hypot(*(pred - dst[i])) / ppm)

    return HoleDetection(
        side=side, ppm=float(ppm),
        affine=[float(v) for v in M.reshape(-1)],
        expected_mm={r: tuple(map(float, expected_mm[r])) for r in refs},
        detected_px={refs[i]: (float(dst[i][0]), float(dst[i][1])) for i in range(len(refs))},
        full_resid_mm=full_resid, loo_err_mm=loo,
        gold_shift_mm={r: round(gold_shift[r], 4) for r in refs},
        not_found=not_found,
    )


def check_holes_cv(detection: HoleDetection, gt: HolesGroundTruth) -> list[HoleFinding]:
    """Classify each detected hole by leave-one-out consistency.

    LOO error is the non-circular metric: it predicts a hole purely from the
    OTHER holes, so a misplaced hole shows mm-scale error while the rest stay
    sub-tolerance. `full_resid` (intra-render consistency) is reported too.
    """
    findings: list[HoleFinding] = []
    for ref in detection.detected_px:
        loo = detection.loo_err_mm.get(ref)
        full = detection.full_resid_mm.get(ref)
        ok = (loo is not None) and (loo <= gt.cv_tol)
        findings.append(HoleFinding(
            ref=ref, check="cv", ok=ok, deviation_mm=loo,
            message=(f"{ref}: centro coincide (LOO {loo:.3f} mm ≤ {gt.cv_tol})"
                     if ok else
                     f"{ref}: centro DESVIADO (LOO {loo:.3f} mm > {gt.cv_tol})"),
            detail=f"resid_ajuste={full:.3f} mm · LOO={loo:.3f} mm · ppm={detection.ppm:.2f}",
        ))
    for ref in detection.not_found:
        findings.append(HoleFinding(
            ref=ref, check="cv", ok=False,
            message=f"{ref}: NO detectado en el render (¿orificio ausente/obstruido?)",
        ))
    return findings


# ── D: visual diff ───────────────────────────────────────────────────────────
_PASS_RGB = (40, 200, 90)
_FAIL_RGB = (230, 50, 50)
_EXP_RGB = (255, 0, 255)     # magenta — expected centre
_DET_RGB = (0, 220, 255)     # cyan — detected centre


def _font(size: int):
    from PIL import ImageFont
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size)
    except OSError:
        return ImageFont.load_default()


def render_holes_diff(render_path: str | Path, detection: HoleDetection,
                      gt: HolesGroundTruth, out_path: str | Path) -> Path:
    """Full-board check image: expected pad+drill circle (green=PASS/red=FAIL),
    expected centre (+), detected centre (x), per-hole offset label."""
    from PIL import Image, ImageDraw

    img = Image.open(render_path).convert("RGB")
    dr = ImageDraw.Draw(img)
    ppm = detection.ppm
    pad_r = gt.pad_dia / 2 * ppm
    drill_r = gt.drill_dia / 2 * ppm
    font = _font(20)

    for ref, (xm, ym) in detection.expected_mm.items():
        ex, ey = detection.mm_to_px(xm, ym)
        loo = detection.loo_err_mm.get(ref)
        ok = (loo is not None) and (loo <= gt.cv_tol)
        col = _PASS_RGB if ok else _FAIL_RGB
        # expected pad ring + drill ring
        dr.ellipse((ex - pad_r, ey - pad_r, ex + pad_r, ey + pad_r), outline=col, width=3)
        dr.ellipse((ex - drill_r, ey - drill_r, ex + drill_r, ey + drill_r), outline=col, width=2)
        # expected centre cross (+)
        dr.line((ex - 9, ey, ex + 9, ey), fill=_EXP_RGB, width=2)
        dr.line((ex, ey - 9, ex, ey + 9), fill=_EXP_RGB, width=2)
        # detected centre (x)
        det = detection.detected_px.get(ref)
        if det:
            dx, dy = det
            dr.line((dx - 8, dy - 8, dx + 8, dy + 8), fill=_DET_RGB, width=2)
            dr.line((dx - 8, dy + 8, dx + 8, dy - 8), fill=_DET_RGB, width=2)
        tag = "PASS" if ok else "FAIL"
        label = f"{ref} {tag} {loo*1000:.0f}µm" if loo is not None else f"{ref} ?"
        dr.text((ex + pad_r + 4, ey - pad_r), label, fill=col, font=font)

    _draw_legend(dr, img.size, detection, gt, font)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return out_path


def _draw_legend(dr, size, detection, gt, font):
    w, h = size
    lines = [
        f"MOUNTING-HOLE DIFF · {detection.side} · {detection.ppm:.2f} px/mm · tol {gt.cv_tol} mm",
        "verde=PASS rojo=FAIL · + esperado(magenta) · x detectado(cian) · circulos Ø pad/taladro",
    ]
    f2 = _font(16)
    y = h - 46
    dr.rectangle((8, y - 4, 8 + 9 * max(len(s) for s in lines), y + 38), fill=(0, 0, 0))
    for i, s in enumerate(lines):
        dr.text((12, y + i * 18), s, fill=(255, 255, 255), font=f2)


def render_hole_crops(render_path: str | Path, detection: HoleDetection,
                      gt: HolesGroundTruth, out_path: str | Path,
                      *, scale: int = 6) -> Path:
    """Montage of per-hole zoom crops — the simple-to-read sign-off image."""
    from PIL import Image, ImageDraw

    base = Image.open(render_path).convert("RGB")
    ppm = detection.ppm
    pad_r = gt.pad_dia / 2 * ppm
    half = pad_r * 1.6
    refs = list(detection.expected_mm)
    cell = int(half * 2 * scale)
    cols = min(3, len(refs)) or 1
    rows = (len(refs) + cols - 1) // cols
    pad_gap = 8
    label_h = 26
    montage = Image.new("RGB", (cols * (cell + pad_gap) + pad_gap,
                                rows * (cell + label_h + pad_gap) + pad_gap),
                        (20, 20, 20))
    mdr = ImageDraw.Draw(montage)
    font = _font(16)

    for idx, ref in enumerate(refs):
        xm, ym = detection.expected_mm[ref]
        ex, ey = detection.mm_to_px(xm, ym)
        crop = base.crop((int(ex - half), int(ey - half),
                          int(ex - half) + int(half * 2), int(ey - half) + int(half * 2)))
        crop = crop.resize((cell, cell), Image.NEAREST)
        cdr = ImageDraw.Draw(crop)
        loo = detection.loo_err_mm.get(ref)
        ok = (loo is not None) and (loo <= gt.cv_tol)
        col = _PASS_RGB if ok else _FAIL_RGB
        # remap into crop coords
        def to_crop(px, py):
            return ((px - (ex - half)) * scale, (py - (ey - half)) * scale)
        cx, cy = to_crop(ex, ey)
        cdr.ellipse((cx - pad_r * scale, cy - pad_r * scale,
                     cx + pad_r * scale, cy + pad_r * scale), outline=col, width=2)
        cdr.line((cx - 12, cy, cx + 12, cy), fill=_EXP_RGB, width=2)
        cdr.line((cx, cy - 12, cx, cy + 12), fill=_EXP_RGB, width=2)
        det = detection.detected_px.get(ref)
        if det:
            dx, dy = to_crop(*det)
            cdr.line((dx - 10, dy - 10, dx + 10, dy + 10), fill=_DET_RGB, width=2)
            cdr.line((dx - 10, dy + 10, dx + 10, dy - 10), fill=_DET_RGB, width=2)
        r = idx // cols
        c = idx % cols
        ox = pad_gap + c * (cell + pad_gap)
        oy = pad_gap + r * (cell + label_h + pad_gap)
        montage.paste(crop, (ox, oy))
        tag = "PASS" if ok else "FAIL"
        txt = f"{ref}  {tag}  LOO={loo*1000:.0f}µm" if loo is not None else f"{ref}  no-detectado"
        mdr.rectangle((ox, oy + cell, ox + cell, oy + cell + label_h), fill=col)
        mdr.text((ox + 4, oy + cell + 4), txt, fill=(0, 0, 0), font=font)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    montage.save(out_path)
    return out_path


# ── orchestrator ─────────────────────────────────────────────────────────────
def verify_holes(pcb_path: str | Path, gt_path: str | Path,
                 renders: dict[str, Path], out_dir: str | Path) -> dict:
    """Run G + V + D for every render side. Returns a machine-readable report.

    `renders` maps side ("top"/"bottom") -> render/overlay PNG path. Each side
    detects the same 6 holes; the geometric check runs once (side-independent).
    """
    pcb_text = Path(pcb_path).read_text()
    design = parse_design_holes(pcb_text)
    gt = load_holes_groundtruth(gt_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    geo = check_holes_geometric(design, gt)
    expected_mm = {r: (float(s["x"]), float(s["y"])) for r, s in gt.holes.items()}

    sides_report: dict[str, dict] = {}
    for side, path in renders.items():
        if not Path(path).exists():
            sides_report[side] = {"error": f"render no encontrado: {path}"}
            continue
        det = detect_holes_in_render(
            path, expected_mm, gt.outline, side=side, mirrored=(side == "bottom"),
            drill_dia_mm=gt.drill_dia)
        cv = check_holes_cv(det, gt)
        diff_img = render_holes_diff(path, det, gt, out_dir / f"holes-diff-{side}.png")
        crops_img = render_hole_crops(path, det, gt, out_dir / f"holes-crops-{side}.png")
        sides_report[side] = {
            "ppm": round(det.ppm, 3),
            "center_method": det.method,
            "not_found": det.not_found,
            "max_full_resid_mm": round(max(det.full_resid_mm.values()), 4) if det.full_resid_mm else None,
            "max_loo_err_mm": round(max(det.loo_err_mm.values()), 4) if det.loo_err_mm else None,
            "max_gold_lighting_shift_mm": (
                round(max(det.gold_shift_mm.values()), 4) if det.gold_shift_mm else None),
            "per_hole": {
                r: {"full_resid_mm": round(det.full_resid_mm[r], 4),
                    "loo_err_mm": round(det.loo_err_mm[r], 4),
                    "gold_shift_mm": det.gold_shift_mm.get(r)}
                for r in det.detected_px
            },
            "cv_findings": [_fd(f) for f in cv],
            "diff_image": str(diff_img),
            "crops_image": str(crops_img),
        }

    geo_failed = [f for f in geo if not f.ok and f.severity == "critical"]
    cv_failed = [f for side in sides_report.values()
                 for f in side.get("cv_findings", []) if not f["ok"]]
    return {
        "screw": gt.screw, "drill_dia_mm": gt.drill_dia, "pad_dia_mm": gt.pad_dia,
        "tolerances": {"pos_mm": gt.pos_tol, "dia_mm": gt.dia_tol, "cv_mm": gt.cv_tol},
        "design_holes": {r: {"x": d.x, "y": d.y, "drill": d.drill_dia,
                             "pad": d.pad_dia, "layer": d.layer} for r, d in design.items()},
        "geometric": [_fd(f) for f in geo],
        "sides": sides_report,
        "pass": not geo_failed and not cv_failed,
        "geometric_failed": len(geo_failed),
        "cv_failed": len(cv_failed),
    }


def _fd(f: HoleFinding) -> dict:
    return {"ref": f.ref, "check": f.check, "ok": f.ok, "message": f.message,
            "deviation_mm": (round(f.deviation_mm, 4) if f.deviation_mm is not None else None),
            "severity": f.severity, "detail": f.detail}
