"""End-to-end pipeline orchestrator.

Chains stages on a `ProjectConfig`:
  schematic → place → route → render → verify → export3d → fab

`verify` is the physical-placement gate (`pcb_designer.verify`): it aborts
the pipeline before `fab` if any footprint is mirrored, mis-flipped, or
pin-swapped vs the ground-truth pinout (POST-MORTEM-001 / BLK-007).

Stage routing:
- `schematic` / `place` / `route` / `render` subprocess-call the
  board-specific orchestrator scripts in the board's tools dir
  (`project.tools_dir` in the YAML config; defaults to
  `projects/<name>/tools/`). Each script is a thin wrapper that binds
  its board's constants (PLACEMENTS, KEEP_REFS, TARGETS, SIDES, …) and
  delegates the actual work to the board-agnostic helpers in
  `pcb_designer.{kicad_pcb_io, geometry, placement, injection, routing,
  schematic, autorouter, render_dim}`.
- `fab` calls `pcb_designer.fab.full_fab` directly — that stage has no
  board-specific data, just the YAML config + paths.
- `export3d` calls `pcb_designer.export3d.export_3d` directly, same reason.
  It runs in the default chain because a rotatable GLB is the cheapest way
  for a human to sanity-check a board, and because `kicad-cli` drops
  unresolvable component bodies silently — the stage surfaces that instead.

The separation keeps the per-board configuration (placements, footprint
lists, GND stitch coords) in the orchestrator scripts where humans
edit it, and the algorithmic logic (paren walkers, layer-flip rules,
freerouting wrapping, zone-filler ordering) in the package where it's
re-usable across boards.

Public API:
- `Pipeline(config, repo_root=None)` — entry point.
- `Pipeline.run(stages=None) -> PipelineResult` — run the listed stages.
  `stages=None` runs the full chain.
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from pcb_designer.config import ProjectConfig
from pcb_designer.fab import full_fab

__all__ = ["Pipeline", "PipelineResult"]


@dataclass
class PipelineResult:
    success: bool
    stages_run: list[str]
    reports: dict[str, str] = field(default_factory=dict)


class Pipeline:
    """End-to-end orchestrator. Each stage is opt-in via `stages`."""

    def __init__(self, config: ProjectConfig, repo_root: Path | None = None) -> None:
        self.config = config
        self.repo_root = repo_root or Path.cwd()
        self.tools_dir = config.tools_dir(self.repo_root)
        self.pcb_path = self.repo_root / config.project.kicad_project_dir / config.project.kicad_pcb_file
        self.sch_path = self.repo_root / config.project.kicad_project_dir / config.project.kicad_sch_file

    def _run_tool(self, script_name: str, args: list[str] | None = None) -> None:
        script = self.tools_dir / script_name
        if not script.exists():
            raise FileNotFoundError(
                f"board orchestrator script not found: {script}\n"
                f"  (declare `project.tools_dir` in the YAML config, or create "
                f"the script — see projects/mt1/tools/ for a worked example)")
        cmd = [sys.executable, str(script)] + (args or [])
        r = subprocess.run(cmd, cwd=str(self.repo_root))
        if r.returncode != 0:
            raise SystemExit(f"orchestrator script {script_name} exited {r.returncode}")

    def _stage_schematic(self) -> None:
        self._run_tool("build_schematic.py")

    def _stage_place(self) -> None:
        # The board's place_components.py runs: place + flip + DRC + 3D + DIM renders.
        self._run_tool("place_components.py")

    def _stage_route(self) -> None:
        self._run_tool("run_autorouter.py")

    def _stage_render(self) -> None:
        version = self.config.project.version
        self._run_tool("render_dim.py", ["--version", version])

    def _stage_verify(self) -> None:
        # Physical-placement gate (anti-mirror). Exits non-zero if any
        # footprint is mirrored / mis-flipped / pin-swapped vs the
        # ground-truth pinout — so `fab` never runs on a mirrored board.
        # See projects/mt1/docs/POST-MORTEM-001-mirror-rootcause.md.
        self._run_tool("verify_placement.py")

    def _stage_export3d(self) -> None:
        """GLB + STEP for interactive inspection (pcb_designer.export3d).

        Non-fatal by design: a missing 3D-model library must not break a
        pipeline whose electrical outputs are fine, so an unresolved body is
        reported loudly and the stage still succeeds.
        """
        from pcb_designer.export3d import VIEWING_HINT, export_3d
        res = export_3d(self.pcb_path,
                        self.config.exports3d_dir(self.repo_root),
                        self.config.project.version)
        for fmt, path in res.files.items():
            print(f"  {fmt}: {path} ({path.stat().st_size / 1e6:.1f} MB)")
        if res.missing_models:
            print(f"  [WARN] {len(res.missing_models)} component body/bodies could not be "
                  f"resolved — the 3D files will show pads with no part there:")
            for m in res.missing_models[:8]:
                print(f"         {m}")
            print("         install kicad-packages3d, or call export_3d(..., "
                  "fetch_missing=True) to pull just these files.")
        print(VIEWING_HINT)

    def _stage_fab(self) -> None:
        version = self.config.project.version
        releases_dir = self.config.releases_dir(self.repo_root)
        full_fab(self.pcb_path, self.sch_path, releases_dir, version)

    def run(self, stages: list[str] | None = None) -> PipelineResult:
        stages = stages or ["schematic", "place", "route", "render", "verify",
                            "export3d", "fab"]
        stage_map = {
            "schematic": self._stage_schematic,
            "place": self._stage_place,
            "route": self._stage_route,
            "render": self._stage_render,
            "verify": self._stage_verify,
            "export3d": self._stage_export3d,
            "fab": self._stage_fab,
        }
        ran = []
        for s in stages:
            if s not in stage_map:
                print(f"  [WARN] unknown stage {s!r}, skipping")
                continue
            print(f"\n=== Pipeline stage: {s} ===")
            stage_map[s]()
            ran.append(s)
        return PipelineResult(success=True, stages_run=ran)
