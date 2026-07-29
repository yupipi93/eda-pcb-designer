"""S-expression I/O primitives for KiCad PCB files (`.kicad_pcb`).

Bedrock primitives — every higher-level helper (`placement`, `routing`,
`injection`, `geometry`) walks a `.kicad_pcb` file as text using a
*depth-aware* paren walker. Naive regex matching breaks on nested
S-expressions, especially inside `(footprint ...)` blocks where 3D-model
paths and sub-blocks add multiple paren levels.

Public API:
- `extract_footprint_block(text, ref_pos) -> (start, end)` — depth-aware
  walker that returns the byte offsets of the `(footprint ...)` block
  whose `(property "Reference" ...)` sits at `ref_pos`.
- `strip_3d_model_blocks(block) -> str` — remove every `(model "..." ...)`
  sub-block from a footprint block. Required when flipping to B.Cu
  (see LESSONS_LEARNED.md §5).
- `remove_tiny_segments(text, max_len_mm) -> (text, removed_count)` —
  strip routing segments shorter than `max_len_mm`. Used as
  post-freerouting cleanup. Depth-aware (see LESSONS_LEARNED.md §2).

Internal aliases (legacy underscore-prefixed names, kept for
backwards-compatibility with the board orchestrator scripts (projects/<board>/tools/) scripts during the
transition):
- `_extract_footprint_block` ≡ `extract_footprint_block`
- `_strip_3d_model_blocks` ≡ `strip_3d_model_blocks`
"""
from __future__ import annotations

import math
import re

__all__ = [
    "extract_footprint_block",
    "strip_3d_model_blocks",
    "remove_tiny_segments",
    "_extract_footprint_block",
    "_strip_3d_model_blocks",
]


def extract_footprint_block(text: str, ref_pos: int) -> tuple:
    """Return (start, end) offsets of the (footprint ...) block whose
    (property "Reference" ...) is at position ref_pos."""
    start = text.rfind("(footprint", 0, ref_pos)
    if start < 0:
        return None, None
    depth = 0
    i = start
    while i < len(text):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return start, i + 1
        i += 1
    return None, None


def strip_3d_model_blocks(block: str) -> str:
    """Remove every (model "..." ...) sub-block from a footprint block.

    Why: when a footprint is flipped to B.Cu via simple layer-tag swap (no
    geometry mirror), KiCad's renderer auto-flips the model in a way that
    leaves the 3D model OFFSET from the pads (the model's pin row ends up
    20+ mm away from the actual pad row in the rendered image — visible
    as a "floating socket header" artifact off-PCB in the bottom render).
    The pads themselves remain correctly placed; only the 3D model misaligns.

    Rather than dive into model rotate/offset hacks per part, just strip the
    model entries from B.Cu footprints. The pads + silkscreen are all you
    need to validate placement on the back side, and the overlay render
    (src/pcb_designer/render_overlay/) shows the realistic breakout photo anyway.
    """
    out_chunks = []
    i = 0
    while i < len(block):
        idx = block.find("(model ", i)
        if idx < 0:
            out_chunks.append(block[i:])
            break
        out_chunks.append(block[i:idx])
        # Find the closing paren of this (model ...) sub-block.
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
        # Also consume any trailing whitespace + newline so the diff stays tidy.
        while j < len(block) and block[j] in " \t":
            j += 1
        if j < len(block) and block[j] == "\n":
            j += 1
        i = j
    return "".join(out_chunks)


def remove_tiny_segments(text: str, max_len_mm: float = 0.1) -> tuple:
    """Strip any (segment ...) whose Euclidean length is below max_len_mm.

    freerouting occasionally leaves <0.1mm dangling stubs at track joins
    (e.g. the /LED2 80µm stub at (151.75, 100.41) in v0.0.16). These
    raise `track_dangling` warnings and never serve electrical purpose.

    Uses a depth-aware S-expression walker (segments contain nested parens
    for (start ...), (end ...), (width ...), (layer ...), (net ...), so
    a naive non-greedy regex would cut them in half).
    """
    head_re = re.compile(
        r'\(segment\s+\(start\s+(-?[\d.]+)\s+(-?[\d.]+)\)\s+'
        r'\(end\s+(-?[\d.]+)\s+(-?[\d.]+)\)')

    removed = 0
    out = []
    i = 0
    while i < len(text):
        m = head_re.search(text, i)
        if not m:
            out.append(text[i:])
            break
        out.append(text[i:m.start()])
        # Walk forward to the matching closing paren of this (segment ...).
        depth = 0
        j = m.start()
        while j < len(text):
            if text[j] == '(':
                depth += 1
            elif text[j] == ')':
                depth -= 1
                if depth == 0:
                    j += 1
                    break
            j += 1
        # Optional trailing whitespace + newline → eat for tidy diff.
        end = j
        while end < len(text) and text[end] in " \t":
            end += 1
        if end < len(text) and text[end] == "\n":
            end += 1

        x1, y1, x2, y2 = map(float, m.group(1, 2, 3, 4))
        if math.hypot(x2 - x1, y2 - y1) < max_len_mm:
            removed += 1
            # Don't append the segment block; consume the leading whitespace
            # of the (segment line if it landed on its own line.
            # (Whitespace before m.start() is already in out via [i:m.start()];
            # trim trailing whitespace from out so the file stays tidy.)
            if out and out[-1].endswith("\t"):
                out[-1] = out[-1].rstrip("\t")
            if out and out[-1].endswith("\n\t"):
                out[-1] = out[-1].rstrip("\t")
        else:
            out.append(text[m.start():end])
        i = end

    return "".join(out), removed


# ── Legacy underscore-prefixed aliases (for projects/<board>/tools/*.py scripts) ──
_extract_footprint_block = extract_footprint_block
_strip_3d_model_blocks = strip_3d_model_blocks
