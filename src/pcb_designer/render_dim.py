"""DIM-style PDF → PNG render with auto-crop.

Lift-and-shift from projects/mt1/tools/render_dim.py. Board-agnostic: paths and
side configs are explicit parameters.

Pipeline per side:
  1. `kicad-cli pcb export pdf --theme <theme> --layers <list> --mode-single`
     → vector PDF at proper colors.
  2. `pdftocairo -png -r DPI` → high-resolution PNG.
  3. Auto-crop to non-white bbox + padding.

Public API:
- `install_themes(themes_src, kicad_colors_dir=None, prefix='')` — copy
  every `*.json` from `themes_src` into KiCad's user color dir. KiCad's
  `--theme NAME` only resolves names against files there (LESSONS_LEARNED §13).
- `crop_to_content(png_path, padding_px=40)` — auto-crop to non-white bbox.
- `render_side(pcb_path, layers, theme, out_png, tmpdir, dpi=300, padding_px=40)`
  — render one side: PDF + PNG + crop.

Default KiCad user-color dir: `~/.config/kicad/9.0/colors/`.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None  # type: ignore

__all__ = [
    "DEFAULT_KICAD_COLORS_DIR",
    "DEFAULT_DPI",
    "DEFAULT_CROP_PADDING_PX",
    "install_themes",
    "crop_to_content",
    "render_side",
]


DEFAULT_KICAD_COLORS_DIR = Path.home() / ".config" / "kicad" / "9.0" / "colors"
DEFAULT_DPI = 300
DEFAULT_CROP_PADDING_PX = 40


def install_themes(themes_src: Path,
                   kicad_colors_dir: Path | None = None,
                   prefix: str = "") -> None:
    """Copy *.json themes from `themes_src` into KiCad's user color dir.

    KiCad's `--theme NAME` only resolves names against files there; passing
    a path doesn't work (LESSONS_LEARNED §13).

    `prefix` is prepended to each theme's filename in the destination
    (e.g. prefix='mt1-' → `dim-front.json` becomes `mt1-dim-front.json`).
    """
    dst_dir = kicad_colors_dir or DEFAULT_KICAD_COLORS_DIR
    dst_dir.mkdir(parents=True, exist_ok=True)
    for src in themes_src.glob("*.json"):
        dst = dst_dir / f"{prefix}{src.name}"
        if not dst.exists() or src.read_bytes() != dst.read_bytes():
            shutil.copy2(src, dst)
            print(f"  installed theme: {dst.name}")


def crop_to_content(png_path: Path,
                    padding_px: int = DEFAULT_CROP_PADDING_PX) -> None:
    """Crop a PNG to its non-white bounding box, in-place.

    KiCad's PDF→PNG plot lands on a white sheet; this strips the
    surrounding whitespace and keeps the dark-themed board rectangle
    with a small breathing margin. No hard-coded dimensions — works for
    any board outline (LESSONS_LEARNED §14).
    """
    if Image is None:
        raise ImportError("Pillow not installed; pip install Pillow")
    img = Image.open(png_path).convert("RGB")
    w, h = img.size
    pixels = img.load()

    min_x, min_y, max_x, max_y = w, h, 0, 0
    step = max(1, min(w, h) // 1000)
    threshold = 245  # "background" = all channels above this
    for y in range(0, h, step):
        for x in range(0, w, step):
            r, g, b = pixels[x, y]
            if r < threshold or g < threshold or b < threshold:
                if x < min_x: min_x = x
                if x > max_x: max_x = x
                if y < min_y: min_y = y
                if y > max_y: max_y = y

    if min_x >= max_x or min_y >= max_y:
        print(f"  [WARN] no non-white content found in {png_path.name}")
        return

    x0 = max(0, min_x - padding_px)
    y0 = max(0, min_y - padding_px)
    x1 = min(w, max_x + padding_px)
    y1 = min(h, max_y + padding_px)
    img.crop((x0, y0, x1, y1)).save(png_path, optimize=True)


def render_side(pcb_path: Path,
                layers: list[str],
                theme: str,
                out_png: Path,
                tmpdir: Path,
                dpi: int = DEFAULT_DPI,
                padding_px: int = DEFAULT_CROP_PADDING_PX,
                mirror: bool = False) -> None:
    """Render one side DIM-style: PDF via kicad-cli + theme, then PDF→PNG
    via pdftocairo, then crop to board bbox.

    `layers` is the layer list in paint order (active side's layers
    LAST so they draw on top).

    `mirror=True` adds kicad-cli's `--mirror` so the plot is a TRUE
    bottom view (board flipped left-right). Use it for the back side so
    B.SilkS text — authored with `(justify mirror)` to read from below —
    renders the RIGHT way round (matches the kicad `--side bottom` 3D view),
    instead of appearing reversed in a top-projected plot.
    """
    side_tag = out_png.stem
    pdf_path = tmpdir / f"{side_tag}.pdf"

    cmd_pdf = [
        "kicad-cli", "pcb", "export", "pdf",
        "--output", str(pdf_path),
        "--layers", ",".join(layers),
        "--mode-single",
        "--theme", theme,
        *(["--mirror"] if mirror else []),
        str(pcb_path),
    ]
    r = subprocess.run(cmd_pdf, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  {side_tag} PDF export FAILED: {r.stderr.strip()}")
        return

    base = tmpdir / side_tag
    cmd_png = ["pdftocairo", "-png", "-r", str(dpi), "-singlefile",
               str(pdf_path), str(base)]
    r2 = subprocess.run(cmd_png, capture_output=True, text=True)
    if r2.returncode != 0:
        print(f"  {side_tag} PDF→PNG FAILED: {r2.stderr.strip()}")
        return

    raw_png = tmpdir / f"{side_tag}.png"
    shutil.copy2(raw_png, out_png)
    crop_to_content(out_png, padding_px=padding_px)
    print(f"  {side_tag}: {out_png.name}")
