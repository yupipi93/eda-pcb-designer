# Changelog

All notable changes to pcb-designer. Format loosely follows Keep a Changelog.

## [Unreleased]

## [0.1.0] — 2026-07-29

First release. Extracted from the
[multi-rocket-avionica](https://github.com/Multitec-UA/multi-rocket-avionica)
project (its `pcb/` toolkit) into a standalone, reusable EDA tool. The engine
had already shipped 5 fabricated releases of the MT1 rocket flight computer at
JLCPCB before extraction; MT1 v0.1.4 is included as the worked example under
`projects/mt1/`.

### Added
- **Deterministic pipeline** (`pipeline.py` + CLI): schematic → place → route →
  render → verify → fab, each stage runnable standalone and idempotent.
- **Typed YAML board config** (`config.py`): one file per board — geometry,
  placements, pin counts, pad extents, net numbers, routing widths, paths.
- **Placement engine** (`placement.py`): text-surgery placement with *genuine*
  F.Cu↔B.Cu flips (layer-tag swap + local-X mirror + text mirror + 3D-model
  strip) — the mirror-image class of bugs that once reached fabrication cannot
  recur (see `projects/mt1/docs/POST-MORTEM-001-mirror-rootcause.md`).
- **Autorouter wrapper** (`autorouter.py`): pcbnew DSN export → freerouting
  (Java 21) → SES import → GND stitches → zone fill, in the one ordering that
  works.
- **Physical-verification gate** (`verify/`): geometric + computer-vision
  checks (chirality, flip integrity, pad-net function, pin-1 orientation,
  mounting-hole centres) against a per-board ground-truth pinout; blocks `fab`.
- **Renders**: PCB-editor-style DIM PNGs (`render_dim.py` + installable KiCad
  themes) and photorealistic overlays compositing real component photos
  (`render_overlay/`, now parameterised by `--project-dir`).
- **Fab exports** (`fab.py`): gerbers + drill + BOM + pick-and-place + release
  zip, JLCPCB/PCBWay-ready.
- **`pcb-designer init`** — new in this release (was a stub upstream):
  scaffolds `projects/<name>/{kicad,tools,renders,validation,releases}` and a
  validated YAML config from packaged templates (`minimal`, `full_features`).
- **Config-driven project layout** — new in this release: `project.tools_dir`
  and `project.releases_output_dir` YAML fields replace the hard-coded
  repo paths the pipeline assumed upstream; defaults follow the
  `projects/<name>/…` convention.
- **Vendor policy**: freerouting v2.1.0 JAR is no longer committed —
  `vendor/fetch-freerouting.sh` downloads it from the official GitHub release
  and verifies its SHA-256.
- **Worked example** `projects/mt1/`: KiCad sources, orchestrator tools, the
  fabricated v0.1.4 release (gerbers/BOM/pos), its renders, DRC baseline and
  physical-verification evidence, ground-truth pinout, and the engineering
  post-mortems that shaped the verify gate.
- Packaging & QA: src layout (hatchling), `pcb-designer` console script,
  42-test pytest suite, ruff-clean, Makefile, Dockerfile (KiCad 9 + Java 21 +
  freerouting in one image), GitHub Actions CI (lint + tests on 3.11/3.12 +
  example validation + init round-trip + Docker smoke test running the real
  MT1 place/render stages), MIT LICENSE, `AGENTS.md` agent protocol and the
  Spanish-language methodology corpus under `docs/`.
