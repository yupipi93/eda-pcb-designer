#!/usr/bin/env python3
"""Lemon Piano anchor-hole verification gate (geometric).

Runs pcb_designer.verify.holes' GEOMETRIC check (design .kicad_pcb vs
ground-truth/holes.yaml: presence, position, drill/pad Ø, pattern
spacings). The toolkit's VISION pass is structurally inapplicable here:
its affine calibration needs >=3 holes and this board has exactly 2 by
spec — so it is reported as skipped, not silently dropped. The renders
are still eyeballed as part of the pipeline's vision gate (step 7e).

Usage:
    python3 projects/lemon-piano/tools/verify_holes.py [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from pcb_designer.verify.holes import (  # noqa: E402
    check_holes_geometric,
    load_holes_groundtruth,
    parse_design_holes,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
PROJ = REPO_ROOT / "projects" / "lemon-piano"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="lemon-piano anchor-hole verifier")
    ap.add_argument("--pcb", type=Path, default=PROJ / "kicad" / "lemon-piano.kicad_pcb")
    ap.add_argument("--ground-truth", type=Path,
                    default=PROJ / "ground-truth" / "holes.yaml")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    design = parse_design_holes(args.pcb.read_text(encoding="utf-8"))
    gt = load_holes_groundtruth(args.ground_truth)
    findings = check_holes_geometric(design, gt)
    failed = [f for f in findings if not f.ok and f.severity == "critical"]

    if args.json:
        print(json.dumps({
            "pass": not failed,
            "vision": "skipped: 2 holes < 3 needed for affine calibration",
            "findings": [{"ref": f.ref, "ok": f.ok, "severity": f.severity,
                          "message": f.message, "detail": f.detail}
                         for f in findings],
        }, ensure_ascii=False, indent=2))
    else:
        print(f"anchor holes: screw {gt.screw} drill Ø{gt.drill_dia} pad Ø{gt.pad_dia}")
        for f in findings:
            print(f"  [{'PASS' if f.ok else 'FAIL'}] {f.message}")
            if f.detail:
                print(f"         {f.detail}")
        print("  [SKIP] vision pass: board has 2 anchor holes; affine "
              "calibration needs >=3 (renders eyeballed in gate 7e instead)")
        print("  =>", "PASS" if not failed else "FAIL")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
