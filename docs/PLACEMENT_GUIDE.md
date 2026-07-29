# PLACEMENT_GUIDE.md — how to write a YAML `placements` section

A practical walkthrough of designing a new board's `placements` table
for `pcb-designer place`. Complementary to `CONFIG_REFERENCE.md`
(schema) and `METHODOLOGY.md` (the higher-level 8-step pipeline).

## 1. Frame the board

Decide the board outline first. The MT1 layout uses **structural
anchors + an electronic strip + service edge**:

```
y=y0  ┌──────┬─────────────────────────────────────┬──────┐
      │ ANCH │            ELECTRONIC               │ ANCH │
      │ LEFT │                                     │ RIGHT│
y=y1  └──────┴─────────────────────────────────────┴──────┘
       ↑                                            ↑
   left_anchor_x                                right_anchor_x
```

Write the four `geometry.pcb.{x0,y0,x1,y1}` corners + the two
`geometry.anchors.{left_x,right_x}` boundaries first. Sanity check:
`x1 - x0` should match the design intent (e.g. 100 mm).

## 2. Inventory the keep-set

Make a list of every footprint that should EXIST in the final
`.kicad_pcb`. This is your `placements` key set. Everything else
(decoupling caps that the user will solder later, removed
components from a previous design iteration) gets stripped on `place`.

```yaml
placements:
  # Anchors (mounting holes)
  H1: ...
  H2: ...
  # Modules
  U1: ...
  U2: ...
```

Naming: stick to KiCad conventions. `H*` for hardware, `U*` for ICs /
modules, `J*` for connectors, `SW*` for switches, `R*/C*/L*/D*` for
passives, `TP*` for test points.

## 3. Place the structural anchors first

Mounting holes go in their final positions BEFORE any electronics.
They're the only things glued to the mechanical design and they
constrain everything else.

```yaml
placements:
  H1: [175, 105, 0, F.Cu]
  H2: [185, 105, 0, F.Cu]
  H3: [175, 125, 0, F.Cu]
  H4: [185, 125, 0, F.Cu]
```

## 4. Place the dominant module(s)

The MCU + the largest breakout. These set the bus pinout and
constrain everything that depends on them (I²C devices on the bus,
SPI peripherals, etc).

When a module is too big to fit on one side, FLIP it: drop a `B.Cu`
in the layer slot. `pcb-designer place` will auto-swap the seven
layer pairs (`LAYER_PAIRS`) and strip the 3D model block to avoid the
render-offset artifact (LESSONS_LEARNED §5).

## 5. Place dependent modules around the dominant one

Sensors on the I²C bus go next to the MCU's I²C pins. SPI peripherals
go next to the SPI bus. The microSD slot goes at the **service edge**
(y=y1 in MT1's convention) so it stays accessible after mechanical
integration.

Use rotations to align breakouts' pin rows along the dominant
direction (rocket axis, in the MT1 case). The IMU U2 on MT1 sits at
rot=90 so its 25.4 mm body lies along the PCB X (= rocket
longitudinal axis): off-axis IMU errors are minimised this way.

## 6. Place the power chain last

JST connectors, switches, passives in the divider. Constrain to the
top strip y=y0..y0+7 mm so the user-facing rails (battery in, ON/OFF
switch) sit on the same edge.

Add `pin_local_positions` for any pad row that isn't the default
1×N vertical 2.54 mm pitch. JST-PH at 2 mm pitch, SPDT slide switch
at 2 mm pitch, 0805 SMD passives at 2 mm pad pitch — all need their
override.

## 7. Iterate with renders + DRC

```bash
pcb-designer place --config examples/my-board.yaml
# emits:
#  - projects/my-board/validation/drc-vX.Y.Z.txt
#  - projects/my-board/renders/vX.Y.Z-top.png
#  - projects/my-board/renders/vX.Y.Z-bottom.png
```

Open the renders side-by-side with the layout intent. If a body
overhangs into another body's clearance, edit the YAML coordinates
and re-run.

DRC violations come in two flavours:
1. **Real**: courtyard collisions, drill clearance, edge clearance.
   Edit the YAML.
2. **Cosmetic**: silk-on-silk, refdes overlap with body. Often
   acceptable; suppress in the KiCad DRC rules or ignore.

## 8. Hand off to the autorouter

Once placement is final, `pcb-designer route` exports DSN, runs
freerouting, imports SES, adds GND stitches, runs the zone filler.
Re-runs are idempotent — see LESSONS_LEARNED §7.

If freerouting can't reach a target net, edit the placement to widen
the choke point or add manual `_seg/_route_l/_route_u` calls in your
board script before the autorouter pass.

## Worked example: MT1 v0.1.0

See [`examples/mt1.yaml`](../examples/mt1.yaml) for the complete
19-placement config that drove MT1 v0.1.0. Note in particular:

- **H5/H6** (left anchor): 5 mm in from the left edge so they don't
  collide with the y=100..107 battery strip.
- **U4** (microSD) rotated 270° so its slot ends up at y=130 (service
  edge) while its pin row sits at y=108 (interior).
- **U3** (BMP585) on **B.Cu** specifically because in v0.1.0 it
  blocks the new battery subsystem on F.Cu — moving it to bottom
  costs one extra via per I²C net but frees the entire top strip.
- **U2** (LSM6) on B.Cu at rot=90 so its 25.4 mm body axis aligns
  with the rocket's longitudinal axis.
- **J4** (proto header) at rot=90 placed in the y=100..105.88 strip
  above the XIAO — explicit pin mapping in the YAML comment.
- **Battery strip** all at y=104 so a single horizontal lane carries
  BAT_P / BAT_SW / VBAT_SENSE through the divider.

These are the kind of decisions that earn an ADR — record them in
your project's `docs/DECISIONS.md` (the MT1 board keeps its ADR log
in the upstream `multi-rocket-avionica` repo).
