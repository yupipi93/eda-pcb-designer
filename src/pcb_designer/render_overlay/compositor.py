"""Orchestrate the photorealistic overlay pipeline.

Reads modules.yaml + the .kicad_pcb, calibrates the base render, then for
each visible module: prepares the image and alpha-composites it onto the
base render. Writes outputs/<version>-realistic-{top,bottom}.png.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import yaml
from PIL import Image, ImageDraw, ImageFont

from .module_overlay import ModuleSpec, render_module
from .pcb_parser import get_pcb_outline, parse_footprints
from .render_calibrator import Calibration, calibrate, calibrate_from_holes


@dataclass
class ModuleConfig:
    name: str
    refs: list[str]
    anchor_ref: str
    positioning: str                       # "bbox_center" or "anchor_offset"
    body_offset_mm: tuple[float, float]    # module-local offset, used by anchor_offset
    image_path: Path | None
    real_size_mm: tuple[float, float]
    image_rotation_deg: float
    visible_layer: str
    category: str


def _assert_image_aspect(name: str, image_path: Path | None,
                         size: list, tol: float) -> None:
    """Guard against image deformation (FASE 0 hard rule, LESSONS_LEARNED §21).

    Compares real_size_mm aspect (w/h) to the source image's pixel aspect.
    Raises if they diverge by more than `tol` (default 5 %) — that mismatch is
    exactly what stretched LSM6/BMP585 ~10-12 % on 2026-06-18. No-op if the
    image is missing (label-only module)."""
    if image_path is None or not Path(image_path).exists():
        return
    with Image.open(image_path) as im:
        iw, ih = im.size
    img_ar = iw / ih
    size_ar = float(size[0]) / float(size[1])
    dev = abs(size_ar / img_ar - 1.0)
    if dev > tol:
        raise ValueError(
            f"Module '{name}': real_size_mm {size} DEFORMA la imagen "
            f"'{Path(image_path).name}' ({iw}x{ih}). aspect imagen={img_ar:.3f} "
            f"vs real_size={size_ar:.3f} → estiramiento {dev*100:.1f}% (>{tol*100:.0f}%). "
            f"Mantén el factor de forma: para una altura {size[1]} usa "
            f"ancho≈{float(size[1])*img_ar:.3f} (o altura≈{float(size[0])/img_ar:.3f} "
            f"para ancho {size[0]}). Excepción documentada: 'allow_aspect_deviation'.")


def load_module_config(yaml_path: Path, images_dir: Path) -> list[ModuleConfig]:
    raw = yaml.safe_load(yaml_path.read_text())
    if not raw or "modules" not in raw:
        raise ValueError(f"{yaml_path} does not contain a 'modules:' key")
    out: list[ModuleConfig] = []
    for name, m in raw["modules"].items():
        refs = list(m.get("refs", []))
        if not refs:
            raise ValueError(f"Module '{name}' has no refs")
        anchor_ref = m.get("anchor_ref", refs[0])
        if anchor_ref not in refs:
            raise ValueError(
                f"Module '{name}': anchor_ref '{anchor_ref}' not in refs {refs}"
            )
        positioning = m.get("positioning", "anchor_offset")
        if positioning not in ("bbox_center", "anchor_offset"):
            raise ValueError(
                f"Module '{name}': positioning must be 'bbox_center' or "
                f"'anchor_offset' (got {positioning!r})"
            )
        body_off = m.get("body_offset_mm", [0.0, 0.0])
        if not (isinstance(body_off, list) and len(body_off) == 2):
            raise ValueError(f"Module '{name}': body_offset_mm must be [dx, dy]")
        image_rel = m.get("image")
        image_path = images_dir / image_rel if image_rel else None
        size = m.get("real_size_mm")
        if not (isinstance(size, list) and len(size) == 2):
            raise ValueError(f"Module '{name}': real_size_mm must be [w, h] in mm")
        # ── FACTOR DE FORMA: never deform the source image ──────────────────
        # real_size_mm[w,h] MUST match the source image's pixel aspect ratio,
        # or the composite stretches the photo (and its mounting holes / pins
        # land in false positions). Hard guard — see LESSONS_LEARNED §21.
        # To resize a module on screen, change BOTH w and h together (keep the
        # ratio); to fix pin spacing, scale uniformly then re-centre via
        # body_offset_mm — do NOT stretch one axis. Documented exceptions set
        # `allow_aspect_deviation: <fraction>` per module.
        _assert_image_aspect(name, image_path, size,
                             float(m.get("allow_aspect_deviation", 0.05)))
        layer = m.get("visible_layer", "F.Cu")
        if layer not in ("F.Cu", "B.Cu"):
            raise ValueError(f"Module '{name}': visible_layer must be F.Cu or B.Cu")
        out.append(ModuleConfig(
            name=name,
            refs=refs,
            anchor_ref=anchor_ref,
            positioning=positioning,
            body_offset_mm=(float(body_off[0]), float(body_off[1])),
            image_path=image_path,
            real_size_mm=(float(size[0]), float(size[1])),
            image_rotation_deg=float(m.get("image_rotation_deg", 0.0)),
            visible_layer=layer,
            category=m.get("category", "default"),
        ))
    return out


def _compute_image_center_mm(
    mod: ModuleConfig,
    footprints: dict,
) -> tuple[float, float, float]:
    """Resolve the (x_mm, y_mm, rotation_deg) where the IMAGE CENTER should
    land on the PCB."""
    x_anchor, y_anchor, rot, _layer = footprints[mod.anchor_ref]
    rad = math.radians(rot)
    dx_local, dy_local = mod.body_offset_mm
    # KiCad footprint convention (verified empirically): pad rotation matrix
    # is (cos θ, sin θ; -sin θ, cos θ) — equivalent to CCW math with +Y down.
    dx_world = math.cos(rad) * dx_local + math.sin(rad) * dy_local
    dy_world = -math.sin(rad) * dx_local + math.cos(rad) * dy_local

    if mod.positioning == "bbox_center":
        xs = [footprints[r][0] for r in mod.refs if r in footprints]
        ys = [footprints[r][1] for r in mod.refs if r in footprints]
        if not xs or not ys:
            return (x_anchor, y_anchor, rot)
        cx = (min(xs) + max(xs)) / 2
        cy = (min(ys) + max(ys)) / 2
        # body_offset_mm (rotated to world) corrects the bbox-of-anchors center
        # for cases where the body center is offset from the anchor-position
        # bbox (e.g., XIAO whose paired sockets are at the pin 1 / top of the
        # body, not at the body Y center — needs +half_pin_row_span in local Y).
        return (cx + dx_world, cy + dy_world, rot)

    # anchor_offset: image center is at anchor + body_offset rotated to world.
    return (x_anchor + dx_world, y_anchor + dy_world, rot)


def _draw_debug(
    base: Image.Image,
    calib: Calibration,
    module: ModuleConfig,
    px_xy: tuple[int, int],
) -> None:
    draw = ImageDraw.Draw(base)
    w_px, h_px = calib.mm_to_px_size(*module.real_size_mm)
    x, y = px_xy
    half_w, half_h = w_px // 2, h_px // 2
    draw.rectangle(
        (x - half_w, y - half_h, x + half_w, y + half_h),
        outline=(255, 0, 255, 255),
        width=2,
    )
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 14)
    except OSError:
        font = ImageFont.load_default()
    draw.text((x - half_w, y - half_h - 18), module.name,
              fill=(255, 0, 255, 255), font=font)
    draw.ellipse((x - 4, y - 4, x + 4, y + 4),
                 outline=(255, 255, 0, 255), width=2)


def compose_side(
    side: str,                              # "top" or "bottom"
    base_render_path: Path,
    pcb_path: Path,
    modules: Iterable[ModuleConfig],
    output_path: Path,
    *,
    debug: bool = False,
    annotate: bool = True,
    annotation_categories: tuple[str, ...] = ("pcb", "anchors", "holes",
                                              "modules", "pins"),
    calibration: str = "mounting_holes",
) -> dict:
    if side not in ("top", "bottom"):
        raise ValueError(f"side must be 'top' or 'bottom' (got {side!r})")
    if not base_render_path.exists():
        raise FileNotFoundError(f"Base render not found: {base_render_path}")

    pcb_outline = get_pcb_outline(pcb_path)
    footprints = parse_footprints(pcb_path)
    base = Image.open(base_render_path).convert("RGBA")

    mirrored = (side == "bottom")
    if calibration == "mounting_holes":
        # Precise fiducial calibration: fit the mm→px affine to the detected
        # mounting-hole centres. Falls back to green-bbox if <4 holes (older
        # boards). See render_calibrator.calibrate_from_holes (FASE 2).
        holes_mm = {ref: (fp[0], fp[1]) for ref, fp in footprints.items()
                    if ref.startswith("H")}
        if len(holes_mm) >= 4:
            calib = calibrate_from_holes(base_render_path, pcb_outline, holes_mm,
                                         mirrored_x=mirrored)
        else:
            calib = calibrate(base_render_path, pcb_outline, mirrored_x=mirrored)
    else:
        calib = calibrate(base_render_path, pcb_outline, mirrored_x=mirrored)

    target_layer = "F.Cu" if side == "top" else "B.Cu"

    rendered = 0
    skipped: list[str] = []

    for mod in modules:
        if mod.visible_layer != target_layer:
            continue
        if mod.anchor_ref not in footprints:
            skipped.append(f"{mod.name} (anchor_ref {mod.anchor_ref} not in PCB)")
            continue
        # Skip the procedural mockup when no real photo exists. The
        # annotation pass below still draws the green bbox + label, so
        # the user knows where the part lives without us pretending the
        # body looks like a generic block. To restore the mockup for a
        # given module, drop an image into <project>/overlays/component-images/
        # and point `image:` at it in modules.yaml.
        if mod.image_path is None or not mod.image_path.exists():
            skipped.append(f"{mod.name} (no image; label only)")
            continue
        x_mm, y_mm, rot_deg = _compute_image_center_mm(mod, footprints)
        canvas, (cx, cy) = render_module(
            ModuleSpec(
                name=mod.name,
                image_path=mod.image_path,
                real_size_mm=mod.real_size_mm,
                image_rotation_deg=mod.image_rotation_deg,
                visible_layer=mod.visible_layer,
                category=mod.category,
            ),
            pcb_rotation_deg=rot_deg,
            calib=calib,
        )
        px_xy = calib.mm_to_px(x_mm, y_mm)
        paste_xy = (px_xy[0] - cx, px_xy[1] - cy)
        base.alpha_composite(canvas, dest=paste_xy)
        if debug:
            _draw_debug(base, calib, mod, px_xy)
        rendered += 1

    if annotate:
        # Local import to keep the static-analysis-friendly module graph
        # free of circular dependencies (annotations imports compositor too).
        from .annotations import draw_annotations
        modules_list = list(modules) if not isinstance(modules, list) else modules
        draw_annotations(
            base, calib, pcb_outline, footprints, modules_list,
            side=side, categories=annotation_categories,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    base.save(output_path)

    return {
        "side": side,
        "rendered": rendered,
        "skipped": skipped,
        "px_per_mm": calib.px_per_mm,
        "calibration": calib.method,
        "pcb_outline_mm": pcb_outline,
        "output": output_path,
    }
