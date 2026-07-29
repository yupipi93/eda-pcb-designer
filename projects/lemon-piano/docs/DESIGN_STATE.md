# DESIGN_STATE.md — Lemon Piano V5.5 Board

**Current version: v0.1.0 — released to fab package, all gates green.**
(2026-07-30)

## Block status

| Block | State |
|---|---|
| Nano socket (U1/U2, 2×15) | ✅ placed, USB-west, all 23 used pins netted, 7 NC by design |
| Power-entry filter (J1→D1→D2→C1‖C2→L1→C3‖C4) | ✅ placed east block, routed, order verified on render |
| Keyboard (R1–R7 pull-ups + J2 header) | ✅ B.Cu pull-ups under the Nano, header above A-pins, labelled |
| LED bar (D3–D12 + R8–R17) | ✅ south strip, ascending 1→10, series R on B.Cu |
| UI (BUZ1 D13, SW1 SENS+ D12, SW2 SENS− A7 + R18) | ✅ placed + routed |
| GND | ✅ B.Cu zone, solid connect on all GND pads, island-healing guard |
| Mounting (H1/H2, M2) | ✅ (95,115) / (185,115), symmetric about x=140 |
| Schematic | ✅ mirrors PCB (45 symbols incl. 3 PWR_FLAGs), ERC 0/0 |
| Fab package | ✅ `releases/v0.1.0/lemon-piano-v0.1.0-fab.zip` (14 files) |

## Verification snapshot (v0.1.0)

| Gate | Result |
|---|---|
| Cloud `/drc` | **0 errors, 0 warnings, 0 unconnected** (`validation/drc-v0.1.0.json`) |
| ERC | 0 errors, 0 warnings (`validation/erc-v0.1.0.txt`) |
| `verify_placement` (C1 chirality, C2 flip, C3 pad↔net↔function, C4 net intent) | ALL PASS |
| `verify_holes` (geometric: pos/Ø/pattern) | PASS (vision N/A: 2 holes < 3, ADR-012) |
| `geometry_gate` (outline, symmetry, service edges, USB corridor, copper per net, courtyards) | ALL PASS |
| Render inspection (top+bottom) | PASS (filter order, socket rows, labels, bar, zone continuity) |
| Idempotency | build_board ×3 byte-identical; build_schematic ×3 byte-identical |

## Iteration history

| Version | What changed | DRC (err/warn/unconn) | Verdict |
|---|---|---|---|
| v0.0.1 | first placement (no routing) | 0 / 44 / 81 | placement fits; silk collisions; renders verified |
| v0.0.2 | first freerouting pass + naive width post-pass | 12 / 44 / 9 | starved thermals on SMD GND pads; widening broke clearances |
| v0.0.3 | solid zone-connect on all GND pads; clearance-aware widener | 0 / 44 / 0 | electrically clean; silk collisions remain |
| v0.0.4 | silk labels/refs repositioned, SW refs hidden | 0 / 25 / 0 | all remaining warnings = text height < 0.8 |
| v0.0.5 | all silk text ≥ 0.8 mm | 0 / 4 / 0 | title/BUZ1 silk clashes + 1 dangling freerouting spur |
| v0.0.6 | title split, BUZ1 ref inside circle, dangling-spur cleaner | **0 / 0 / 0** | fully clean; all gates pass |
| v0.1.0 | release: schematic+ERC, gates wired into pipeline, island-healing guard, /fab | **0 / 0 / 0** | RELEASED |

(One v0.1.0 route attempt produced a GND-zone island — caught by the new
DRC gate, fixed by the automatic island healing, re-run clean. Kept in
`validation/` history.)

## How to regenerate

```bash
# full iteration (build → /place → /route → post → /drc → /render → gates):
./projects/lemon-piano/tools/cloud_pipeline.sh v0.1.0
# release (adds /fab):
./projects/lemon-piano/tools/cloud_pipeline.sh v0.1.0 --fab
```

## Open items

- Bench-validate the filter on the physical board (the V5.5 repo's own
  pending check — switch-flipping session with the V5 bench sampler).
- The 10 capped power/signal stubs (ADR-008) are ≥0.2 mm and current-safe;
  a future placement tweak could open those channels if 100 % nominal
  widths are ever required.
