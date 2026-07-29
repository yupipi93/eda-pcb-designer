# AI_AGENT_PROMPT.md — briefing template for one PCB iteration

Copy the block below into a fresh agent session to run **one iteration** on a
board, filling every `<<placeholder>>`. It is self-contained: the agent needs
no prior context beyond repo access.

For the general operating protocol (hard rules, stop-and-ask criteria), the
agent must still read [`AGENTS.md`](../AGENTS.md) — this template deliberately
repeats only the essentials.

> The upstream MT1 project kept a fully-instantiated, per-version copy of this
> briefing (524 lines of board state). That works well: instantiate this
> template once per board, keep it under `projects/<board>/docs/`, and update
> it as the design evolves.

---

```markdown
# Briefing: PCB iteration for <<board-name>>

## Working directory

<<absolute path to the eda-pcb-designer repo root>> — run every command from
here, with the project venv active (`source .venv/bin/activate`).

## The task for this iteration

<<1-5 lines: what must change and why. Example: "move U3 2 mm left to clear
the mounting screw head; re-route; regenerate renders + DRC report.">>

## Mental model (read before touching anything)

- `src/pcb_designer/` — board-agnostic algorithms (the installed package).
  You rarely edit this; if you do, its 42-test suite must stay green.
- `<<config path, e.g. projects/myboard/myboard.yaml>>` — the board's single
  source of truth: geometry, placements `[x, y, rot, layer]`, pin counts,
  net numbers, routing widths. **This is your main edit surface.**
- `projects/<<board>>/tools/` — thin orchestrator scripts that bind this
  board's constants and delegate to the package. Placement changes usually
  touch the YAML (and, if the board still hard-codes constants in
  `place_components.py`, both — keep them in sync).
- `projects/<<board>>/{renders,validation,overlays,releases}/` — pipeline
  outputs, versioned `vX.Y.Z[-tag]`.

## Mandatory reading, in order

1. `AGENTS.md` (repo root) — hard rules + stop-and-ask criteria.
2. `docs/LESSONS_LEARNED.md` — load-bearing; do not violate any rule.
3. `projects/<<board>>/docs/DESIGN_STATE.md` — current state.
4. `<<config path>>` — the config you will edit.
5. <<any board-specific docs relevant to this task>>

## Pipeline (idempotent — re-run freely)

    pcb-designer validate --config <<config path>>
    pcb-designer pipeline --config <<config path>> --stages place,route,render
    pcb-designer pipeline --config <<config path>> --stages verify

Only if pinouts/nets changed: `pcb-designer schematic --config <<config path>>`
followed by the one GUI step (ask the user): KiCad → Tools → Update PCB from
Schematic.

## Pass criteria for this iteration

- DRC: 0 errors (warnings: <<policy, e.g. "silk warnings acceptable, justify
  any new one">>) — report at `projects/<<board>>/validation/`.
- Physical-verification gate passes (no mirror / pin-swap / hole findings).
- Renders regenerated and **visually inspected** — describe what you see and
  why it matches the intent before declaring done.
- <<board-specific criteria, e.g. "overlay render regenerated (release
  policy)", "IMU long axis stays parallel to PCB X">>

## Deliverables

1. Updated YAML (+ orchestrator constants if applicable) — show the diff.
2. Fresh DRC report + renders under the new version tag <<vX.Y.Z-tag>>.
3. Updated `projects/<<board>>/docs/DESIGN_STATE.md` (same turn).
4. A summary: what changed, validation results, anything that needs my input.

Do NOT run `pcb-designer fab` unless I explicitly ask for a release.
```
