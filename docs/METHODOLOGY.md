# METHODOLOGY.md — Iterative PCB design pipeline

This is the canonical loop for any PCB iteration. The concrete commands and
pass criteria below use the **MT1 worked example** (`examples/mt1.yaml` +
`projects/mt1/`) — substitute your own board's config and project dir; the
loop itself is board-agnostic. It is intentionally headless +
scriptable so it can be repeated end-to-end without opening the GUI on every cycle.

Each step has an explicit pass criterion. **Do not skip a step.** Visual review
(step 6) is mandatory before commit — `verify_layout()` and DRC catch geometric
errors but cannot catch "this looks wrong" issues like body overhang into the
rocket interior, awkward connector orientation, or silkscreen collisions.

---

## 0. Pre-flight

- Activate the project venv: `source .venv/bin/activate`
  (created once with `python3 -m pip install -e .` from the repo root —
  see `docs/SETUP.md`).
- Confirm `kicad-cli` is on PATH (it should point to KiCad 9 native;
  AppImage builds have GUI issues).
- Working dir for every command below: the repo root.

> **Two equivalent entry points**: every stage can be invoked either via
> the **CLI canónico** (`pcb-designer <stage> --config examples/mt1.yaml`)
> or via the **MT1 orchestrator scripts** (`python3 projects/mt1/tools/<script>.py`).
> The CLI is the recommended path for new boards; the scripts are kept
> while constants are still hard-coded in MT1's case.

## 1. Schematic build (only if pinout / nets changed)

```bash
python3 projects/mt1/tools/build_schematic.py
# or, equivalent via CLI:
pcb-designer schematic --config examples/mt1.yaml
```

Pass criteria:
- Script prints `0 ERC errors, 0 ERC warnings`
- `mt1-pcb.kicad_sch` regenerated

If pins did NOT change, **skip this step** — re-running clobbers manual notes.

## 2. Update PCB from schematic (KiCad GUI)

Open `projects/mt1/kicad/mt1-pcb.kicad_pcb` in KiCad 9 PCB Editor:

1. `Tools → Update PCB from Schematic…`
2. Click **Update PCB**.
3. **Ctrl+S** to save.
4. Close the PCB Editor (otherwise the next script step can race on file locks).

Pass criteria: KiCad reports "OK" or only benign warnings.

Notes:
- This step removes mounting holes — they are not in the schematic. Step 3
  re-injects them.
- To inspect the back side: **Appearance panel → Presets (Ctrl+Tab) → "Back Layers"**.
  *Not* `View → Flip Board View` (that's mirror view).

## 3. Place components + render

```bash
python3 projects/mt1/tools/place_components.py
# or, equivalent via CLI:
pcb-designer place --config examples/mt1.yaml
```

What this script does, in order:
1. `verify_layout()` — sanity-checks the PLACEMENTS table BEFORE writing.
2. Backs up the current `.kicad_pcb` to `.kicad_pcb.bak5`.
3. Resizes the Edge.Cuts outline to `(90,100)..(190,130)` (100 × 30 mm).
4. Repositions anchor silk divider + ANCHOR text + title text.
5. Injects mounting holes H1–H4 (if missing) into the anchor zones.
6. For every entry in PLACEMENTS:
   - Updates the `(at X Y rot)` of that footprint.
   - If layer is `B.Cu`, recursively swaps `F.*` → `B.*` for that footprint.
7. Runs `kicad-cli pcb drc` → writes report to `validation/drc-<version>.txt`.
8. Renders top + bottom 3D views to `renders/<version>-{top,bottom}.png` (1800×900).
9. Invokes `render_dim.py` → 2D PCB-editor-style DIM renders at
   `renders/<version>-dim-{front,back}.png` (front-active and back-active,
   no flip, via custom KiCad color themes + PDF→PNG pipeline). Useful to
   inspect routing because individual traces are crisp and contrast against
   the dark theme background.

Pass criteria:
- `verify_layout()` prints **all OK** lines:
  - All footprints inside outline
  - TOP anchor strip free
  - No same-layer bbox overlaps
- `Placed: N/N` (everything found and updated)
- Renders produced (no `FAILED` lines)

Failure modes:
- `Not found in PCB: [ref, …]` → reference is in `PLACEMENTS` but not in
  schematic → either fix the typo or add it via `build_schematic.py`.
- `[WARN] non-anchor component(s) in TOP anchor strip` → move the component
  down (y >= 110).
- `[WARN] same-layer bbox overlap` → resolve collision in PLACEMENTS.

## 4. Visual verification (renders)

Open `projects/mt1/renders/<version>-top.png` and `…-bottom.png`. Verify:

**Layout zones**
- [ ] LEFT anchor x=90..100 is component-free (only H5, H6).
- [ ] RIGHT anchor x=170..190 contains only mounting holes H1..H4 (power section sits at x≈160..167, just inside the electronic zone).
- [ ] Edge.Cuts outline is one continuous 100×30 rectangle.

**Connector orientation** (long lateral edge access)
- [ ] XIAO USB-C end (= pin 1 of U5 with `rot=180`) points toward y=130 edge.
- [ ] microSD U4 pin row sits near y=130 (body extends into PCB interior or just past).
- [ ] J1 JST cable exit faces y=130 (white connector body protrudes downward).

**No overlaps**
- [ ] No two same-layer footprint silkscreens overlap.
- [ ] No footprint courtyard crosses Edge.Cuts (except intentional overhangs).
- [ ] No silk text overlaps a footprint pad.
- [ ] Title / ANCHOR labels don't clash with components.

**Trace optimization** (sanity-check)
- [ ] U2 LSM6 + decoupling caps cluster near U1 (short I²C).
- [ ] U4 microSD + C7 cluster near U5 (short SDIO).
- [ ] Buttons SW2/SW3 near U1's data pins (D0/D1).
- [ ] LEDs D1/D2 near U1's D2/D3 pins.

If any visual issue: edit `PLACEMENTS` or silkscreen repositioning, return to
step 3. Do not advance to commit until renders are clean.

## 4b. PCB-editor-style DIM renders (auto-generated by step 3)

`render_dim.py` produces two 2D plots that mimic the PCB Editor's
"Single Layer + Dim" rendering mode:

- `renders/<version>-dim-front.png` — F.Cu prominent (red traces/pads
  on dark navy), back layers visible as a dim hint.
- `renders/<version>-dim-back.png` — B.Cu prominent (cyan/light-blue
  traces on darker navy), front layers dimmed. **Not flipped** —
  silkscreen text reads mirrored, matching how KiCad shows B.Cu when
  Flip Board View is OFF.

Use these to verify routing decisions: the vector PDF→PNG pipeline
keeps traces crisp at 300 DPI, and the strong contrast makes each
signal easy to follow individually (much more than the 3D top/bottom
photorealistic render). Themes live under
`themes/dim-{front,back}.json` and are auto-installed into
`~/.config/kicad/9.0/colors/` on every script run.

## 4c. (Optional) Photorealistic overlay render

Generate a render with the actual breakout photos overlaid on top of the
KiCad render, so you can verify "how it will look with the chips on" before
ordering PCBs.

```bash
python3 src/pcb_designer/render_overlay/cli.py --version v0.1.X-tag
# → outputs go next to the source renders: projects/mt1/renders/
#   v0.1.X-tag-realistic-{top,bottom}.png
```

Inputs:
- `projects/mt1/renders/v0.1.X-tag-{top,bottom}.png`
- `projects/mt1/kicad/mt1-pcb.kicad_pcb`
- `projects/mt1/overlays/modules.yaml` (post-migration location;
  was inside the package before).

The script auto-detects the PCB outline in the render (no hardcoded
px/mm), so it works for any board geometry without reconfiguration.

> **HARD RULE — never deform the source images (factor de forma).**
> `real_size_mm` aspect MUST match the source image pixel aspect, or the
> photo (and its pins / mounting holes) is stretched. Enforced in code
> (`compositor._assert_image_aspect`, >5 % → error). To resize, scale both
> axes together; to fix pin spacing, scale uniformly + re-centre via
> `body_offset_mm` — never stretch one axis. Calibration is done from the
> mounting-hole fiducials (`calibrate_from_holes`) and the render base MUST
> be generated with `--background transparent`. Full methodology:
> **[MOUNTHOLE_OVERLAY_METHODOLOGY.md](MOUNTHOLE_OVERLAY_METHODOLOGY.md)**.

If a module image is missing, a procedural mockup is generated
automatically — useful to validate placement even before all photos
are sourced. Add `--debug` to draw magenta bboxes + anchor markers for
calibration of new modules.

See `src/pcb_designer/render_overlay/README.md` for details on adding
new modules.

## 5. Autorouting (added in v0.0.16)

```bash
python3 projects/mt1/tools/run_autorouter.py
# or, equivalent via CLI:
pcb-designer route --config examples/mt1.yaml
```

> **Module mounting holes (MH) are routing keepouts.** Place MH1–MH6
> (`MT_MountHole_M2`) at the real module-hole positions BEFORE routing, so
> freerouting routes around them (their NPTH `hole_clearance` 0.25 mm). **If
> you move a mounting hole, RE-RUN this step** — moving the hole does NOT
> reroute an existing trace, and you get a drill through a track (the MH1 vs
> `/+3V3` incident, REPORT §10.4). After routing, DRC must show zero
> `hole_clearance` of a track against an MH pad. See
> [MOUNTHOLE_OVERLAY_METHODOLOGY.md §5](MOUNTHOLE_OVERLAY_METHODOLOGY.md).

What this step does:
1. `pcbnew.LoadBoard()` reads the `.kicad_pcb`.
2. Strips all existing tracks/vias from the in-memory board
   (freerouting v2 sees pre-routed boards and exits without writing the
   SES).
3. `pcbnew.ExportSpecctraDSN()` → `mt1-pcb.dsn` (~12 KB).
4. Subprocess: `java -jar vendor/freerouting.jar -de … -do … -mp 30
   -mt 4 -dr 5` — 30 routing passes + 5 optimisation rounds, ~3-4 s.
   Output: `mt1-pcb.ses` with all the new traces + vias.
5. Reloads the board from disk, strips the (now-stale) old tracks,
   `pcbnew.ImportSpecctraSES()` adds the freshly routed segments.
6. `pcbnew.ZONE_FILLER` recomputes the GND zone polygon with thermal
   reliefs around each GND pad.
7. `pcbnew.SaveBoard()` writes the final `.kicad_pcb`.

Pass criteria:
- `Imported SES → board has N track/via items now` (N typically 60-80
  for this board).
- `Filled 1 zone(s)` (the B.Cu GND zone).
- `Saved mt1-pcb.kicad_pcb`.

Failure modes:
- `Java 21+ not found`: install `openjdk-21-jre-headless` once.
- `freerouting.jar not found`: it's in `vendor/freerouting.jar`
  (vendored — should always be present).
- `ImportSpecctraSES returned False`: usually means the SES is empty
  or malformed; check `projects/mt1/validation/freerouting.log`.

After autorouting, **re-run** `python3 projects/mt1/tools/place_components.py`
to regenerate DRC report + renders against the routed board. The
script is idempotent and now detects the existing GND zone (doesn't
overwrite the filled polygon).

```bash
# Full pipeline in one line (idempotent, ~6 s):
python3 projects/mt1/tools/place_components.py && \
    python3 projects/mt1/tools/run_autorouter.py && \
    python3 projects/mt1/tools/place_components.py

# CLI equivalent:
pcb-designer pipeline --config examples/mt1.yaml --stages place,route,render
```

## 6. DRC review

Open `validation/drc-<version>.txt`:

- `Found N violations` — read each. After autorouting (step 5):
  - `unconnected_items` should drop from ~21 to ~0-2 (only starved
    thermals where a GND pad has < 2 spokes).
  - `copper_edge_clearance`: may flag traces freerouting placed too
    close to the board edge. Mitigation: raise the copper-to-edge
    rule in `mt1-pcb.kicad_pro` and re-run the pipeline.
  - `track_dangling`: dangling stubs occasionally produced by the
    autorouter — usually 0-2.
  - `silk_*`: cosmetic, doesn't block.
  - `lib_footprint_mismatch`: benign (library cache mismatches).
- Goal at this milestone: **0 shorting_items, 0 courtyard_overlap**.
  Edge clearance + dangling can wait for a board-rule pass.

## 7. Commit

Stage only intended files:

```bash
cd <repo-root>
git status
git add projects/mt1/tools/place_components.py projects/mt1/tools/run_autorouter.py \
        projects/mt1/kicad/mt1-pcb.kicad_pcb \
        projects/mt1/renders/v0.1.X-*.png \
        examples/mt1.yaml
# Note: projects/mt1/validation/* and projects/mt1/kicad/
# *.dsn / *.ses are gitignored (regenerable artefacts).
git commit -m "feat(pcb): <one-line summary>

<detailed bullet list>"
# Do NOT push without explicit user approval — current workflow uses
# feature branches + manual PR merge.
```

## 8. Update tracking docs

After commit, update at least:
- `CHANGELOG.md` — what changed in this version.
- `DESIGN_STATE.md` — current geometry, layer counts, open questions.
- `DECISIONS.md` — only if this iteration introduced a new ADR.

---

## Anchor zones — quick reference (v0.0.10 dual anchor)

```
PCB: x=90..190, y=100..130    (100 × 30 mm)

       x=90    x=100                          x=170    x=190
y=100  ┌──────┬───────────────────────────────┬───────┐
       │ LEFT │  ELECTRONIC ZONE (70×30)      │ RIGHT │
       │ ANCH │  (XIAO, sensors, microSD,     │ ANCH  │
       │      │   UI, debug, test points)     │ (power│
       │ H5,H6│                               │  chain│
       │      │                               │  +H1..│
       │      │                               │   H4) │
y=130  └──────┴───────────────────────────────┴───────┘
                          ↓
                    JST cable + service edge
       Board axis = VERTICAL inside rocket:
       LEFT anchor and RIGHT anchor are the
       two opposite ends of the rocket's
       longitudinal axis (structural screws).
```

## Component clusters — connectivity logic

| Cluster                                | Refs                              | Net                  |
|----------------------------------------|-----------------------------------|----------------------|
| XIAO + BAT                             | U1, U5, J2                        | (assembly)           |
| I²C sensors (close to U1)              | U2 (LSM6), U3 (BMP585), C3/C5/C6  | SDA, SCL             |
| microSD (close to U5)                  | U4, C7                            | SDIO_CLK/CMD/D0      |
| UI inputs (close to U1)                | SW2, SW3                          | D0, D1               |
| UI outputs (close to U1)               | D1, R1, D2, R2                    | D2, D3               |
| Power chain (in right anchor)          | J1, F1, D3, SW1, C1               | BAT_P, BAT_SW        |
| Debug                                  | J3                                | DBG_TX, DBG_RX, DBG_5V |
| Test points                            | TP1..TP6                          | (probing)            |

Edit `placements:` in `examples/mt1.yaml` (canonical source of
truth) and mirror the change in `PLACEMENTS` of
`projects/mt1/tools/place_components.py` (transitional, while constants are
still hard-coded in the MT1 orchestrator) if a cluster needs to
move — the table is the single source of truth for component
position + layer.
