#!/usr/bin/env python3
"""Lemon Piano physical-placement verification gate (anti-mirror).

Loads the ground-truth pinout + the .kicad_pcb, runs the four checks
(C1 chirality, C2 flip integrity, C3 pad→net→function, C4 net intent),
prints a report and exits non-zero if any check fails. Runs BEFORE `fab`
so a mirrored or pin-swapped board never produces gerbers.

Usage:
    python3 projects/lemon-piano/tools/verify_placement.py [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from pcb_designer.verify import pinmap, report  # noqa: E402
from pcb_designer.verify.checks import load_ground_truth, run_all  # noqa: E402
from pcb_designer.verify.report import summary  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
PROJ = REPO_ROOT / "projects" / "lemon-piano"
DEFAULT_PCB = PROJ / "kicad" / "lemon-piano.kicad_pcb"
DEFAULT_GT = PROJ / "ground-truth" / "components.yaml"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="lemon-piano anti-mirror verifier")
    ap.add_argument("--pcb", type=Path, default=DEFAULT_PCB)
    ap.add_argument("--ground-truth", type=Path, default=DEFAULT_GT)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if not args.pcb.exists():
        print(f"ERROR: PCB not found: {args.pcb}", file=sys.stderr)
        return 2
    if not args.ground_truth.exists():
        print(f"ERROR: ground truth not found: {args.ground_truth}", file=sys.stderr)
        return 2

    board = pinmap.parse_board(args.pcb.read_text())
    gt = load_ground_truth(args.ground_truth)
    findings = run_all(board, gt)
    passed, failed = summary(findings)

    if args.json:
        print(json.dumps({
            "passed": passed, "failed": failed,
            "findings": [
                {"check": f.check, "component": f.component, "ok": f.ok,
                 "severity": f.severity, "message": f.message, "detail": f.detail}
                for f in findings
            ],
        }, ensure_ascii=False, indent=2))
    else:
        print(report.format_report(findings, board, gt))

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
