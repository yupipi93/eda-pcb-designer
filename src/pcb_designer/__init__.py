"""pcb-designer — reusable Python toolkit for KiCad-9 PCB design.

Package layout:
- `cli` — `pcb-designer` console_script (10 subcommands).
- `config` — `ProjectConfig` dataclass + YAML loader.
- `kicad_pcb_io` — depth-aware paren walker + tiny_segments + 3d_model strip.
- `geometry` — outline + silk + title (board-agnostic, all params explicit).
- `placement` — LAYER_PAIRS + flip helpers + `place_and_flip(text, placements)`.
- `injection` — `force_pad_zone_connect` + `remove_non_module_footprints` + `rename_net`.
- `routing` — `segment` + `route_l` + `route_u` + default trace widths.
- `schematic` — `kicad-sch-api` helpers (`g`, `label_pin`, `nc_pin`,
  `auto_label`, `add_pwr_flag`).
- `autorouter` — `find_java21` + DSN/SES round-trip + freerouting wrapper +
  GND stitches + ZONE_FILLER.
- `render_dim` — `install_themes` + `crop_to_content` + `render_side`.
- `fab` — gerbers + drill + BOM + pos + release zip (via `kicad-cli`).
- `pipeline` — `Pipeline(config).run(stages)` end-to-end orchestrator.
- `render_overlay` — photorealistic overlay subpackage (composites
  KiCad renders with real breakout photos; see `projects/mt1/` for a
  board that made it a release gate).
- `verify` — physical-placement verification gate (anti-mirror,
  anti-pin-swap, mounting-hole checks against a ground-truth pinout).

Extracted from the MultitecUA MT1 flight-computer board
(multi-rocket-avionica), which ships in `projects/mt1/` as the worked
example. Use `pcb-designer validate --config <yaml>` to confirm the
package is wired correctly against a board's config.
"""

__version__ = "0.2.0"
__all__ = ["ProjectConfig", "load_config"]

from pcb_designer.config import ProjectConfig, load_config
