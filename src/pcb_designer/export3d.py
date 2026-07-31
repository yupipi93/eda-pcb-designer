"""Interactive 3D export: GLB (glTF binary) + STEP.

Turns a routed `.kicad_pcb` into models you can rotate and inspect:

- **GLB** — self-contained binary glTF. Opens in any browser-based viewer
  (drag it onto <https://3dviewer.net>), in the lightweight native viewer
  `f3d`, and in Windows/macOS built-in 3D viewers. This is the one to hand
  to a human who just wants to look at the board.
- **STEP** — the CAD interchange standard, for FreeCAD / Fusion / enclosure
  design and real fit checks.

Both are produced by `kicad-cli pcb export`, with every visual layer turned
on (tracks, pads, zones, silkscreen, soldermask) so the result matches the
`realistic` render rather than a bare outline.

## The 3D-model dependency

Component *bodies* do not live in the `.kicad_pcb`; each footprint only
carries a **path** to a `.step` file under the `KICAD9_3DMODEL_DIR` tree
(the `kicad-packages3d` library, several GB). `kicad-cli` skips models it
cannot resolve **silently** — you get a board with pads and no components,
and no error. So this module:

1. reads the model paths the board actually references
   (`referenced_models`),
2. reports which of them are missing (`missing_models`),
3. can fetch just those few files from upstream (`fetch_models`, ~1-2 MB
   for a typical board) for hosts that have KiCad but not the multi-GB
   model library — e.g. the slim CI/Docker image,
4. and refuses to pretend: `export_3d` returns the missing list so callers
   can warn instead of shipping a bodiless model.

Public API:
- `referenced_models(pcb_path)` — model paths the board asks for.
- `missing_models(pcb_path, models_dir)` — the subset not present.
- `fetch_models(pcb_path, models_dir, ...)` — download the missing ones.
- `export_glb(pcb_path, out_path, ...)` / `export_step(...)`.
- `export_3d(pcb_path, out_dir, version, ...)` — both formats + a report.
- `VIEWING_HINT` — ready-made "how do I look at this" text for CLIs.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "DEFAULT_MODELS_DIR",
    "MODEL_VAR",
    "UPSTREAM_BASE",
    "VIEWING_HINT",
    "Export3DResult",
    "export_3d",
    "export_glb",
    "export_step",
    "fetch_models",
    "missing_models",
    "referenced_models",
]

MODEL_VAR = "KICAD9_3DMODEL_DIR"
DEFAULT_MODELS_DIR = Path("/usr/share/kicad/3dmodels")

# Raw-file base for the official 3D package library. Only used by the opt-in
# `fetch_models` helper, and only for the handful of files a board needs.
UPSTREAM_BASE = "https://gitlab.com/kicad/libraries/kicad-packages3D/-/raw/master"

# Everything that makes the export look like the board rather than a slab.
_VISUAL_FLAGS = [
    "--include-tracks",
    "--include-pads",
    "--include-zones",
    "--include-silkscreen",
    "--include-soldermask",
    "--subst-models",     # prefer STEP bodies over the older VRML ones
]

_MODEL_RE = re.compile(r'\(model\s+"\$\{' + MODEL_VAR + r'\}/([^"]+)"')

VIEWING_HINT = """How to look at the .glb:
  • web, nothing to install — open https://3dviewer.net and drag the file in
    (it renders in your browser; the file is not uploaded anywhere)
  • local, lightweight     — sudo apt install f3d   then   f3d <file.glb>
  • the .step file is for CAD (FreeCAD, Fusion) and enclosure fit checks"""


@dataclass
class Export3DResult:
    """What `export_3d` produced, and what it could not."""
    files: dict[str, Path] = field(default_factory=dict)
    missing_models: list[str] = field(default_factory=list)
    fetched_models: list[str] = field(default_factory=list)
    substituted_models: dict[str, str] = field(default_factory=dict)

    @property
    def complete(self) -> bool:
        """True when every component body resolved (nothing rendered empty)."""
        return not self.missing_models


def referenced_models(pcb_path: Path) -> list[str]:
    """Model paths the board references, relative to the model root.

    Paths are returned exactly as written after `${KICAD9_3DMODEL_DIR}/`,
    de-duplicated and sorted, e.g.
    `["LED_THT.3dshapes/LED_D3.0mm_Green.step", ...]`.
    """
    text = Path(pcb_path).read_text(encoding="utf-8")
    return sorted(set(_MODEL_RE.findall(text)))


def missing_models(pcb_path: Path, models_dir: Path | None = None) -> list[str]:
    """Referenced model paths that are absent under `models_dir`."""
    root = Path(models_dir) if models_dir else DEFAULT_MODELS_DIR
    return [p for p in referenced_models(pcb_path)
            if not (root / p).is_file()]


def _substitute_candidates(rel_path: str) -> list[str]:
    """Plausible stand-ins for a model that upstream does not ship.

    Colour variants are the case this exists for: the library has
    `LED_D3.0mm.step` but no `LED_D3.0mm_Orange.step` (that one is generated
    downstream). Exactly ONE trailing `_Suffix` is dropped, deliberately:
    stripping further would happily offer `LED.step` for
    `LED_D3.0mm_Orange.step`, i.e. a body of a completely different size.
    A wrong-sized part in a 3D model is worse than an absent one, because
    absent is visible and wrong is not.
    """
    parent, _, name = rel_path.rpartition("/")
    stem, dot, ext = name.rpartition(".")
    base, sep, _suffix = stem.rpartition("_")
    if not sep:
        return []
    cand = base + dot + ext
    return [f"{parent}/{cand}" if parent else cand]


def _http_get(url: str, timeout: float) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as r:   # noqa: S310 (fixed https base)
        return r.read()


def fetch_models(pcb_path: Path, models_dir: Path, *,
                 base_url: str = UPSTREAM_BASE,
                 timeout: float = 60.0,
                 substitute: bool = True,
                 opener=_http_get) -> Export3DResult:
    """Download the models this board needs into `models_dir` (cached).

    For hosts that have KiCad but not the multi-GB `kicad-packages3d`
    library. Only the files the board actually references are fetched —
    typically 15 files / ~1.5 MB — and anything already cached is skipped.

    When a model does not exist upstream and `substitute` is on, a colour-
    variant fallback is copied in its place (see `_substitute_candidates`)
    so the export completes; the swap is reported, never hidden.

    `opener` is injectable so tests never touch the network.
    """
    root = Path(models_dir)
    res = Export3DResult()
    for rel in referenced_models(pcb_path):
        dest = root / rel
        if dest.is_file():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            dest.write_bytes(opener(f"{base_url}/{rel}", timeout))
            res.fetched_models.append(rel)
            continue
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError):
            dest.unlink(missing_ok=True)
        if not substitute:
            res.missing_models.append(rel)
            continue
        for cand in _substitute_candidates(rel):
            src = root / cand
            if not src.is_file():
                try:
                    src.parent.mkdir(parents=True, exist_ok=True)
                    src.write_bytes(opener(f"{base_url}/{cand}", timeout))
                    res.fetched_models.append(cand)
                except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError):
                    src.unlink(missing_ok=True)
                    continue
            shutil.copyfile(src, dest)
            res.substituted_models[rel] = cand
            break
        else:
            res.missing_models.append(rel)
    return res


def _export(kind: str, pcb_path: Path, out_path: Path,
            models_dir: Path | None, extra: list[str] | None) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["kicad-cli", "pcb", "export", kind, *_VISUAL_FLAGS, *(extra or []),
           "-f", "-o", str(out_path), str(pcb_path)]
    env = None
    if models_dir is not None:
        import os
        env = {**os.environ, MODEL_VAR: str(models_dir)}
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if r.returncode != 0:
        print(f"  cmd failed: {' '.join(cmd)}")
        print((r.stderr or r.stdout).strip())
        raise SystemExit(r.returncode)
    if not out_path.is_file():
        raise SystemExit(f"{kind} export reported success but {out_path} is missing")
    return out_path


def export_glb(pcb_path: Path, out_path: Path, *,
               models_dir: Path | None = None,
               extra_args: list[str] | None = None) -> Path:
    """Export binary glTF — the browser/`f3d`-friendly format."""
    return _export("glb", pcb_path, out_path, models_dir, extra_args)


def export_step(pcb_path: Path, out_path: Path, *,
                models_dir: Path | None = None,
                extra_args: list[str] | None = None) -> Path:
    """Export STEP — the CAD interchange format."""
    return _export("step", pcb_path, out_path, models_dir, extra_args)


def export_3d(pcb_path: Path, out_dir: Path, version: str, *,
              formats: tuple[str, ...] = ("glb", "step"),
              models_dir: Path | None = None,
              fetch_missing: bool = False,
              stem: str | None = None) -> Export3DResult:
    """Export the board to every requested 3D format.

    Files land as `out_dir/<stem>-<version>.<ext>`. Set `fetch_missing` on
    hosts without `kicad-packages3d` to pull just the referenced models into
    `models_dir` first. The returned result lists anything that stayed
    unresolved so the caller can warn — a bodiless model is a silent failure
    otherwise.
    """
    pcb_path = Path(pcb_path)
    out_dir = Path(out_dir)
    base = stem or pcb_path.stem
    res = Export3DResult()

    if fetch_missing:
        if models_dir is None:
            models_dir = out_dir / "models"
        res = fetch_models(pcb_path, models_dir)

    still_missing = missing_models(pcb_path, models_dir)
    # fetch_models already accounted for what it could not get; trust the
    # filesystem for the final word so a stale report can't mask a gap.
    res.missing_models = still_missing

    exporters = {"glb": export_glb, "step": export_step}
    for fmt in formats:
        if fmt not in exporters:
            raise ValueError(f"unknown 3D format {fmt!r} (known: {sorted(exporters)})")
        res.files[fmt] = exporters[fmt](
            pcb_path, out_dir / f"{base}-{version}.{fmt}", models_dir=models_dir)
    return res
