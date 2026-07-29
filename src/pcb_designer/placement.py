"""Component placement: place + flip footprints to target (x, y, rot, layer).

Lift-and-shift from `projects/mt1/tools/place_components.py` — semantics preserved
byte-identical. The only API change: `place_and_flip` now takes the
placements dict as an explicit parameter instead of relying on a
module-level constant, making the helper board-agnostic.

Public API:
- `LAYER_PAIRS` — the 7 F.* / B.* layer-tag pairs auto-swapped on flip
  (LESSONS_LEARNED §4).
- `flip_to_back(block) -> str` — swap F.* → B.* + strip 3D models
  (LESSONS_LEARNED §5).
- `flip_to_front(block) -> str` — swap B.* → F.* (model strip not needed
  for back-to-front).
- `place_and_flip(text, placements) -> (text, updated_count, not_found_refs)`
  — for each ref in `placements`, find its (footprint ...) block, rewrite
  the (at x y rot) line, and if the target layer differs from current,
  flip via LAYER_PAIRS.

Legacy aliases for the board orchestrator scripts (projects/<board>/tools/):
- `_LAYER_PAIRS` ≡ `LAYER_PAIRS`
- `_flip_footprint_block_to_back` ≡ `flip_to_back`
- `_flip_footprint_block_to_front` ≡ `flip_to_front`
"""
from __future__ import annotations

import re

from pcb_designer.kicad_pcb_io import (
    extract_footprint_block,
    strip_3d_model_blocks,
)

__all__ = [
    "LAYER_PAIRS",
    "flip_to_back",
    "flip_to_front",
    "place_and_flip",
    "_LAYER_PAIRS",
    "_flip_footprint_block_to_back",
    "_flip_footprint_block_to_front",
]


LAYER_PAIRS: list[tuple[str, str]] = [
    ('"F.Cu"',     '"B.Cu"'),
    ('"F.Paste"',  '"B.Paste"'),
    ('"F.Mask"',   '"B.Mask"'),
    ('"F.SilkS"',  '"B.SilkS"'),
    ('"F.Fab"',    '"B.Fab"'),
    ('"F.Adhes"',  '"B.Adhes"'),
    ('"F.CrtYd"',  '"B.CrtYd"'),
]


# Footprint-local geometry that must be X-mirrored on a real flip. The
# footprint's OWN top-level (at x y rot) is in BOARD coords and is preserved
# (it's the placement); everything after it is footprint-local.
_AT_RE = re.compile(r'(\(at\s+)(-?[\d.]+)(\s+-?[\d.]+(?:\s+-?[\d.]+)?\s*\))')
_PT_RE = re.compile(r'(\((?:start|end|center|mid)\s+)(-?[\d.]+)(\s+-?[\d.]+\))')


def _mirror_local_x(block: str) -> str:
    """Negate the X of every footprint-LOCAL coordinate (pads + graphics +
    text), leaving the footprint's own placement (first `(at ...)`) intact.

    This is the geometry half of a genuine KiCad flip — a pure layer-tag swap
    (the old behaviour) left every footprint on B.Cu as the MIRROR IMAGE of a
    correctly-flipped one (see POST-MORTEM-001 / ERRATA-001 §9). For a single
    pad column (lx=0) this is a no-op on the copper but still mirrors the silk.
    """
    first_at = _AT_RE.search(block)
    head_end = first_at.end() if first_at else 0
    head, body = block[:head_end], block[head_end:]

    def _neg_at(m):
        return f"{m.group(1)}{_fmt(-float(m.group(2)))}{m.group(3)}"

    def _neg_pt(m):
        return f"{m.group(1)}{_fmt(-float(m.group(2)))}{m.group(3)}"

    body = _AT_RE.sub(_neg_at, body)
    body = _PT_RE.sub(_neg_pt, body)
    return head + body


def _fmt(v: float) -> str:
    """Format a mirrored coordinate without trailing-zero noise (0.0 → 0)."""
    if v == 0:
        return "0"
    s = f"{v:.6f}".rstrip("0").rstrip(".")
    return s


def _set_text_mirror(block: str, mirror: bool) -> str:
    """Add/remove `(justify mirror)` on every text `(effects ...)` so the
    silk reads correctly from the flipped side."""
    out = []
    i = 0
    while True:
        idx = block.find("(effects", i)
        if idx < 0:
            out.append(block[i:])
            break
        out.append(block[i:idx])
        depth = 0
        j = idx
        while j < len(block):
            if block[j] == "(":
                depth += 1
            elif block[j] == ")":
                depth -= 1
                if depth == 0:
                    j += 1
                    break
            j += 1
        eff = block[idx:j]
        has_justify = "(justify" in eff
        has_mirror = "mirror" in eff
        if mirror and not has_mirror:
            if has_justify:
                eff = re.sub(r"\(justify\b([^)]*)\)",
                             lambda m: f"(justify{m.group(1)} mirror)", eff, count=1)
            else:  # insert a justify clause just before the closing paren
                eff = eff[:-1].rstrip() + "\n\t\t\t(justify mirror)\n\t\t)"
        elif not mirror and has_mirror:
            eff = re.sub(r"\s*mirror", "", eff)
            eff = re.sub(r"\(justify\s*\)", "", eff)
        out.append(eff)
        i = j
    return "".join(out)


def flip_to_back(block: str) -> str:
    """Genuine flip of a footprint block from F.* to B.* layers.

    A real KiCad flip = (1) swap the 7 layer-tag pairs, (2) mirror every
    footprint-local X coordinate (pads + graphics + text), (3) mirror the text
    so the silk reads from the back, (4) strip 3D models (they misalign on the
    auto-flipped render — LESSONS_LEARNED §5). Steps (2)+(3) are what the old
    layer-tag-only swap omitted, which is why every B.Cu module shipped as a
    mirror image (POST-MORTEM-001). For arbitrary/custom footprints,
    `pcbnew.Footprint.Flip()` remains the authoritative implementation.
    """
    for f, b in LAYER_PAIRS:
        block = block.replace(f, b)
    block = _mirror_local_x(block)
    block = _set_text_mirror(block, mirror=True)
    block = strip_3d_model_blocks(block)
    return block


def flip_to_front(block: str) -> str:
    """Inverse of `flip_to_back`: B.* → F.* + un-mirror geometry and text."""
    for f, b in LAYER_PAIRS:
        block = block.replace(b, f)
    block = _mirror_local_x(block)
    block = _set_text_mirror(block, mirror=False)
    return block


def place_and_flip(text: str, placements: dict) -> tuple:
    """Place + flip every ref in `placements` within the given .kicad_pcb text.

    `placements` maps ref → (x_mm, y_mm, rot_deg, layer). For each ref:
    1. Find its (footprint ...) block via the Reference property.
    2. Rewrite its (at x y rot) line.
    3. If the target layer differs from current, flip via LAYER_PAIRS.
    4. If target is B.Cu, also strip (model "...") sub-blocks every run
       (idempotent, avoids the off-by-20mm render misalignment from
       LESSONS_LEARNED §5).

    Returns (new_text, updated_count, not_found_refs).
    """
    updated = 0
    not_found = []

    prop_re_template = r'\(property\s+"Reference"\s+"{}"'
    refs_with_pos = []
    for ref in placements:
        m = re.search(prop_re_template.format(re.escape(ref)), text, re.MULTILINE)
        if m:
            refs_with_pos.append((m.start(), ref))
        else:
            not_found.append(ref)
    refs_with_pos.sort(reverse=True)

    at_re = re.compile(
        r'\(at\s+(-?[\d.]+)\s+(-?[\d.]+)(?:\s+(-?[\d.]+))?\s*\)')

    layer_re = re.compile(r'\(layer\s+"(F\.Cu|B\.Cu)"\)')

    for prop_pos, ref in refs_with_pos:
        x, y, rot, target_layer = placements[ref]

        fp_start, fp_end = extract_footprint_block(text, prop_pos)
        if fp_start is None:
            continue
        fp_block = text[fp_start:fp_end]

        new_block = at_re.sub(f"(at {x} {y} {rot})", fp_block, count=1)

        m = layer_re.search(new_block)
        current_layer = m.group(1) if m else "F.Cu"
        if target_layer == "B.Cu" and current_layer == "F.Cu":
            new_block = flip_to_back(new_block)
        elif target_layer == "F.Cu" and current_layer == "B.Cu":
            new_block = flip_to_front(new_block)
        # Strip 3D models from B.Cu footprints every run (idempotent) — the
        # auto-flip in KiCad's renderer misaligns the model for layer-swapped
        # footprints, so we just don't render them on the back side.
        if target_layer == "B.Cu":
            new_block = strip_3d_model_blocks(new_block)

        text = text[:fp_start] + new_block + text[fp_end:]
        updated += 1

    return text, updated, not_found


# ── Legacy aliases (for projects/<board>/tools/*.py during the transition) ──
_LAYER_PAIRS = LAYER_PAIRS
_flip_footprint_block_to_back = flip_to_back
_flip_footprint_block_to_front = flip_to_front
