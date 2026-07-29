"""Footprint + silk + net injection passes.

Lift-and-shift from `projects/mt1/tools/place_components.py` (`force_pad_zone_connect`,
`remove_non_module_footprints`) and `projects/mt1/tools/inject_battery.py`
(`_rename_net_in_file`). All board-agnostic — board-specific constants
(KEEP_REFS, battery footprint list) live in the board's config / script.

Public API:
- `force_pad_zone_connect(text, ref, pad_num, mode=2) -> str`
  — inject `(zone_connect <mode>)` into one pad of a footprint.
  Idempotent. mode=2 is solid-fill (LESSONS_LEARNED §1).
- `remove_non_module_footprints(text, keep_refs) -> (text, removed_refs)`
  — strip every `(footprint ...)` whose Reference isn't in `keep_refs`.
  Used by the v0.0.12 "modules-only" reset.
- `rename_net(pcb_path, old, new) -> int`
  — file-level net rename via text substitution.
  pcbnew's `SetNetname()` does NOT update the internal index, so
  renaming in-process is unreliable (LESSONS_LEARNED §8). Matches with
  quotes to avoid `/BTN1` colliding with `/BTN10`.

Legacy aliases for the board orchestrator scripts (projects/<board>/tools/):
- `_rename_net_in_file` ≡ `rename_net`
"""
from __future__ import annotations

import re
from pathlib import Path

from pcb_designer.kicad_pcb_io import extract_footprint_block

__all__ = [
    "force_pad_zone_connect",
    "remove_non_module_footprints",
    "rename_net",
    "_rename_net_in_file",
]


def force_pad_zone_connect(text: str, ref: str, pad_num: str,
                            mode: int = 2) -> str:
    """Inject `(zone_connect <mode>)` into a specific pad of a footprint.

    mode=2 → solid: zone fills right up to the pad (no thermal-relief gap,
    no `(connect_pads (clearance ...))` clearance). Use this to force a
    GND pad to merge with the GND plane when neighbouring TH anti-pads
    fragment the zone fill (the case for U3.3 in v0.0.16).

    Idempotent: if `(zone_connect ...)` is already present in that pad
    block, the existing value is overwritten."""
    ref_re = re.compile(rf'\(property\s+"Reference"\s+"{re.escape(ref)}"')
    m = ref_re.search(text)
    if not m:
        return text
    fp_start, fp_end = extract_footprint_block(text, m.start())
    if fp_start is None:
        return text
    fp_block = text[fp_start:fp_end]

    pad_re = re.compile(rf'(\(pad\s+"{re.escape(pad_num)}"\s+thru_hole[\s\S]*?)(\n\s*\)\s*)(\n)',
                         re.MULTILINE)
    m_pad = pad_re.search(fp_block)
    if not m_pad:
        return text

    pad_body = m_pad.group(1)
    if '(zone_connect' in pad_body:
        new_pad_body = re.sub(r'\(zone_connect\s+\d+\)',
                              f'(zone_connect {mode})', pad_body)
    else:
        new_pad_body = pad_body + f'\n\t\t\t(zone_connect {mode})'

    new_fp_block = fp_block[:m_pad.start(1)] + new_pad_body + fp_block[m_pad.end(1):]
    print(f"  {ref}.{pad_num} -> (zone_connect {mode}) "
          f"({'solid' if mode==2 else 'thermal' if mode==1 else 'none'})")
    return text[:fp_start] + new_fp_block + text[fp_end:]


def remove_non_module_footprints(text: str, keep_refs: set) -> tuple:
    """Strip every (footprint ...) block whose Reference is not in
    `keep_refs`. Returns (new_text, removed_refs)."""
    ref_re = re.compile(r'\(property\s+"Reference"\s+"([A-Z]+[0-9]+)"',
                        re.MULTILINE)
    targets = []
    for m in ref_re.finditer(text):
        ref = m.group(1)
        if ref in keep_refs:
            continue
        fp_start, fp_end = extract_footprint_block(text, m.start())
        if fp_start is None:
            continue
        targets.append((fp_start, fp_end, ref))

    seen_starts = set()
    unique = []
    for s, e, r in targets:
        if s in seen_starts:
            continue
        seen_starts.add(s)
        unique.append((s, e, r))

    unique.sort(reverse=True)
    removed_refs = []
    for s, e, r in unique:
        end = e
        if end < len(text) and text[end] == "\n":
            end += 1
        text = text[:s] + text[end:]
        removed_refs.append(r)

    removed_refs.sort()
    return text, removed_refs


def rename_net(pcb_path: Path, old: str, new: str) -> int:
    """Post-process a saved `.kicad_pcb` to rename a net by string
    substitution.

    pcbnew's `SetNetname()` doesn't update the internal index (LESSONS_LEARNED §8).
    Returns the number of substitutions made.
    """
    text = pcb_path.read_text()
    needle = f'"{old}"'
    repl = f'"{new}"'
    n = text.count(needle)
    if n == 0:
        return 0
    pcb_path.write_text(text.replace(needle, repl))
    print(f"  text-renamed net {old!r} → {new!r} ({n} occurrence{'s' if n != 1 else ''})")
    return n


# ── Legacy aliases (for projects/<board>/tools/*.py during the transition) ──
_rename_net_in_file = rename_net
