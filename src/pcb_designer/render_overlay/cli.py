#!/usr/bin/env python3
"""CLI entry point for the photorealistic overlay tool.

Usage (from the repo root, board project under projects/<name>/):
  python3 -m pcb_designer.render_overlay.cli --project-dir projects/mt1 --version v0.1.4
  python3 -m pcb_designer.render_overlay.cli --project-dir projects/mt1 --version v0.1.4 --side top
  python3 -m pcb_designer.render_overlay.cli --project-dir projects/mt1 --version v0.1.4 --debug

The board project dir is expected to contain `kicad/*.kicad_pcb`,
`renders/<version>-{top,bottom}.png` and `overlays/modules.yaml` +
`overlays/component-images/`. Every path can also be overridden
individually (--pcb, --renders-dir, --modules, --images-dir, --output-dir).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Allow running this file directly (python3 cli.py) as well as `python -m
# pcb_designer.render_overlay.cli`. When invoked directly, __package__ is
# empty, so we register the sibling modules under the proper package name.
if __package__ in (None, ""):
    sys.path.insert(0, str(HERE.parent.parent))
    __package__ = "pcb_designer.render_overlay"

from .compositor import compose_side, load_module_config


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True,
                        help="Version tag matching renders/<version>-{top,bottom}.png")
    parser.add_argument("--side", choices=("top", "bottom", "both"), default="both")
    parser.add_argument("--project-dir", type=Path, default=Path("projects/mt1"),
                        help="Board project dir with kicad/, renders/, overlays/ "
                             "(default: projects/mt1, relative to cwd)")
    parser.add_argument("--pcb", type=Path, default=None,
                        help="Path to the .kicad_pcb "
                             "(default: sole *.kicad_pcb under <project-dir>/kicad/)")
    parser.add_argument("--renders-dir", type=Path, default=None,
                        help="Folder with base renders <version>-{top,bottom}.png "
                             "(default: <project-dir>/renders)")
    parser.add_argument("--modules", type=Path, default=None,
                        help="Path to modules.yaml (default: <project-dir>/overlays/modules.yaml)")
    parser.add_argument("--images-dir", type=Path, default=None,
                        help="Folder containing per-module images "
                             "(default: <project-dir>/overlays/component-images)")
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="Output folder (default: <project-dir>/overlays)")
    parser.add_argument("--debug", action="store_true",
                        help="Draw bbox + anchor marker over each module")
    parser.add_argument("--no-annotations", action="store_true",
                        help="Skip the technical-drawing dimension annotations")
    parser.add_argument("--annotations",
                        default="pcb,anchors,holes,modules,pins",
                        help="Comma-separated annotation categories to draw. "
                             "Available: pcb, anchors, holes, modules, pins")
    parser.add_argument("--calibration", choices=("mounting_holes", "green_bbox"),
                        default="mounting_holes",
                        help="mm→px mapping source. 'mounting_holes' fits a 6-DOF "
                             "affine to the detected hole centres (precise, "
                             "parametric); 'green_bbox' uses the PCB outline "
                             "(fallback for boards without ≥4 holes).")
    args = parser.parse_args()

    proj = args.project_dir
    if args.pcb is None:
        candidates = sorted((proj / "kicad").glob("*.kicad_pcb")) if (proj / "kicad").is_dir() else []
        if len(candidates) != 1:
            print(f"ERROR: expected exactly one .kicad_pcb under {proj / 'kicad'}, "
                  f"found {len(candidates)} — pass --pcb explicitly.", file=sys.stderr)
            return 2
        args.pcb = candidates[0]
    if args.renders_dir is None:
        args.renders_dir = proj / "renders"
    if args.modules is None:
        args.modules = proj / "overlays" / "modules.yaml"
    if args.images_dir is None:
        args.images_dir = proj / "overlays" / "component-images"
    if args.output_dir is None:
        args.output_dir = proj / "overlays"

    if not args.pcb.exists():
        print(f"ERROR: PCB file not found: {args.pcb}", file=sys.stderr)
        return 2
    if not args.modules.exists():
        print(f"ERROR: modules.yaml not found: {args.modules}", file=sys.stderr)
        return 2

    try:
        modules = load_module_config(args.modules, args.images_dir)
    except Exception as e:
        print(f"ERROR loading modules.yaml: {e}", file=sys.stderr)
        return 2

    sides = ("top", "bottom") if args.side == "both" else (args.side,)
    rc = 0
    for side in sides:
        base = args.renders_dir / f"{args.version}-{side}.png"
        if not base.exists():
            print(f"WARN: base render missing: {base} (skipping)", file=sys.stderr)
            rc = 1
            continue
        out = args.output_dir / f"{args.version}-realistic-{side}.png"
        try:
            cats = tuple(c.strip() for c in args.annotations.split(",") if c.strip())
            result = compose_side(
                side=side,
                base_render_path=base,
                pcb_path=args.pcb,
                modules=modules,
                output_path=out,
                debug=args.debug,
                annotate=not args.no_annotations,
                annotation_categories=cats,
                calibration=args.calibration,
            )
        except Exception as e:
            print(f"ERROR composing {side}: {e}", file=sys.stderr)
            rc = 2
            continue
        print(f"[{side}] rendered {result['rendered']} modules → {result['output'].name}")
        print(f"         px_per_mm = {result['px_per_mm']:.2f}, "
              f"pcb_outline_mm = {result['pcb_outline_mm']}")
        if result["skipped"]:
            for s in result["skipped"]:
                print(f"         skipped: {s}")

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
