"""Fab artefact generation: gerbers + drill + BOM + pos + release zip.

Wraps `kicad-cli pcb export gerbers`, `kicad-cli pcb export drill`,
`kicad-cli pcb export pos`, `kicad-cli sch export bom`, and zips
everything for upload to JLCPCB / PCBWay.

Public API:
- `export_gerbers(pcb_path, out_dir)` — emit one .gbr per layer + .gbrjob.
- `export_drill(pcb_path, out_dir)` — emit Excellon NPTH + PTH .drl files.
- `export_pos(pcb_path, out_path, side='both', fmt='csv')` — emit
  pick-and-place file.
- `export_bom(sch_path, out_path)` — emit BOM CSV from the schematic.
- `package_release(version, paths, out_zip)` — zip everything into a
  single fab-ready archive.
- `full_fab(pcb_path, sch_path, out_dir, version)` — convenience wrapper
  that runs all four exports + zips them.
"""
from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path

__all__ = [
    "export_gerbers",
    "export_drill",
    "export_pos",
    "export_bom",
    "package_release",
    "full_fab",
]


def _run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  cmd failed: {' '.join(cmd)}")
        print(r.stderr.strip())
        raise SystemExit(r.returncode)


def export_gerbers(pcb_path: Path, out_dir: Path) -> list[Path]:
    """Emit one Gerber file per layer + a .gbrjob manifest.

    Layers: F.Cu, B.Cu, F.Mask, B.Mask, F.Silkscreen, B.Silkscreen,
    F.Paste, B.Paste, Edge.Cuts. KiCad's `--layers` accepts a
    comma-separated list; we pass the standard set most fabs accept.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    layers = "F.Cu,B.Cu,F.Mask,B.Mask,F.Silkscreen,B.Silkscreen,F.Paste,B.Paste,Edge.Cuts"
    _run([
        "kicad-cli", "pcb", "export", "gerbers",
        "--output", str(out_dir) + "/",
        "--layers", layers,
        "--no-x2",
        str(pcb_path),
    ])
    # KiCad 9 emits Gerbers with layer-specific extensions:
    #   .gtl/.gbl (Cu), .gts/.gbs (Mask), .gto/.gbo (Silkscreen),
    #   .gtp/.gbp (Paste), .gm1 (Edge), .gbr (generic) + .gbrjob manifest.
    exts = ("*.gtl", "*.gbl", "*.gts", "*.gbs", "*.gto", "*.gbo",
            "*.gtp", "*.gbp", "*.gm1", "*.gbr", "*.gbrjob")
    files = []
    for e in exts:
        files.extend(sorted(out_dir.glob(e)))
    print(f"  → {len(files)} gerber file(s) in {out_dir}")
    return files


def export_drill(pcb_path: Path, out_dir: Path) -> list[Path]:
    """Emit Excellon drill files (NPTH + PTH as separate files)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    _run([
        "kicad-cli", "pcb", "export", "drill",
        "--output", str(out_dir) + "/",
        "--format", "excellon",
        "--excellon-units", "mm",
        "--excellon-separate-th",  # NPTH/PTH split
        str(pcb_path),
    ])
    files = sorted(out_dir.glob("*.drl"))
    print(f"  → {len(files)} drill file(s) in {out_dir}")
    return files


def export_pos(pcb_path: Path, out_path: Path,
               side: str = "both", fmt: str = "csv") -> Path:
    """Emit pick-and-place file (component positions).

    `side` ∈ {front, back, both}. `fmt` ∈ {csv, ascii, gerber}.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "kicad-cli", "pcb", "export", "pos",
        "--output", str(out_path),
        "--side", side,
        "--format", fmt,
        "--units", "mm",
        str(pcb_path),
    ])
    print(f"  → {out_path}")
    return out_path


def export_bom(sch_path: Path, out_path: Path) -> Path:
    """Emit a BOM CSV from the schematic via `kicad-cli sch export bom`."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "kicad-cli", "sch", "export", "bom",
        "--output", str(out_path),
        "--format-preset", "CSV",
        str(sch_path),
    ])
    print(f"  → {out_path}")
    return out_path


def package_release(version: str, paths: list[Path], out_zip: Path) -> Path:
    """Bundle `paths` into a single zip suitable for upload to JLCPCB/PCBWay."""
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in paths:
            if p.is_dir():
                for sub in p.rglob("*"):
                    if sub.is_file():
                        arcname = f"{version}/{sub.relative_to(p)}"
                        zf.write(sub, arcname)
            elif p.is_file():
                arcname = f"{version}/{p.name}"
                zf.write(p, arcname)
    size_kb = out_zip.stat().st_size // 1024
    print(f"  → {out_zip} ({size_kb} KB)")
    return out_zip


def full_fab(pcb_path: Path, sch_path: Path, out_dir: Path,
             version: str) -> Path:
    """Convenience: emit gerbers + drill + pos + BOM + zip them all.

    Output layout:
        out_dir/<version>/
            gerbers/         (gbrs + drill files)
            <pcb>-pos.csv
            <pcb>-bom.csv
            <pcb>-<version>.zip
    """
    rel_dir = out_dir / version
    gerbers_dir = rel_dir / "gerbers"
    pos_path = rel_dir / f"{pcb_path.stem}-pos.csv"
    bom_path = rel_dir / f"{pcb_path.stem}-bom.csv"

    print(f"=== Fab export {version} ===")
    export_gerbers(pcb_path, gerbers_dir)
    export_drill(pcb_path, gerbers_dir)
    export_pos(pcb_path, pos_path)
    export_bom(sch_path, bom_path)

    zip_path = rel_dir / f"{pcb_path.stem}-{version}.zip"
    package_release(version, [gerbers_dir, pos_path, bom_path], zip_path)
    return zip_path
