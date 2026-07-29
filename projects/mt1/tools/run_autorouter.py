#!/usr/bin/env python3
"""End-to-end autorouter pipeline for the MT1 PCB — thin orchestrator.

Delegates to pcb_designer.autorouter (board-agnostic implementation).
This script binds MT1's paths + the v0.1.0 GND stitch coordinates.

Pipeline (each step idempotent):

  1. Load .kicad_pcb via the KiCad Python API (`pcbnew` module).
  2. Export Specctra DSN (the standard interchange format).
  3. Invoke freerouting (Java OSS autorouter, JAR vendored under
     vendor/freerouting.jar) on the DSN to produce a routed SES file.
  4. Import the SES back into the .kicad_pcb (tracks + vias get added;
     (zone) declarations stay as we defined them).
  5. Run the zone filler so the GND polygon is computed (gives DRC a
     proper connectivity model + the renders show the actual fill).
  6. Save the .kicad_pcb.

Usage:
    python3 projects/mt1/tools/run_autorouter.py
    python3 projects/mt1/tools/run_autorouter.py -n   # dry-run: steps 1-3 only

The script is meant to be run AFTER projects/mt1/tools/place_components.py —
that one positions the components and lays down the GND zone
definition; this one fills the signal traces and the zone polygon.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make the pcb_designer package importable when this script is run directly
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from pcb_designer.autorouter import (  # noqa: E402
    ensure_tools,
    export_specctra_dsn,
    run_freerouting,
    import_ses_and_fill,
)

# MT1 board paths (script lives at projects/mt1/tools/, parents[3] = repo root).
REPO_ROOT = Path(__file__).resolve().parents[3]
PROJ = REPO_ROOT / "projects" / "mt1" / "kicad"
PCB_PATH = PROJ / "mt1-pcb.kicad_pcb"
DSN_PATH = PROJ / "mt1-pcb.dsn"
SES_PATH = PROJ / "mt1-pcb.ses"
FREEROUTING_JAR = REPO_ROOT / "vendor" / "freerouting.jar"
VAL = REPO_ROOT / "projects" / "mt1" / "validation"
LOG_PATH = VAL / "freerouting.log"

# MT1 GND stitches (B.Cu bridges to keep the GND zone contiguous post-
# autorouting). NOT used since v0.0.17 — lowering the zone's connect_pads
# clearance from 0.4 → 0.2 (see place_components.inject_routing) lets the
# fill survive between adjacent TH anti-pads at 2.54 mm pitch. Listed
# here for reference and easy re-enable via `--stitches` if a future
# layout reintroduces a fenced region.
MT1_GND_STITCHES = [
    # (x1, y1, x2, y2)  — millimetres, B.Cu, 0.4mm width
    (145.0, 119.92, 110.0, 119.92),   # U3.3 island → west main plane
    (165.24, 121.46, 165.24, 110.0),  # U5.2 island → north main plane
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-n", "--dry-run", action="store_true",
                        help="Export DSN + run freerouting only; "
                             "don't touch the .kicad_pcb.")
    parser.add_argument("--stitches", action="store_true",
                        help="Inject MT1 GND stitches after SES import "
                             "(legacy v0.0.16 behaviour).")
    args = parser.parse_args()

    java_bin = ensure_tools(FREEROUTING_JAR)
    if not PCB_PATH.exists():
        print(f"ERROR: PCB file not found at {PCB_PATH}", file=sys.stderr)
        return 1
    print(f"Using Java: {java_bin}")

    export_specctra_dsn(PCB_PATH, DSN_PATH)
    VAL.mkdir(parents=True, exist_ok=True)
    run_freerouting(java_bin, FREEROUTING_JAR, DSN_PATH, SES_PATH, LOG_PATH)
    if args.dry_run:
        print("\n(dry-run) skipping SES import & save.")
        return 0

    stitches = MT1_GND_STITCHES if args.stitches else None
    import_ses_and_fill(PCB_PATH, SES_PATH, stitches=stitches)

    # Per-pad silkscreen pin legends on BOTH faces — re-applied here (idempotent)
    # so every routed board / new version carries the full pinout legend. The
    # labels come from the ground-truth physical pin names and are verified
    # against each pad's net before emission. See tools/inject_pin_legends.py.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from inject_pin_legends import inject as inject_pin_legends
    print("\n=== Injecting per-pad silk pin legends (both faces) ===")
    inject_pin_legends(PCB_PATH)

    print("\nNext: run projects/mt1/tools/place_components.py to regenerate renders + DRC.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
