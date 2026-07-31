# Changelog

All notable changes to pcb-designer. Format loosely follows Keep a Changelog.

## [Unreleased]

## [0.4.0] — 2026-07-31

### Added
- **`export3d` stage — rotatable 3D models, in the default pipeline**
  (`pcb_designer.export3d`). Emits a **GLB** (binary glTF, opens in any
  browser viewer such as <https://3dviewer.net> or the light native `f3d`)
  and a **STEP** (CAD interchange, for FreeCAD/Fusion and enclosure fit
  checks). Both carry tracks, pads, zones, silkscreen and soldermask, so the
  model matches the `realistic` render rather than a bare outline.
  - New default stage order: `schematic → place → route → render → verify →
    export3d → fab`. A rotatable model is the cheapest way for a human to
    sanity-check a board, so it is opt-out, not opt-in.
  - `pcb-designer export3d --config <yaml> [--formats glb,step]
    [--fetch-models]`.
  - `POST /export3d?format=glb|step|both` on the HTTP service (`both`
    returns a zip). The service image ships the 3D model library, so
    component bodies always resolve there.
  - New optional config key `project.exports3d_output_dir` (defaults to
    `projects/<name>/3d`).
- **Missing-body detection.** Component bodies are not in the `.kicad_pcb` —
  footprints only store *paths* into the multi-GB `kicad-packages3d` library,
  and `kicad-cli` skips models it cannot resolve **silently** (no warning, no
  DRC item, no non-zero exit). `referenced_models()` / `missing_models()`
  surface that, the stage prints a loud warning, and `Export3DResult.complete`
  lets callers gate on it. Found on the lemon-piano board, where D1 shipped
  bodiless through four releases because nothing could detect it.
- **`fetch_models()`** — pulls only the handful of bodies a board actually
  references (~15 files / ~1.5 MB for a typical board, cached) for hosts that
  have KiCad but not the multi-GB model library, e.g. the slim Docker image.
  Colour variants missing upstream (`LED_D3.0mm_Orange.step`) fall back to
  their base body, and the swap is reported, never hidden. The fallback drops
  **exactly one** filename suffix on purpose: stripping further would offer
  `LED.step` for `LED_D3.0mm_Orange.step`, i.e. a body of a different size —
  a wrong-sized part is worse than an absent one, because absent is visible.
- **VS Code viewer recommendation** — `.vscode/extensions.json` recommends
  `thingraph.cad-viewer`, so the editor offers to install it on first open and
  a `.glb` (or `.step`) opens in a rotatable tab on double-click. It is the one
  extension found that handles *both* formats `export3d` emits, and it bundles
  `occt-import-js.wasm` (OpenCascade), so STEP is a real geometry kernel.
  Deliberately **not** the far more popular `cesium.gltf-vscode` (235 k
  installs): that one validates and converts glTF/GLB but registers no viewer
  for `.glb`, so looking at a binary model means importing it to `.gltf`
  first. `VIEWING_HINT` (printed by the CLI and the pipeline stage) now lists
  the VS Code, web and native options.

## [0.2.0] — 2026-07-29

### Added
- **HTTP API** (`pcb_designer.api`, `[api]` extra — Flask + gunicorn):
  stateless KiCad pipeline operations over uploaded board files, mirroring
  eda-wirewright's hosted-engine pattern. Endpoints: `POST /validate` (YAML
  config → summary), `POST /place` (placements applied with genuine layer
  flips), `POST /drc` (KiCad DRC report as JSON), `POST /render` (raytraced
  PNGs), `POST /route` (**freerouting-as-a-service**: strip tracks → DSN →
  freerouting → SES → zone fill), `POST /fab` (gerbers/drill/BOM/pos zip),
  plus `GET /health` and `GET /openapi.json` so agents self-configure. No
  uploaded code is ever executed; errors are structured JSON with meaningful
  statuses; hosts missing a tool answer 501 with install instructions.
- **Cloud Run deployment**: `deploy/Dockerfile` (same KiCad 9 + Java 21 +
  freerouting toolchain, served by gunicorn) and `deploy/cloudbuild.yaml`.
  Live at https://pcb-designer.scv.multitecua.com (direct service URL:
  https://pcb-designer-773810300510.europe-west1.run.app). The service is
  Terraform-managed (multitec terraform repo, workspace sergioconejero);
  production deploys are tag-driven — push `pcb-designer-vX.Y.Z`.
- 11 API unit tests (53 total); CI docker job extended with an end-to-end
  HTTP smoke test (health → validate → place → drc → render → route → fab).

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
