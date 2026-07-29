# DECISIONS.md — Lemon Piano V5.5 Board

Every design choice made autonomously (no user in the loop), with rationale.
Circuit facts were **never** decided here — they come from
`arduino-lemon-piano` (see [NETLIST.md](NETLIST.md)).

## ADR-001 — Pin map source: builder contract over stale BOM rows

The V5 `HARDWARE.md` BOM table says "Passive buzzer — D8" and "SENS + on
D7"; the 2026-07-28 pin map in the same file and the DRC-validated
`build_v5_5()` wirewright contract both say **buzzer = D13, SENS+ = D12,
SENS− = A7**. The contract + pin map win (they agree with each other and
with the firmware pin constants); the BOM rows are stale leftovers.

## ADR-002 — Nano socket orientation: mini-USB faces the WEST edge

The 2×15 socket rows run along X (a 43 mm Nano cannot sit across a 30 mm
board). USB-west puts D2..D12 on the SOUTH row → LED bar directly south
with short fanning traces, and A0..A7 on the NORTH row → key header
directly above the analog pins with straight 4 mm drops. USB-east was
evaluated and rejected: it mirrors the rows and makes the LED-bar and
key-header traces cross the board. H1 sits under the USB overhang
airspace (connector is 8.5 mm above board on the socket; M2 screw head
~2 mm — no interference).

## ADR-003 — Power entry on a screw terminal (not a barrel jack)

The v5.5 BOM says "5 V input pigtail / barrel jack — chop a USB-A cable:
red = V+, black = GND". A 2-pos 5.08 mm screw terminal (Phoenix MKDS
1,5/2) accepts exactly that pigtail without a crimped plug, matches the
board-spec wording "jack/terminal", and is the sturdier choice for a
board that gets handled by piano players. Wire entry faces north (off
the board edge).

## ADR-004 — Lemon-key interface: 1×8 pin header on the NORTH edge

Spec allowed "screw-terminal blocks or pin headers". An 8-position screw
block (5.08 mm: 41 mm wide, ~10 mm deep; 3.5 mm: ~8 mm deep) cannot fit
in the 6.5 mm strip between the north edge and the Nano's top socket row
without colliding with it — and moving the Nano south starves the LED
bar. A 1×8 2.54 mm pin header fits directly above A0..A6 (zero-crossing
straight drops), and the lemon leads already terminate in jumper-style
ends in the breadboard build. Pin 1 = GND (clip line, west), then
KEY7..KEY1 — each key pin sits exactly above its Nano analog pin. Every
position is silk-labelled (G, 7..1) per the "labelled" requirement.
Also: the mission text says "8 lemon-key lines + GND clip line"; the
circuit truth is **7** key lines (A0–A6) + 1 GND clip = 8 terminals.

## ADR-005 — LEDs: 3 mm THT green (LED_D3.0mm)

The source BOM says only "Green LEDs ×10". CONVENTIONS §5 default for
status LEDs is 0805 SMD; the breadboard build uses THT. 3 mm THT is the
middle ground: hand-solderable, bright, and 10 of them fit the south
strip at 4.6 mm pitch (5 mm LEDs need ≥5.5 mm pitch — they did not fit
alongside the SENS buttons). Lead pitch is 2.54 mm either way, so the
breadboard's existing LEDs still fit the holes if they are 3 mm parts.

## ADR-006 — Filter parts: vertical axials, radial electrolytics, B.Cu ceramics

- P6KE6.8A / 1N5817 mounted **vertical** (D_DO-15/D_DO-41 P5.08 vertical):
  a 30 mm-tall board is area-limited, not height-limited.
- 470 µF/16 V as 8 mm radial (CP_Radial_D8.0mm_P3.50mm) per "electrolytics
  THT radial" in the board spec.
- L1 = Fastron 07HCP footprint (8.7 mm radial drum, the 07HCP-101K is a
  real 100 µH / 1.3 A part satisfying "≥1 A, low DCR").
- C2/C4 (100 nF ceramics) on **B.Cu** under their electrolytics: the top
  east block is full; a 0805 with two short vias adds ~1 nH, irrelevant
  for a 700 Hz pi filter whose job is conducted-transient suppression.

## ADR-007 — Key pull-ups + SENS− pull-up on B.Cu between the socket rows

R1..R7 + R18 sit on the bottom, each at its analog pin's x, 2.2 mm south
of the row — the region under the socketed Nano is unused on the bottom.
Traces are 2 mm B.Cu stubs to the pin annuli; the +5 V side feeds a
single bus. The LED series resistors (R8..R17) similarly go on B.Cu
under the LED bar, offset +2.3 mm east of each LED.

## ADR-008 — Routing widths: cloud routes at 0.2, post-pass widens

The stateless `/route` endpoint exports the DSN from a bare board: the
default netclass (0.2 mm track / 0.2 mm clearance) applies — netclasses
live in the project file the API never sees. Enforcing the YAML widths
(0.25 signal / 0.5 power ≥ the 0.4 spec minimum) is therefore a local
post-pass (`tools/post_route.py`): clearance-aware widening from the
freerouting centerlines (one-shot, idempotent), capped so 0.2 mm copper
clearance and 0.3 mm edge clearance are never violated, floor 0.2 mm
(= CONVENTIONS §7 minimum). Result on v0.1.0: 105 segments at full
target, 10 short pad-entry stubs capped (all ≤ 0.35 mm, all ≥ 0.2 mm,
worst-case current ≈ 200 mA — a 0.2 mm/1 oz trace is good for ~0.5 A+).
The zone is refilled afterwards (fills are stored in the file; `/drc`
does not refill).

## ADR-009 — GND strategy: B.Cu zone, solid connect on EVERY GND pad

Zone per LESSONS_LEARNED §1/§3/§16: clearance 0.2, min_thickness 0.2,
thermal 0.5/0.5, no `min_resolved_spokes`. v0.0.2 DRC showed the SMD GND
pads of R8..R17 starving on thermal reliefs (1 spoke < 2) in the packed
LED strip → **all** GND pads get `zone_connect 2` (solid). Slightly
harder hand-soldering on those pads, always-connected fill.

## ADR-010 — Automatic zone-island healing (LESSONS_LEARNED §12)

Freerouting output varies run to run; one v0.1.0 route attempt fenced
off a B.Cu fill region (DRC: zone↔zone unconnected). `post_route.py` now
detects fill islands and lays a 0.3 mm B.Cu GND stitch track across the
narrowest pinch (a track needs only clearance where the fill needs
clearance + min_thickness), refills, and repeats — aborting loudly if it
cannot converge. The DRC gate in `cloud_pipeline.sh` additionally blocks
`/fab` whenever errors or unconnected items are non-zero.

## ADR-011 — Silk policy

References hidden for the dense small parts (LEDs, resistors, bottom
ceramics, holes) — the F.Fab layer keeps them all for assembly docs; the
load-bearing labels are explicit: `KEYS G 7..1`, `5V IN + −`, `SENS+`,
`SENS−`, LED `1`/`10`, title + version. All silk text ≥ 0.8 mm (KiCad
text_height DRC minimum). Iterated until `/drc` reports **zero** silk
warnings, so the final DRC gate is 0 errors / 0 warnings with no
justification list needed.

## ADR-012 — Hole-verification vision pass structurally skipped

`pcb_designer.verify.holes`' vision method calibrates a 6-DOF affine
from detected hole centres and needs ≥3 holes; this board has exactly 2
by spec. The geometric check (position, Ø, spacing pattern) runs and
passes; the vision pass is reported as SKIP with the reason, and the
renders are inspected visually in the pipeline instead (gate 7e).

## ADR-013 — Toolkit bugfix: `verify.holes._pad_subblock` main-pad selection

KiCad 9's `MountingHole_*_Pad_Via` footprints serialise the eight Ø0.5
stitching vias BEFORE the Ø2.5 anchor pad; the parser took "the first
pad" and reported drill Ø0.5/pad Ø0.8 for every such hole (false FAIL
against any ground truth). Fixed in `src/pcb_designer/verify/holes.py`
to select the largest-drill pad. `ruff` + full `pytest` (53) stay green.
Own commit per the toolkit-change policy.

## ADR-014 — Deterministic serialisation for idempotency (LESSONS_LEARNED §7)

pcbnew and kicad-sch-api serialise objects in random-UUID order. The
builders therefore (a) canonically reorder top-level and footprint-child
blocks (pads keep library order — the verify parser and human diffs
expect it), and (b) rewrite every UUID with a deterministic uuid5
sequence, mapping old→new so sheet-instance `(path "/…")` references
stay consistent. Each object keeps a unique UUID; none are reused.
Verified: 3 consecutive builds → identical SHA256 for both files.
