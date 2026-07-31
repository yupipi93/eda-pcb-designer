"""ProjectConfig + YAML loader for pcb-designer.

A board's full configuration (geometry, placements, pin counts, footprint
metadata, net numbers, routing widths, file paths) lives in a single YAML
file. `load_config(path)` parses it into a typed `ProjectConfig`
dataclass tree that downstream modules (`placement`, `routing`, …) use
directly.

YAML schema:

    project:
      name: <slug>
      full_name: <human title>
      version: <version tag, e.g. v0.1.0-battery-power>
      vendor: <organisation>
      kicad_project_dir: <path, relative to repo root>
      kicad_pcb_file: <filename>
      kicad_sch_file: <filename>
      validation_output_dir: <path>
      renders_output_dir: <path>
      tools_dir: <path, optional — board orchestrator scripts;
                  defaults to projects/<name>/tools>
      exports3d_output_dir: <path, optional — GLB/STEP 3D exports;
                            defaults to projects/<name>/3d>
      releases_output_dir: <path, optional — fab output;
                  defaults to projects/<name>/releases>

    geometry:
      pcb: { x0, y0, x1, y1 }   # board outline rect, mm
      anchors: { left_x, right_x }   # vertical silk dividers

    placements:
      <ref>: [x_mm, y_mm, rot_deg, layer]   # layer = F.Cu | B.Cu

    pin_counts:
      <ref>: <int>

    pad_half:
      <ref>: [half_x_mm, half_y_mm]

    body_extent:
      <ref>:
        half:   [half_x_mm, half_y_mm]
        offset: [offset_x_mm, offset_y_mm]

    pin_local_positions:
      <ref>: [[x_mm, y_mm], ...]   # in footprint-local frame, before rotation

    th_footprints: [<ref>, ...]   # through-hole footprints

    nets:
      numbers:
        <net>: <int>

    routing:
      trace_width_signal: <mm>
      trace_width_power:  <mm>

Backwards compatibility: missing sections fall back to empty defaults so
partial configs can drive partial pipelines (e.g. a 'blank-board' example
needs only `project` + `geometry`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PcbGeometry:
    x0: float = 90.0
    y0: float = 100.0
    x1: float = 190.0
    y1: float = 130.0

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0


@dataclass(frozen=True)
class AnchorGeometry:
    left_x: float = 100.0
    right_x: float = 170.0


@dataclass(frozen=True)
class Placement:
    x: float
    y: float
    rot: float
    layer: str  # "F.Cu" | "B.Cu"

    def as_tuple(self) -> tuple[float, float, float, str]:
        return (self.x, self.y, self.rot, self.layer)


@dataclass(frozen=True)
class BodyExtent:
    half: tuple[float, float]
    offset: tuple[float, float]


@dataclass(frozen=True)
class ProjectMeta:
    name: str
    full_name: str
    version: str
    vendor: str = ""
    kicad_project_dir: str = ""
    kicad_pcb_file: str = ""
    kicad_sch_file: str = ""
    validation_output_dir: str = ""
    renders_output_dir: str = ""
    tools_dir: str = ""
    releases_output_dir: str = ""
    exports3d_output_dir: str = ""


@dataclass(frozen=True)
class Routing:
    trace_width_signal: float = 0.25
    trace_width_power: float = 0.4


@dataclass
class ProjectConfig:
    """Top-level parametric configuration for a single PCB project."""
    project: ProjectMeta
    geometry_pcb: PcbGeometry = field(default_factory=PcbGeometry)
    geometry_anchors: AnchorGeometry = field(default_factory=AnchorGeometry)
    placements: dict[str, Placement] = field(default_factory=dict)
    pin_counts: dict[str, int] = field(default_factory=dict)
    pad_half: dict[str, tuple[float, float]] = field(default_factory=dict)
    body_extent: dict[str, BodyExtent] = field(default_factory=dict)
    pin_local_positions: dict[str, list[tuple[float, float]]] = field(default_factory=dict)
    th_footprints: set[str] = field(default_factory=set)
    net_numbers: dict[str, int] = field(default_factory=dict)
    routing: Routing = field(default_factory=Routing)

    @property
    def keep_refs(self) -> set[str]:
        """Refs that survive the non-module footprint strip pass."""
        return set(self.placements.keys())

    def pcb_path(self, repo_root: Path) -> Path:
        return Path(repo_root) / self.project.kicad_project_dir / self.project.kicad_pcb_file

    def sch_path(self, repo_root: Path) -> Path:
        return Path(repo_root) / self.project.kicad_project_dir / self.project.kicad_sch_file

    def tools_dir(self, repo_root: Path) -> Path:
        """Board orchestrator scripts dir (default: projects/<name>/tools)."""
        rel = self.project.tools_dir or f"projects/{self.project.name}/tools"
        return Path(repo_root) / rel

    def exports3d_dir(self, repo_root: Path) -> Path:
        """Where `export3d` writes GLB/STEP models (regenerable artefacts)."""
        rel = self.project.exports3d_output_dir or f"projects/{self.project.name}/3d"
        return Path(repo_root) / rel

    def releases_dir(self, repo_root: Path) -> Path:
        """Fab release output dir (default: projects/<name>/releases)."""
        rel = self.project.releases_output_dir or f"projects/{self.project.name}/releases"
        return Path(repo_root) / rel


def load_config(path: str | Path) -> ProjectConfig:
    """Parse a YAML config file into a ProjectConfig.

    Raises:
        FileNotFoundError: path doesn't exist.
        ImportError: PyYAML is not installed.
        ValueError: required `project` section is missing or malformed.
    """
    try:
        import yaml
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            "PyYAML is required to load pcb-designer configs. "
            "Install with `pip install pyyaml` or `pip install -e '.[dev]'`."
        ) from e

    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {p}")

    with p.open("r", encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}

    proj_raw = raw.get("project")
    if not isinstance(proj_raw, dict) or "name" not in proj_raw:
        raise ValueError("Config missing required `project.name` field")

    project = ProjectMeta(
        name=proj_raw["name"],
        full_name=proj_raw.get("full_name", proj_raw["name"]),
        version=proj_raw.get("version", "v0.0.0"),
        vendor=proj_raw.get("vendor", ""),
        kicad_project_dir=proj_raw.get("kicad_project_dir", ""),
        kicad_pcb_file=proj_raw.get("kicad_pcb_file", ""),
        kicad_sch_file=proj_raw.get("kicad_sch_file", ""),
        validation_output_dir=proj_raw.get("validation_output_dir", ""),
        renders_output_dir=proj_raw.get("renders_output_dir", ""),
        tools_dir=proj_raw.get("tools_dir", ""),
        releases_output_dir=proj_raw.get("releases_output_dir", ""),
        exports3d_output_dir=proj_raw.get("exports3d_output_dir", ""),
    )

    geom = raw.get("geometry") or {}
    pcb_geom = PcbGeometry(**(geom.get("pcb") or {}))
    anchor_geom = AnchorGeometry(**(geom.get("anchors") or {}))

    placements = {
        ref: Placement(x=v[0], y=v[1], rot=v[2], layer=v[3])
        for ref, v in (raw.get("placements") or {}).items()
    }

    pin_counts = dict(raw.get("pin_counts") or {})
    pad_half = {
        ref: (v[0], v[1]) for ref, v in (raw.get("pad_half") or {}).items()
    }
    body_extent = {
        ref: BodyExtent(half=tuple(v["half"]), offset=tuple(v["offset"]))
        for ref, v in (raw.get("body_extent") or {}).items()
    }
    pin_local_positions = {
        ref: [(p[0], p[1]) for p in v]
        for ref, v in (raw.get("pin_local_positions") or {}).items()
    }
    th_footprints = set(raw.get("th_footprints") or [])
    net_numbers = dict((raw.get("nets") or {}).get("numbers") or {})
    routing = Routing(**(raw.get("routing") or {}))

    return ProjectConfig(
        project=project,
        geometry_pcb=pcb_geom,
        geometry_anchors=anchor_geom,
        placements=placements,
        pin_counts=pin_counts,
        pad_half=pad_half,
        body_extent=body_extent,
        pin_local_positions=pin_local_positions,
        th_footprints=th_footprints,
        net_numbers=net_numbers,
        routing=routing,
    )
