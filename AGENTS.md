# Operating pcb-designer as an AI agent

This file is the entry point for an LLM/agent working on a PCB with this
toolkit. You edit the **board's YAML config** and drive the **CLI**; the
deterministic engine does the geometry. You do not place tracks, and you do not
hand-edit `.kicad_pcb` / `.kicad_sch` S-expressions for routine iterations.

## Mandatory reading, in order

1. This file.
2. [`docs/LESSONS_LEARNED.md`](docs/LESSONS_LEARNED.md) — 24 load-bearing rules.
   Breaking one produces a board that passes DRC yet crashes pcbnew on load,
   yields an empty autoroute, or ships mirrored. Non-negotiable.
3. [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) — the canonical iteration loop.
4. [`docs/CONVENTIONS.md`](docs/CONVENTIONS.md) — naming/footprint/DRC rules.
5. [`docs/CONFIG_REFERENCE.md`](docs/CONFIG_REFERENCE.md) — the YAML schema.
6. The board's own files: its YAML config (e.g. `examples/mt1.yaml`), its
   project docs under `projects/<board>/docs/`, and its orchestrator scripts
   under `projects/<board>/tools/`.

## The iteration loop

```bash
# 0. Sanity: config parses and matches the board
pcb-designer validate --config <board>.yaml

# 1. Edit the YAML (placements, geometry, nets) — this is your main edit surface.
#    If pinouts/nets changed, also update the board's build_schematic.py, then:
pcb-designer schematic --config <board>.yaml
#    (a schematic change requires the one GUI step: KiCad → Tools →
#     Update PCB from Schematic — ask the user to run it)

# 2. Apply placement + autoroute + render (idempotent, re-run freely)
pcb-designer pipeline --config <board>.yaml --stages place,route,render

# 3. Inspect: DRC report under projects/<board>/validation/, renders under
#    projects/<board>/renders/. LOOK at the renders — DRC can't see "wrong".

# 4. Physical-verification gate (anti-mirror / anti-pin-swap):
pcb-designer pipeline --config <board>.yaml --stages verify

# 5. Only when DRC is clean and verify passes:
pcb-designer fab --config <board>.yaml --version vX.Y.Z
```

## Hard rules

1. **Never write to `.kicad_pcb`/`.kicad_sch` while KiCad GUI has them open**
   — check for `~<file>.lck` first; if present, ask the user to close KiCad
   and stop.
2. **Idempotency is law**: any stage re-run must converge to the same board.
   If a script you changed stops being idempotent, that's a bug to fix first.
3. **Do not invent values** (resistor values, I²C addresses, footprints,
   pin mappings). If it isn't documented in the board's config/docs, ask the
   user and record the answer in the board's project docs.
4. **DRC + verify gate before `fab`, always.** Never emit fabrication outputs
   from a board with DRC errors or a failing physical-verification report.
5. **If a needed symbol/footprint library isn't installed, don't improvise a
   symbol** — surface it to the user with the suggested library.
6. **Keep the docs in sync in the same turn**: any change to placements,
   pinout, BOM or geometry updates the board's YAML *and* its project docs
   (design state / changelog), so the next session starts from truth.
7. **Backups & UUIDs**: the tools back up before mutating; if you must touch a
   KiCad file manually (rare, justified), never reuse a UUID.
8. Coordinates are **mm**; schematic grid 1.27 mm; footprint coords mm.

## When to stop and ask the user

- Several reasonable design options exist (e.g. LDO vs buck) and no stated
  preference — present the trade-off, don't pick silently.
- Physical-world information only the user has (enclosure dimensions, budget,
  deadlines, connector accessibility).
- The change would contradict a recorded design decision.
- Anything touching mechanical anchoring (mounting holes, connector positions)
  on a board that has already been fabricated.
- Destructive actions: deleting components, regenerating whole files, anything
  that loses UUID history.

Proceed without asking (and record the choice) for: standard passive values,
default footprints per `docs/CONVENTIONS.md`, net names following the
convention, cosmetic schematic reorganisation.

## Command reference

```bash
pcb-designer validate  --config <yaml>            # typecheck the config
pcb-designer init <name> [--template minimal|full_features] [--vendor ORG]
pcb-designer schematic --config <yaml>            # build .kicad_sch programmatically
pcb-designer place     --config <yaml>            # place + flip + DRC + renders
pcb-designer route     --config <yaml>            # freerouting + GND zone + stitches
pcb-designer render    --config <yaml>            # DIM PDF→PNG renders
pcb-designer pipeline  --config <yaml> --stages place,route,render
pcb-designer fab       --config <yaml> --version vX.Y.Z
pcb-designer gallery   projects/<board>/renders   # regenerate INDEX.md
python3 -m pcb_designer.render_overlay.cli --project-dir projects/<board> --version vX.Y.Z
```

Environment: stages `place/route/render/fab` need KiCad 9 (+ Java 21 and
`./vendor/fetch-freerouting.sh` for `route`) — see the table in
[`README.md`](README.md#system-requirements-per-stage). If the host lacks them,
use the Docker image (`make docker`), which runs the full pipeline — or, for
one-off operations without any local toolchain, the hosted **HTTP API**
(`https://pcb-designer-773810300510.europe-west1.run.app`, spec at
`GET /openapi.json`): upload a `.kicad_pcb`, get back the routed board, DRC
report, render or fab zip. See README §"HTTP API".

## Session bootstrap prompt

Paste this to start a fresh session on an existing board:

> *Read `AGENTS.md` and everything it tells you to read for board `<name>`
> (config `<path>.yaml`). Then report: (1) current design state in 1-2
> sentences per block, (2) open questions that block work, (3) your proposed
> next step with the exact files you'd touch and the validation you'd run.*

For a full per-iteration briefing template, see
[`docs/AI_AGENT_PROMPT.md`](docs/AI_AGENT_PROMPT.md).
