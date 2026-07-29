"""Programmatic schematic generation via `kicad-sch-api`.

Board-agnostic helpers for building a `.kicad_sch` programmatically.
The per-board `build_<board>_schematic()` orchestrator stays in
`projects/mt1/tools/build_schematic.py` (or analogue for other boards) — that
function holds the board-specific layout (which symbols, which grid
coords, which nets) and uses these helpers to wire it up.

Public API:
- `GRID = 1.27` mm (KiCad standard schematic grid).
- `g(*coords) -> tuple` — snap coords to grid.
- `label_pin(sch, ref, pin_no, net_name, direction='right')` — add a wire
  stub + net label at a component pin.
- `nc_pin(sch, ref, pin_no)` — mark a pin no-connect.
- `auto_label(sch, ref, nets_directions)` — bulk apply labels to a component's
  pins. `nets_directions` is {pin_no: (net_name, direction)|None|(None,_)}.
- `add_pwr_flag(sch, position, net_name, ref_suffix)` — drop a PWR_FLAG
  symbol at `position` driving `net_name`, with `#FLG<ref_suffix>` reference.

`build_schematic_from_yaml(cfg)` is a placeholder for a fully
YAML-driven schematic build — a design exercise rather than a lift
(component layouts vary per board). MT1's hand-written
`build_slim_schematic()` in `projects/mt1/tools/build_schematic.py` is the
canonical example today.
"""
from __future__ import annotations

__all__ = [
    "GRID",
    "g",
    "label_pin",
    "nc_pin",
    "auto_label",
    "add_pwr_flag",
    "build_schematic_from_yaml",
]


GRID = 1.27


def g(*coords):
    """Snap coordinate(s) to the standard 1.27 mm schematic grid."""
    return tuple(round(c / GRID) * GRID for c in coords)


def label_pin(sch, ref: str, pin_no, net_name: str, direction: str = "right") -> None:
    """Add a 1-grid wire stub from `ref`.`pin_no` in `direction` and place
    a `net_name` label at the end of the stub.

    `sch` is a `kicad_sch_api` schematic instance. Direction is one of
    `right`, `left`, `down`, `up`. Silently no-ops if the pin is missing.
    """
    pin_pos = sch.get_component_pin_position(ref, str(pin_no))
    if pin_pos is None:
        print(f"  ! pin {pin_no} not found on {ref}")
        return
    sx, sy = pin_pos.x, pin_pos.y
    if direction == "right":
        ex, ey = sx + GRID, sy
    elif direction == "left":
        ex, ey = sx - GRID, sy
    elif direction == "down":
        ex, ey = sx, sy + GRID
    else:
        ex, ey = sx, sy - GRID
    sch.add_wire(start=(sx, sy), end=(ex, ey))
    sch.add_label(net_name, position=(ex, ey))


def nc_pin(sch, ref: str, pin_no) -> None:
    """Mark a pin as no-connect."""
    pin_pos = sch.get_component_pin_position(ref, str(pin_no))
    if pin_pos is not None:
        sch.no_connects.add(position=(pin_pos.x, pin_pos.y))


def auto_label(sch, ref: str, nets_directions: dict) -> None:
    """Bulk-apply labels to a component's pins.

    `nets_directions` is `{pin_no: (net_name, direction)|None|(None, _)}`.
    When `direction` is None, the helper picks one based on the pin's
    position relative to the component centre. When the value is None
    or `(None, _)`, the pin is marked no-connect.
    """
    comp = sch.components.get(ref)
    anchor = comp.position if comp else None
    for pin_no, val in nets_directions.items():
        if val is None or val[0] is None:
            nc_pin(sch, ref, pin_no)
            continue
        net_name, direction = val
        if direction is None and anchor is not None:
            pin_pos = sch.get_component_pin_position(ref, str(pin_no))
            if pin_pos:
                dx = pin_pos.x - anchor.x
                dy = pin_pos.y - anchor.y
                if abs(dx) >= abs(dy):
                    direction = "right" if dx >= 0 else "left"
                else:
                    direction = "down" if dy >= 0 else "up"
        label_pin(sch, ref, pin_no, net_name, direction or "right")


def add_pwr_flag(sch, position, net_name: str, ref_suffix: str) -> None:
    """Drop a `power:PWR_FLAG` symbol at `position` driving `net_name`.

    Required by KiCad ERC for every "power source" net that isn't driven
    by a regulator output. `ref_suffix` becomes the symbol reference
    (e.g. `01` → `#FLG01`).
    """
    pin_pos = g(*position)
    sch.components.add(lib_id="power:PWR_FLAG",
                       reference=f"#FLG{ref_suffix}",
                       value="PWR_FLAG", position=pin_pos)
    label_pin(sch, f"#FLG{ref_suffix}", "1", net_name, "down")


def build_schematic_from_yaml(config):
    """Build a schematic file from a ProjectConfig (TODO).

    Target API: parametric schematic build driven by the YAML config.
    Today the canonical implementation is `build_slim_schematic()` in
    `projects/mt1/tools/build_schematic.py`, hard-coded to MT1. Lifting it to a
    config-driven generator is a design exercise beyond a simple
    lift-and-shift (component placements, net assignments and PWR_FLAGs
    are MT1-specific).
    """
    raise NotImplementedError(
        "Config-driven schematic build is a follow-up; for now use the "
        "MT1 orchestrator at projects/mt1/tools/build_schematic.py:build_slim_schematic.")
