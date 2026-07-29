# CONFIG_REFERENCE.md — `pcb-designer` YAML schema

Authoritative reference for every field that a `pcb-designer` YAML
config recognises. The companion templates at
`src/pcb_designer/templates/minimal.yaml` and
`src/pcb_designer/templates/full_features.yaml` (the ones
`pcb-designer init` scaffolds from) are kept in sync with this
document.

## Top-level structure

```yaml
project:        # ProjectMeta — required
geometry:       # PcbGeometry + AnchorGeometry — required
placements:     # {ref: [x, y, rot, layer]} — required (may be empty)
pin_counts:     # {ref: int}                — optional
pad_half:       # {ref: [hx, hy]}           — optional
body_extent:    # {ref: {half, offset}}     — optional
pin_local_positions:  # {ref: [[x,y], ...]} — optional
th_footprints:  # [ref, ...]                — optional
nets:           # {numbers: {name: int}}    — optional
routing:        # Routing                   — optional (defaults applied)
```

## `project`

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | ✅ | Short slug; used as default project key and in CLI prompts. |
| `full_name` | string | – | Human-readable title; defaults to `name`. |
| `version` | string | – | Free-form version tag. Used to label fab artefacts, renders, validation reports. Recommended: SemVer prefix (`vX.Y.Z[-descriptor]`). |
| `vendor` | string | – | Organisation. Defaults to empty. |
| `kicad_project_dir` | path | – | Directory holding `.kicad_pro` (relative to repo root). |
| `kicad_pcb_file` | filename | – | `.kicad_pcb` filename within `kicad_project_dir`. |
| `kicad_sch_file` | filename | – | `.kicad_sch` filename within `kicad_project_dir`. |
| `validation_output_dir` | path | – | Where `drc-<version>.txt` and `erc-<version>.txt` land. |
| `renders_output_dir` | path | – | Where versioned PNG renders land + `latest` symlink. |
| `tools_dir` | path | – | Board orchestrator scripts run by the pipeline stages. Defaults to `projects/<name>/tools`. |
| `releases_output_dir` | path | – | Where `pcb-designer fab` writes gerbers/BOM/pos/zip. Defaults to `projects/<name>/releases`. |

## `geometry`

```yaml
geometry:
  pcb:     { x0: 0, y0: 0, x1: 100, y1: 30 }    # board rect, mm
  anchors: { left_x: 10, right_x: 80 }          # vertical silk dividers, mm
```

Defaults (if omitted) match the MT1 board: 90 → 190 mm × 100 → 130 mm board, anchors at 100 and 170 mm.

## `placements`

Maps a KiCad refdes to its target placement:

```yaml
placements:
  U1: [150.0, 124.0, 180, F.Cu]
  U2: [103.0, 127.0,  90, B.Cu]
```

- `x_mm`, `y_mm` — pin-1 position in board coordinates.
- `rot_deg` — clockwise rotation. 0 = +Y default orientation.
- `layer` — `F.Cu` (top) or `B.Cu` (bottom). The placement module
  auto-flips silk / mask / fab / paste / adhes / courtyard layers via
  `LAYER_PAIRS` when moving to B.Cu, and strips the 3D model block
  (see LESSONS_LEARNED §5).

The set of `placements` keys is also the **KEEP set** for the
non-module footprint strip pass: any footprint in the `.kicad_pcb`
whose Reference is NOT a key here gets removed (the v0.0.12
modules-only reset pattern).

## `pin_counts`

```yaml
pin_counts:
  U1: 7
  H1: 1
```

Number of pads in each footprint. Used by bbox computation. Mounting
holes count as 1. For 1×N sockets at rot=0 with 2.54 mm pitch, the
bbox is computed automatically. For non-standard layouts, see
`pin_local_positions`.

## `pad_half`

```yaml
pad_half:
  U1: [1.25, 1.25]   # 0.5 mm courtyard padding + 0.75 mm pad
  H1: [2.75, 2.75]   # M2 mounting hole with 5.5 mm courtyard
```

Half-size of one pad's courtyard, in the footprint-local frame at
rot=0 (half_X, half_Y). Used to expand the bbox of multi-pin rows.

## `body_extent`

```yaml
body_extent:
  U2:
    half:   [8.89, 12.70]   # half-extent of the breakout PCB
    offset: [7.62, 11.43]   # offset from pin 1 to body centre
```

Optional. Set for footprints whose physical body overhangs the pin
row (Adafruit breakouts, modular socket headers). The bbox used for
clearance checks combines pad bbox + body extent.

## `pin_local_positions`

```yaml
pin_local_positions:
  J1:  [[0.0, 0.0], [2.0, 0.0]]            # JST-PH 2-pin, 2 mm pitch
  R1:  [[-1.0, 0.0], [1.0, 0.0]]           # 0805, 2 mm pad pitch
```

Override the default "1×N vertical 2.54 mm pitch" pin row. Each
position is in the footprint-local frame BEFORE rotation, anchored on
pin 1.

## `th_footprints`

```yaml
th_footprints: [U1, U2, H1, H2]
```

List of refs that are through-hole. THT footprints' drill holes
consume keep-out space on BOTH layers; the placement verifier uses
this set to flag cross-layer collisions.

## `nets`

```yaml
nets:
  numbers:
    GND:      2
    "+3V3":   3
    DBG_RX:  25
```

Net numbers as assigned by KiCad after the schematic→PCB sync. Stable
across runs as long as `build_schematic.py` / `pcb-designer schematic`
isn't modified. Used by the routing module to refer to nets by
integer ID in `(segment ...)` blocks.

## `routing`

```yaml
routing:
  trace_width_signal: 0.25   # mm
  trace_width_power:  0.40   # mm
```

Defaults: 0.25 / 0.4 mm (CONVENTIONS §7). Apply to manually-emitted
`_seg/_route_l/_route_u` traces. Freerouting (`pcb-designer route`)
reads widths from the KiCad project's design rules, not from this
section.
