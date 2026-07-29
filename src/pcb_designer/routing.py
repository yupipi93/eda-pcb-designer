"""Manual routing helpers: segment generators + L/U-shaped routes.

Lift-and-shift from `projects/mt1/tools/place_components.py`. All board-agnostic.
GND zone, stitch vias and signal routes for a specific board live in
the board's script (e.g. `projects/mt1/tools/place_components.py:inject_routing`).

Public API:
- `DEFAULT_TRACE_WIDTH_SIGNAL` = 0.25 mm
- `DEFAULT_TRACE_WIDTH_POWER` = 0.4 mm
- `segment(x1, y1, x2, y2, layer, net, width)` — single (segment ...)
  S-expression. UUID is a deterministic hash of the coords (so two runs
  with the same inputs produce the same UUID when PYTHONHASHSEED is fixed).
- `route_l(x1, y1, x2, y2, layer, net, *, vertical_first=True, width=...)`
  — L-shaped two-segment route. Single segment if already on same row/column.
- `route_u(x1, y1, x2, y2, corridor_x, layer, net, *, width=...)` —
  U-shaped three-segment route via a corridor.

Legacy aliases for the board orchestrator scripts (projects/<board>/tools/):
- `_seg`, `_route_l`, `_route_u`
"""
from __future__ import annotations

__all__ = [
    "DEFAULT_TRACE_WIDTH_SIGNAL",
    "DEFAULT_TRACE_WIDTH_POWER",
    "segment",
    "route_l",
    "route_u",
    "_seg",
    "_route_l",
    "_route_u",
]


DEFAULT_TRACE_WIDTH_SIGNAL = 0.25
DEFAULT_TRACE_WIDTH_POWER = 0.4


def segment(x1, y1, x2, y2, layer, net, width=DEFAULT_TRACE_WIDTH_SIGNAL):
    """Generate a (segment ...) S-expression for one PCB trace."""
    uuid = f"trace{abs(hash((x1, y1, x2, y2, layer, net))) % 10**12:012d}"
    return (
        f'\t(segment\n'
        f'\t\t(start {x1} {y1})\n'
        f'\t\t(end {x2} {y2})\n'
        f'\t\t(width {width})\n'
        f'\t\t(layer "{layer}")\n'
        f'\t\t(net {net})\n'
        f'\t\t(uuid "{uuid}-trc")\n'
        f'\t)'
    )


def route_l(x1, y1, x2, y2, layer, net, *, vertical_first=True,
            width=DEFAULT_TRACE_WIDTH_SIGNAL) -> list:
    """Generate an L-shaped two-segment route from (x1,y1) to (x2,y2)."""
    if abs(x1 - x2) < 0.01 or abs(y1 - y2) < 0.01:
        # Already on the same row/column — single segment.
        return [segment(x1, y1, x2, y2, layer, net, width)]
    if vertical_first:
        return [
            segment(x1, y1, x1, y2, layer, net, width),
            segment(x1, y2, x2, y2, layer, net, width),
        ]
    return [
        segment(x1, y1, x2, y1, layer, net, width),
        segment(x2, y1, x2, y2, layer, net, width),
    ]


def route_u(x1, y1, x2, y2, corridor_x, layer, net, *,
            width=DEFAULT_TRACE_WIDTH_SIGNAL) -> list:
    """U-shaped route: (x1,y1) → (corridor_x, y1) → (corridor_x, y2) → (x2, y2)."""
    return [
        segment(x1, y1, corridor_x, y1, layer, net, width),
        segment(corridor_x, y1, corridor_x, y2, layer, net, width),
        segment(corridor_x, y2, x2, y2, layer, net, width),
    ]


# ── Legacy aliases (for projects/<board>/tools/*.py during the transition) ──
_seg = segment
_route_l = route_l
_route_u = route_u
