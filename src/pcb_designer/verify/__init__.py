"""Physical-placement verification for KiCad PCBs (anti-mirror gate).

Why this package exists: DRC/ERC/`verify_layout()` validate the *drawn
copper*, which is internally consistent even when a module is placed in
mirror image. Three critical mirror/pin-order bugs shipped on MT1 v0.1.x
(see POST-MORTEM-001) precisely because nothing modeled the *physical*
component (its real pinout, its chirality, how it inserts from top/bottom).

This package adds that missing layer. It reads a ground-truth pinout
(`ground-truth/components.yaml`) and the `.kicad_pcb`, then runs four
complementary checks — each mapping 1-to-1 to a known failure:

- C1 `check_chirality`     → XIAO column-swap mirror (multi-column parts)
- C2 `check_flip_integrity`→ fake `flip_to_back` on B.Cu (sensors)
- C3 `check_pad_net_function` → BMP585 SDA/SDO pin-order swap
- C4 `check_net_intent`    → general safety net (bus touches wrong pads)

Pure text parsing (no `pcbnew` dependency) — runs anywhere Python + PyYAML
are available.

Public API:
- `pinmap.parse_board(text) -> dict[ref, Footprint]`
- `checks.run_all(board, gt) -> list[Finding]`
- `report.format_report(findings, board, gt) -> str`
"""
from __future__ import annotations

from . import checks, pinmap, report

__all__ = ["pinmap", "checks", "report"]
