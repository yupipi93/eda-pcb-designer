"""Human-readable report: per-check verdicts + full pin enumeration.

The pin enumeration is the artefact a human uses to sanity-check a board
before fab: for every footprint, every pad → global (x,y) → net → physical
function, interpreted from BOTH the top and the bottom side.
"""
from __future__ import annotations

from .checks import Finding, GroundTruth, _norm
from .pinmap import Footprint

__all__ = ["format_report", "format_pin_enumeration", "summary"]

_GREEN = "PASS"
_RED = "FAIL"

_CHECK_TITLES = {
    "chirality": "C1 · Quiralidad (espejo)",
    "flip_integrity": "C2 · Integridad de flip a B.Cu",
    "pad_net_function": "C3 · pad → net → función física",
    "pin1_orientation": "C5 · Orientación de pin-1 (montaje por cara)",
    "net_intent": "C4 · Conectividad por intención",
}


def summary(findings: list[Finding]) -> tuple[int, int]:
    failed = sum(1 for f in findings if not f.ok)
    return (len(findings) - failed, failed)


def format_report(findings: list[Finding], board: dict[str, Footprint],
                  gt: GroundTruth) -> str:
    lines: list[str] = []
    lines.append("=" * 74)
    lines.append("  VERIFICACIÓN FÍSICA DE PLACEMENT (anti-espejo) — pcb_designer.verify")
    lines.append("=" * 74)

    # Group findings by check.
    by_check: dict[str, list[Finding]] = {}
    for f in findings:
        by_check.setdefault(f.check, []).append(f)

    for check in ("chirality", "flip_integrity", "pad_net_function",
                  "pin1_orientation", "net_intent"):
        fs = by_check.get(check, [])
        if not fs:
            continue
        lines.append("")
        lines.append(_CHECK_TITLES.get(check, check))
        lines.append("-" * 74)
        for f in fs:
            tag = _GREEN if f.ok else _RED
            lines.append(f"  [{tag}] {f.component:<14} {f.message}")
            if f.detail:
                for dl in f.detail.splitlines():
                    lines.append(f"         ↳ {dl}")

    passed, failed = summary(findings)
    lines.append("")
    lines.append("=" * 74)
    lines.append(f"  RESULTADO: {passed} OK · {failed} FALLO(S)")
    if failed:
        lines.append("  ⛔ NO FABRICAR hasta resolver los FALLOS (ver POST-MORTEM-001).")
    else:
        lines.append("  ✅ Placement físico verificado.")
    lines.append("=" * 74)

    lines.append("")
    lines.append(format_pin_enumeration(board, gt))
    return "\n".join(lines)


def format_pin_enumeration(board: dict[str, Footprint], gt: GroundTruth) -> str:
    """Per-footprint pad table with global position, net, expected function."""
    lines: list[str] = []
    lines.append("ENUMERACIÓN DE PINES (interpretación top / bottom)")
    lines.append("=" * 74)
    for cname, comp in gt.components.items():
        side = comp.get("mount_side", "top")
        lines.append("")
        lines.append(f"▸ {cname}  (refs={comp.get('refs')}  mount_side={side})")
        lines.append(f"  {comp.get('source','')}")
        for ref in comp.get("refs", []):
            fp = board.get(ref)
            if fp is None:
                lines.append(f"    {ref}: ausente en el board")
                continue
            view = "vista bottom" if fp.is_back else "vista top"
            lines.append(f"    {ref}  [{fp.layer}, at=({fp.x},{fp.y},{fp.rot}°), {view}]"
                         f"  lib={fp.library.split(':')[-1]}")
            lines.append("      pad │  global (x,y)    │ net actual            │ func física │ net esperado │ ok")
            lines.append("      ────┼──────────────────┼───────────────────────┼─────────────┼──────────────┼───")
            for num in sorted(fp.pads, key=lambda s: (len(s), s)):
                g = fp.global_pad(num)
                gtxt = f"({g[0]:.2f}, {g[1]:.2f})" if g else "   ?   "
                pad = fp.pads[num]
                actual = pad.net_name or "—"
                spec = comp.get("pins", {}).get(f"{ref}.{num}", {})
                func = spec.get("func", "?")
                exp = _norm(spec.get("net")) or "—"
                ok = "✔" if (pad.net_name or None) == (_norm(spec.get("net")) or None) else "✗"
                lines.append(f"      {num:>3} │ {gtxt:<16} │ {actual:<21} │ {func:<11} │ {exp:<12} │ {ok}")
    return "\n".join(lines)
