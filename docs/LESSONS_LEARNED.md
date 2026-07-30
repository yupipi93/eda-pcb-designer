# LESSONS_LEARNED.md — pcb-designer

> 24 hard-won rules about manipulating KiCad 9 `.kicad_pcb` files
> programmatically, learned on the MultitecUA MT1 board (the worked
> example in `projects/mt1/`). Each rule
> below is referenced from the relevant module (`kicad_pcb_io`,
> `geometry`, `placement`, `injection`, `routing`, `autorouter`,
> `render_dim`) and from unit/regression tests; if you break one, the
> board will look fine on screen and silently fail on pcbnew load or
> DRC. **Treat this file as load-bearing.**
>
> Source incidents and PR commit messages are catalogued in the MT1
> project history (upstream repo `multi-rocket-avionica`,
> `pcb/projects/mt1/docs/CHANGELOG.md`).

---

## §1 — `force_pad_zone_connect(mode=2)` for solid-fill GND TH pads

When a GND through-hole pad sits in a neighbourhood with multiple TH
anti-pads, KiCad's default thermal-relief mode (mode 1, four spokes)
fragments the zone fill and a copper island gets stranded near the pad.

Fix: force `(zone_connect 2)` on the offending pad. Mode 2 = solid:
zone copper fills right up to the pad edge, no thermal-relief gap, no
`(connect_pads (clearance ...))` clearance. Combine with
`min_resolved_spokes 2` on the *zone* (not the pad) to keep the rest
of the board on thermal reliefs.

Failure mode if you skip this: GND zone shows island fragments around
U3.3 in v0.0.16+; freerouting then can't bridge them.

---

## §2 — `remove_tiny_segments(max_len_mm=0.1)` post-freerouting

Freerouting occasionally emits 1-pixel "segments" inside vias — the
`(segment ...)` block contains nested `(start ...)` and `(end ...)`
S-expressions whose paren depth must be tracked. A naive regex
`r'\(segment[^)]*\)'` will rewrite or strip the wrong block.

Implementation lives in `kicad_pcb_io.remove_tiny_segments`. It
walks the file as text with a depth-aware paren counter and considers
a segment only when balanced `(` / `)` count returns to 0.

---

## §3 — GND zone parameters: `clearance: 0.2 mm`, `min_thickness: 0.2 mm`

The defaults (clearance 0.4 mm, min_thickness 0.5 mm) FRAGMENT the
zone fill at the 2.54 mm pitch of TH pads on MT1 — the zone literally
cannot reach into the corridors between TH columns.

Use 0.2 / 0.2 mm. DRC still passes on standard 0.15 mm clearance
rules.

---

## §4 — `_LAYER_PAIRS` auto-swap on layer flip

Flipping a footprint between F.Cu and B.Cu requires swapping seven
layer tags (Cu, Paste, Mask, SilkS, Fab, Adhes, CrtYd) in the
`(footprint ...)` block. The table is hard-coded in
`placement.LAYER_PAIRS` and must be applied as STRING REPLACES inside
double quotes (`'"F.Cu"' → '"B.Cu"'`) — the unquoted token `F.Cu` would
also match net names and properties.

---

## §5 — Strip 3D model blocks on flip-to-back

When KiCad auto-flips a footprint's 3D model on a layer-tag swap, the
model lands ~20 mm OFF the actual pads in renders (visible as a
floating breakout 30 mm above the board in the bottom view PNG). The
pads themselves are correctly placed.

Fix: `placement._strip_3d_model_blocks` removes every `(model "..." ...)`
sub-block from a footprint before applying the layer swap. The
photorealistic overlay (`pcb_designer.render_overlay`) shows the real
component photo anyway, so the missing model in the KiCad render is
not user-visible.

---

## §6 — Backup before mutate

Every text mutation pass writes `<file>.bak6` (next free .bak slot)
before clobbering the original. `kicad_pcb_io.read_pcb()` does this
transparently. Idempotent: if `.bak6` exists, the snapshot is skipped.

The KiCad GUI uses `.bak`, `.bak2`, …, `.bak5` for its own autosaves.
`.bak6+` is reserved for the toolchain.

---

## §7 — Idempotency end-to-end

Every CLI subcommand and every public function in `pcb_designer.*`
must produce **byte-identical output** when re-run on the same input.
This is the regression gate for the entire package:

- Re-running `pcb-designer pipeline --config mt1.yaml` after a clean
  produces the same `.kicad_pcb` (SHA256), the same DRC report, and
  the same PNG checksums (≤1 % pixel diff for `pdftocairo`'s
  non-determinism).
- Re-running a subcommand twice in sequence is a no-op on the second
  run.

If you add a feature that introduces randomness (UUIDs, timestamps),
expose it as a `--no-random` flag and default to seeded output.

---

## §8 — Net rename via text post-pass (NOT `pcbnew.SetNetname`)

`pcbnew.SetNetname()` updates the in-memory object but **does not**
update the internal net-name index, so subsequent net lookups by the
new name return nothing and the saved file still contains the old
name.

Workaround: do the rename as a text post-pass on the `.kicad_pcb`
file. CRITICAL: match with surrounding quotes (`"/BTN1"` not `/BTN1`)
or `/BTN1` will also match `/BTN10`, `/BTN11`, … and collide.
Implementation in `injection.rename_net`.

---

## §9 — `ExportSpecctraDSN` strip-tracks-first

Freerouting v2 short-circuits with an empty `.ses` if the input
`.dsn` contains tracks (which `ExportSpecctraDSN` from pcbnew emits
unconditionally). Strip every `(wiring ...)` block from the DSN
before invoking freerouting. Implementation in
`autorouter.export_specctra_dsn(strip_tracks=True)`.

---

## §10 — Java 21 detection ladder

freerouting v2 needs class file 65+ (Java 21+). Default `java` on
Ubuntu 24 is Java 17 — silently miscompiles. Try in order:

1. `JAVA_21_HOME/bin/java`
2. `/usr/lib/jvm/java-21-openjdk-amd64/bin/java`
3. `/usr/lib/jvm/java-21-openjdk-*/bin/java`  (glob match)
4. `update-alternatives --display java | grep 21`
5. `java -version 2>&1 | grep '21\\.'`
6. `which java` ← fallback, validate with `java -version`

Implementation in `autorouter.find_java21`.

---

## §11 — `ZONE_FILLER` AFTER `ImportSpecctraSES` AND after stitches

If you fill the zones before importing the SES, the SES tracks have
no copper to land on and freerouting's connect_pads metadata
mis-translates. If you import the SES and skip the zone filler, the
GND fill has gaps where the new tracks cross the zone.

Correct order: import SES → add GND stitches → run ZONE_FILLER.
Implementation in `autorouter.run_zone_filler` and the pipeline glue
in `pipeline.Pipeline.run`.

---

## §12 — `add_gnd_stitches()` for trapped islands

After freerouting + zone fill, some B.Cu GND islands stay isolated
(no track or via reaches them). Add explicit B.Cu→F.Cu via stitches
at known choke points; configurable per board via
`config.geometry.gnd_stitches`.

For MT1 v0.1.0 the stitches sit at the centre-line of the battery
strip and at the bottom edge of the U2 footprint.

---

## §13 — KiCad DIM theme install path

KiCad 9 only looks for color themes under
`~/.config/kicad/9.0/colors/`. Symlinks work, but the file's basename
must end with `.json` and the `(name "...")` field inside must match
the basename without extension.

`render_dim.install_themes` copies `themes/dim-*.json`
into that dir at startup.

---

## §14 — PDF → PNG: `pdftocairo -r DPI` + auto-crop to non-white bbox

KiCad's `Plot to PDF` produces a PDF whose page is the full sheet
(A4) with the actual layout in a small corner. Convert with
`pdftocairo -r <DPI> -png in.pdf out_prefix` (the `-r` flag is the
output DPI; the input PDF's logical size is irrelevant).

Then auto-crop: load the PNG with PIL, find the bbox of all non-white
pixels (any pixel where R<240 or G<240 or B<240), pad by 40 px, and
re-save. No hard-coded dimensions — works for any board outline.

Implementation in `render_dim.crop_to_content`.

---

## §15 — Render-overlay calibration: bbox center auto-detect

The realistic overlay (`pcb_designer.render_overlay`) does NOT
hard-code px/mm scale or board centre. It parses the `.kicad_pcb`
Edge.Cuts rect, computes the bbox centre in mm, opens the KiCad PNG,
computes the bbox centre in px (non-white pixels), and derives px/mm
from those two centres + the rect size.

This means a different board outline shape just works — no per-board
calibration tweak.

---

## §16 — `(min_resolved_spokes 1)` PROHIBITED inside `(fill ...)`

Putting `(min_resolved_spokes 1)` inside the `(fill ...)` sub-block of
a zone CRASHES pcbnew on `LoadBoard()`. The token is valid at the
`(zone ...)` level but NOT inside `(fill ...)`.

If freerouting or a copy-paste from a forum example puts it there,
`autorouter.import_specctra_ses` strips it before saving.

---

## §17 — `reposition_silk` first-vertical-line targeting

The anchor silk dividers (vertical lines at LEFT_ANCHOR_X and
RIGHT_ANCHOR_X) need to land at specific coordinates. Detecting them
in the existing `(gr_line ...)` blocks is fragile because there are
multiple vertical lines on the layer (footprint silk, board outline,
etc.).

Strategy: do NOT detect. Match the *first* `(gr_line ...)` block on
the F.SilkS layer in the file order, replace its coords with the
right anchor; then INSERT a new block for the left anchor right after
it. Reconstructs deterministically from scratch on every run.

Implementation in `geometry.reposition_silk`.

---

## §18 — Title silk regen-every-run via template

The PCB title silk (`MT1 vX.Y.Z - MultitecUA`) goes stale across
iterations if you try to "update it in place". Match the regex
`r'\(gr_text\s+"MT1[^"]*MultitecUA"...'` and replace with a fresh
title built from `config.project.version`.

Idempotent: re-running with the same version produces the same text
in the same place. The regex matches anything looking like an MT1
title so stale versions get overwritten too.

Implementation in `geometry.title_silk` (post P3.B migration).

---

## §19 — `extract_footprint_block` depth-aware paren walker

This is the BEDROCK PRIMITIVE of the entire package. Every higher-
level helper that mutates a footprint (`place_and_flip`, `force_pad_zone_connect`,
`strip_3d_model_blocks`, `rename_net`) calls it.

Implementation: given the byte offset of a `(property "Reference" "X")`
match, walk *backwards* in the text to find the enclosing `(footprint`,
then walk *forwards* tracking paren depth until it returns to zero.

Unit tests covering this primitive are MANDATORY in
`tests/unit/test_kicad_pcb_io.py`:

- One footprint, deeply nested.
- Two footprints adjacent.
- Footprint with `(model "...")` sub-block containing parens in the
  filename.
- Footprint with `(pad ...)` containing `(net N "name with (parens)")`.

---

## §20 — DRC + render are part of the pipeline, not afterthoughts

Every `pcb-designer place` and `pcb-designer route` invocation emits:

1. A DRC report under `projects/<board>/validation/drc-<version>.txt`
   (the run aborts non-zero if DRC has errors, unless `--no-drc`).
2. A pair of dim-front + dim-back PNGs under
   `projects/<board>/renders/<version>-dim-{front,back}.png`.
3. A realistic overlay pair under
   `projects/<board>/overlays/<version>-realistic-{top,bottom}.png`.

This is the source of truth for regression gates: the dim PNGs are
compared SHA256-against the goldens. The realistic overlay was a hard
release requirement on the MT1 project; treat it as a per-project
policy knob, not a pipeline invariant.

---

## §21 — NUNCA deformar la imagen de overlay (factor de forma)

`real_size_mm` ([w,h] mm) **debe** tener el mismo aspect ratio que la imagen
fuente en píxeles. Escalar un solo eje estira la foto y desplaza sus pines y
orificios de anclaje (incidente 2026-06-18: LSM6 +12.6 %, BMP585 +10.1 % al
subir sólo el ancho para ajustar el paso de pines).

- Enforce: `render_overlay.compositor._assert_image_aspect` (>5 % → `ValueError`;
  override por módulo `allow_aspect_deviation`). Tests en `test_pins.py`.
- Para redimensionar: cambia w **y** h juntos. Para ajustar el paso de pines:
  escala **uniforme** + re-centra con `body_offset_mm`. Nunca un solo eje.

## §22 — Render base para overlay: `--background transparent`

`kicad-cli pcb render` debe usar `--background transparent` (no `opaque`). Con
`opaque` el fondo gris se ve a través de los taladros pasantes y el detector
dark-bore falla (LOO 0.6–1.6 mm vs 0.0097 mm). El render comprometido es RGBA
con taladros negros. Regenerar cambia el framing (~2352 vs 2384 px) → re-afinar
el perpendicular de los pines tras regenerar.

## §23 — Detección de centros: dark-bore + círculo de Kåsa (no centroide de intensidad)

- Centro de orificio = **dark-bore** (centroide del taladro oscuro), invariante a
  iluminación. El centroide del anillo dorado tiene sesgo direccional de ~1.5 mm.
- Para centrar el taladro PCB en el orificio del módulo: **ajuste de círculo (Kåsa)**
  al anillo dorado vs dark-bore del taladro. El centroide por intensidad y el borde
  blanco están sesgados por serigrafía (~0.2 mm fantasma).
- Mapeo imagen-fuente→placa: transformación **isótropa** del compositor validada
  con pines; una afín libre es DEGENERADA con pines colineales.
- Calibración mm↔px: `calibrate_from_holes` (afín 6-DOF a H1–H6, residual ≤0.01 mm).

## §24 — Orificios de anclaje de módulo (MH) = keepout de ruteo

Coloca MH1–MH6 antes de rutear; trata el NPTH como keepout (clearance 0.25 mm);
**si mueves un MH, RE-RUTEA** (mover el orificio no reenruta la pista → taladro
sobre pista, incidente MH1 vs `/+3V3`). DRC tras rutear: cero `hole_clearance` de
pista contra pad MH. Síntesis completa:
[`MOUNTHOLE_OVERLAY_METHODOLOGY.md`](MOUNTHOLE_OVERLAY_METHODOLOGY.md).

---

## Cross-references

- [`METHODOLOGY.md`](METHODOLOGY.md) — high-level 8-step pipeline
- [`MOUNTHOLE_OVERLAY_METHODOLOGY.md`](MOUNTHOLE_OVERLAY_METHODOLOGY.md) — overlay alignment, mounting-hole placement/centering & verification (§0 factor de forma, §5 routing keepouts)
- [`CONVENTIONS.md`](CONVENTIONS.md) — ref designators, net names, footprint conventions
- [`SCHEMATIC_RECIPE.md`](../projects/mt1/docs/SCHEMATIC_RECIPE.md) — kicad-sch-api recipe
- [`FAB_ORDER_GUIDE.md`](FAB_ORDER_GUIDE.md) — JLCPCB / PCBWay quote-to-order
- [`../AGENTS.md`](../AGENTS.md) — manual obligatorio para LLMs antes de tocar el PCB
- MT1 source incidents (v0.0.1 → v0.1.4): upstream repo `multi-rocket-avionica`, `pcb/projects/mt1/docs/CHANGELOG.md`

## §25 — `pad.GetLayer()` LIES for flipped footprints — use `IsOnLayer()`

A pad belonging to a footprint flipped to B.Cu still reports
`GetLayer() == F_Cu` in the pcbnew Python API. Any layer test built on
`GetLayer()` silently exempts every bottom-side SMD pad from clearance
checks (incident: lemon-piano v0.2.0 — the post-route widener grew a
B.Cu track into a flipped 0805's pad, 0.1777 mm actual vs 0.2 required,
found by /drc). Always test pads with `pad.IsOnLayer(layer)`.

## §26 — Overlay photo rotation: `PIL_rot = −pcb_rot + image_rot` (calibrate the DATA)

`render_overlay.module_overlay` composes the pasted photo's rotation
with a NEGATED footprint angle. MT1 never exercised the sign (anchors
at 180°/bottom); the first 90°-anchor board (lemon-piano) landed its
Nano photo 180° off on the first try. The convention is baked into
MT1's calibrated modules.yaml values — do NOT "fix" the sign in code;
calibrate each board's `image_rotation_deg` against a render, exactly
like MT1 did. The overlay itself shows the error immediately (that is
its job — see POST-MORTEM-001).
