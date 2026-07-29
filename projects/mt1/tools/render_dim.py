#!/usr/bin/env python3
"""Generate DIM-mode (PCB-editor-like) renders of the MT1 board.

Thin MT1-specific orchestrator on top of pcb_designer.render_dim. Defines:
- MT1's KiCad project + renders paths
- MT1's per-side layer lists + theme names (mt1-dim-front / mt1-dim-back)

The actual pipeline (kicad-cli PDF + pdftocairo PNG + auto-crop) lives
in pcb_designer.render_dim.

Two flavours, both 2D plots from `kicad-cli pcb export pdf` with custom
KiCad color themes that emulate the GUI "Single Layer + Dim" rendering:

  - **front-dim**: F.Cu pads + traces in bright red on dark navy; back
    layers + silk faintly visible as context.
  - **back-dim** *(mirrored = true bottom view)*: B.Cu plane + traces in
    cyan/light blue on darker navy; front layers faint. Rendered with
    `--mirror` so B.SilkS text reads the RIGHT way round (as on the
    physical bottom / the 3D `--side bottom` view), not reversed.

Themes live under `themes/` and are auto-installed into
`~/.config/kicad/9.0/colors/` (KiCad only resolves `--theme NAME` there).

Usage (standalone):
    python3 projects/mt1/tools/render_dim.py --version v0.1.0-battery-power
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

# Make the pcb_designer package importable when this script is run directly
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from pcb_designer.render_dim import (  # noqa: E402
    install_themes,
    crop_to_content,  # noqa: F401  (re-exported for callers that imported it from here)
    render_side,
)

# MT1 paths.
REPO_ROOT = Path(__file__).resolve().parents[3]
PCB_PATH = REPO_ROOT / "projects" / "mt1" / "kicad" / "mt1-pcb.kicad_pcb"
RENDERS = REPO_ROOT / "projects" / "mt1" / "renders"
THEMES_SRC = REPO_ROOT / "themes"

# MT1 per-side configs.  (theme_name, layer_list, mirror)
# Order matters: layers paint in the given order (active side's layers LAST).
# `mirror=True` on the back → true bottom view (B.SilkS text reads correctly,
# not reversed); see render_side.
MT1_SIDES = {
    "front": (
        "mt1-dim-front",
        ["Edge.Cuts", "B.Cu", "B.SilkS", "B.Mask",
         "F.Mask", "F.Cu", "F.SilkS", "F.Fab"],
        False,
    ),
    "back": (
        "mt1-dim-back",
        ["Edge.Cuts", "F.Cu", "F.SilkS", "F.Mask",
         "B.Mask", "B.Cu", "B.SilkS", "B.Fab"],
        True,
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--version", required=True,
                        help="Version tag for the output filenames "
                             "(e.g. v0.1.0-battery-power).")
    parser.add_argument("--output-dir", type=Path, default=RENDERS,
                        help=f"Output directory (default: {RENDERS}).")
    args = parser.parse_args()

    if not PCB_PATH.exists():
        print(f"ERROR: PCB not found at {PCB_PATH}", file=sys.stderr)
        return 1

    # Install themes with `mt1-` prefix so `--theme mt1-dim-front` resolves.
    install_themes(THEMES_SRC, prefix="mt1-")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="mt1-dim-") as tmp:
        tmpdir = Path(tmp)
        for side, (theme, layers, mirror) in MT1_SIDES.items():
            out = args.output_dir / f"{args.version}-dim-{side}.png"
            render_side(PCB_PATH, layers, theme, out, tmpdir, mirror=mirror)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
