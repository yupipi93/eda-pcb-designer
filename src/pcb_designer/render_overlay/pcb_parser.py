"""Parse mt1-pcb.kicad_pcb to extract footprint positions, rotations, and layer.

Returns a dict {ref: (x_mm, y_mm, rot_deg, layer)} for every named footprint.
Also exposes get_pcb_outline() which returns the Edge.Cuts rectangle bounds.
"""
from __future__ import annotations

import re
from pathlib import Path

_FP_OPEN = re.compile(r"\(footprint\s+\"[^\"]+\"")
_AT_RE = re.compile(r"\(at\s+(-?\d+\.?\d*)\s+(-?\d+\.?\d*)(?:\s+(-?\d+\.?\d*))?\s*\)")
_REF_RE = re.compile(r'\(property\s+"Reference"\s+"([^"]+)"')
_LAYER_RE = re.compile(r'\(layer\s+"([FB]\.Cu)"')
_EDGE_RECT_RE = re.compile(
    r"\(gr_rect\s*\(start\s+(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\)\s*"
    r"\(end\s+(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\)"
    r"[\s\S]*?layer\s+\"Edge\.Cuts\""
)


def _iter_footprint_blocks(text: str):
    """Yield (start, end) offsets of each top-level (footprint ...) block."""
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
                    yield start, i + 1
                    break
            i += 1


def parse_footprints(kicad_pcb_path: Path) -> dict[str, tuple[float, float, float, str]]:
    """Return {ref: (x_mm, y_mm, rot_deg, layer)} for every footprint."""
    text = Path(kicad_pcb_path).read_text()
    out: dict[str, tuple[float, float, float, str]] = {}
    for start, end in _iter_footprint_blocks(text):
        block = text[start:end]
        # The footprint's (at X Y rot) appears BEFORE the first nested
        # (property ...) — take the first match in the block.
        at = _AT_RE.search(block)
        ref = _REF_RE.search(block)
        layer = _LAYER_RE.search(block)
        if not (at and ref and layer):
            continue
        x = float(at.group(1))
        y = float(at.group(2))
        rot = float(at.group(3)) if at.group(3) else 0.0
        out[ref.group(1)] = (x, y, rot, layer.group(1))
    return out


def get_pcb_outline(kicad_pcb_path: Path) -> tuple[float, float, float, float]:
    """Return (x0, y0, x1, y1) of the first Edge.Cuts rectangle."""
    text = Path(kicad_pcb_path).read_text()
    m = _EDGE_RECT_RE.search(text)
    if not m:
        raise ValueError(f"No Edge.Cuts rectangle found in {kicad_pcb_path}")
    x0, y0, x1, y1 = (float(g) for g in m.groups())
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
