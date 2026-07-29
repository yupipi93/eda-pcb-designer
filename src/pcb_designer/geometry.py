"""PCB outline + silk geometry helpers.

Pure-function transforms of `.kicad_pcb` text. All parameters explicit
(no module-level constants) so the same helpers drive any board, not
just MT1.

Public API:
- `resize_outline(text, x0, y0, x1, y1) -> str` — rewrite the Edge.Cuts
  rect to the given corners.
- `reposition_silk(text, left_anchor_x, right_anchor_x, y0, y1, version_tag) -> str`
  — rewrite the silk anchor dividers + ANCHOR text + dynamic title
  (regen-every-run pattern — see LESSONS_LEARNED §17, §18).
- `make_title_silk(version_tag) -> str` — build the `MT1 vX.Y.Z -
  MultitecUA` title from a version tag. The descriptive suffix after
  the SemVer part (e.g. `-battery-power`) is dropped.
- `rotate_cw(point, deg) -> (x, y)` — clockwise rotation helper.

Legacy aliases (for board orchestrator scripts that still use module-locals):
- `_rotate_cw` ≡ `rotate_cw`
"""
from __future__ import annotations

import math
import re

__all__ = [
    "resize_outline",
    "reposition_silk",
    "make_title_silk",
    "rotate_cw",
    "_rotate_cw",
]


def resize_outline(text: str, x0: float, y0: float, x1: float, y1: float) -> str:
    """Rewrite the Edge.Cuts (gr_rect ...) of the PCB to span (x0,y0)..(x1,y1)."""
    rect_re = re.compile(
        r'\(gr_rect\s*\(start\s+[\d.]+\s+[\d.]+\)\s*'
        r'\(end\s+[\d.]+\s+[\d.]+\)([\s\S]*?layer\s+"Edge.Cuts"[\s\S]*?\))',
        re.MULTILINE)
    new_rect = (
        f'(gr_rect (start {x0} {y0}) (end {x1} {y1})'
        + r'\1'
    )
    text, n = rect_re.subn(new_rect, text, count=1)
    if n:
        print(f"  Edge.Cuts -> ({x0},{y0})..({x1},{y1}) "
              f"[{x1-x0:.0f} x {y1-y0:.0f} mm]")
    return text


def reposition_silk(text: str,
                    left_anchor_x: float,
                    right_anchor_x: float,
                    y0: float,
                    y1: float,
                    version_tag: str) -> str:
    """Reposition silk anchor dividers + labels for the board layout.

    Pattern: first-vertical-line targeting (LESSONS_LEARNED §17) — don't
    DETECT the dividers, REBUILD them from scratch. The title silk is
    regenerated every run from `version_tag` (LESSONS_LEARNED §18).
    """
    line_re = re.compile(
        r'\(gr_line\s*\(start\s+(\d+\.?\d*)\s+(\d+\.?\d*)\)\s*'
        r'\(end\s+(\d+\.?\d*)\s+(\d+\.?\d*)\)',
        re.MULTILINE)

    def _replace_first_vertical(match):
        sx, sy, ex, ey = match.groups()
        if sx != ex:
            return match.group(0)
        return (f'(gr_line (start {right_anchor_x} {y0}) '
                f'(end {right_anchor_x} {y1})')

    new_text, n = line_re.subn(_replace_first_vertical, text, count=1)
    if n:
        text = new_text
        print(f"  Right anchor silk divider -> x={right_anchor_x}")

    if f'(start {left_anchor_x} {y0})' not in text:
        left_divider = (
            f'\n\t(gr_line (start {left_anchor_x} {y0}) '
            f'(end {left_anchor_x} {y1})\n'
            f'\t\t(stroke (width 0.15) (type solid))\n'
            f'\t\t(layer "F.SilkS")\n'
            f'\t\t(uuid "aabbccdd-0000-4000-8000-000000000001")\n'
            f'\t)'
        )
        marker = f'(gr_line (start {right_anchor_x} {y0})'
        idx = text.find(marker)
        if idx >= 0:
            depth = 0
            i = idx
            while i < len(text):
                if text[i] == "(":
                    depth += 1
                elif text[i] == ")":
                    depth -= 1
                    if depth == 0:
                        text = text[:i+1] + left_divider + text[i+1:]
                        print(f"  Left anchor silk divider -> x={left_anchor_x}")
                        break
                i += 1

    anchor_text_re = re.compile(
        r'(\(gr_text\s+"ANCHOR"\s*\(at\s+)[\d.]+(\s+)[\d.]+(\s+\d+\))',
        re.MULTILINE)
    text, n = anchor_text_re.subn(r'\g<1>180\g<2>122\g<3>', text, count=1)
    if n:
        print("  ANCHOR text -> (180, 122) (centered in right anchor)")

    # Title silkscreen: dynamic from version_tag. Match any prior title
    # of the form "MT1 vX.Y[.Z][...] - MultitecUA" so we can rewrite on
    # every release without leaving stale text behind.
    new_title = make_title_silk(version_tag)
    title_re = re.compile(
        r'\(gr_text\s+"MT1[^"]*MultitecUA"\s*\(at\s+[\d.]+\s+[\d.]+\s+\d+\)',
        re.MULTILINE)
    text, n = title_re.subn(
        f'(gr_text "{new_title}" (at 180 113 0)', text, count=1)
    if n:
        print(f"  Title text -> ({new_title!r}) at (180, 113)")
    return text


def make_title_silk(version_tag: str) -> str:
    """Build the PCB title silk string from a version tag so each release
    self-labels its rev. Format: 'MT1 vX.Y.Z - MultitecUA'. The
    descriptive suffix after the version (e.g. '-battery-power') is
    dropped — only the SemVer-like part is kept."""
    m = re.match(r'(v\d+\.\d+(?:\.\d+)?)', version_tag)
    ver = m.group(1) if m else version_tag
    return f"MT1 {ver} - MultitecUA"


def rotate_cw(point, rot_deg):
    """Rotate `point` by `rot_deg` clockwise around origin."""
    th = math.radians(rot_deg)
    cos_t, sin_t = math.cos(th), math.sin(th)
    return (point[0]*cos_t + point[1]*sin_t,
            -point[0]*sin_t + point[1]*cos_t)


# ── Legacy aliases (for projects/<board>/tools/*.py during the transition) ──
_rotate_cw = rotate_cw
