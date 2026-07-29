"""Parse footprints + pads + nets from a `.kicad_pcb`, with pad geometry.

Text-only (no pcbnew). Reuses the depth-aware paren walker from
`kicad_pcb_io` for block boundaries and the `geometry.rotate_cw` transform
already trusted by `place_components.py` (so global pad positions match the
rest of the pipeline).

Coordinate model:
- KiCad global frame: +X right, +Y DOWN.
- Footprint at = (x, y, rot). Pad local = (lx, ly[, lrot]).
- Global pad = footprint_at + rotate_cw(local, rot).
- B.Cu footprint: KiCad mirrors the local X across the footprint origin,
  so local x is negated before the rotation. (For a single-column footprint
  with all pads at lx=0 this is a no-op — which is exactly why the sensor
  mirror was invisible to copper checks.)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from pcb_designer.geometry import rotate_cw
from pcb_designer.kicad_pcb_io import extract_footprint_block

__all__ = ["Pad", "Footprint", "parse_board"]


_NC_PREFIXES = ("unconnected-", "no_connect", "")


def _norm_net(net_name: str | None) -> str | None:
    """Map KiCad NC/auto net names to None so ground-truth `null` matches."""
    if not net_name:
        return None
    if net_name.startswith("unconnected-"):
        return None
    return net_name


@dataclass
class Pad:
    num: str
    lx: float
    ly: float
    lrot: float
    net_num: int
    net_name: str | None      # normalized (None for NC)
    raw_net: str | None       # exactly as in the file
    shape: str


@dataclass
class Footprint:
    ref: str
    value: str
    library: str
    layer: str
    x: float
    y: float
    rot: float
    pads: dict[str, Pad] = field(default_factory=dict)
    block: str = ""

    @property
    def is_back(self) -> bool:
        return self.layer == "B.Cu"

    def global_pad(self, num: str) -> tuple[float, float] | None:
        """Global (x, y) of pad `num`, accounting for rotation and B.Cu mirror."""
        p = self.pads.get(str(num))
        if p is None:
            return None
        lx = -p.lx if self.is_back else p.lx     # B.Cu mirrors local X
        rcx, rcy = rotate_cw((lx, p.ly), self.rot)
        return (self.x + rcx, self.y + rcy)

    def has_mirror_text(self) -> bool:
        """True if any footprint text carries `(justify ... mirror ...)` — the
        signature of a genuine KiCad flip. A footprint moved to B.Cu by a pure
        layer-name swap (`flip_to_back`) lacks this."""
        for m in re.finditer(r"\(justify\b([^)]*)\)", self.block):
            if "mirror" in m.group(1):
                return True
        return False

    def silk_extent_x(self) -> tuple[float, float] | None:
        """(min, max) local X over silk/fab graphics — used to confirm whether
        geometry was actually mirrored on a flip. Returns None if no graphics."""
        xs: list[float] = []
        for m in re.finditer(
            r'\(fp_(?:line|rect|poly|circle|arc)\b[\s\S]*?\(layer\s+"[BF]\.(?:SilkS|Fab)"\)',
            self.block,
        ):
            for pt in re.finditer(r"\((?:start|end|center|mid)\s+(-?[\d.]+)\s+(-?[\d.]+)\)", m.group(0)):
                xs.append(float(pt.group(1)))
        if not xs:
            return None
        return (min(xs), max(xs))


_PROP_REF_RE = re.compile(r'\(property\s+"Reference"\s+"([A-Za-z]+\d+)"')
_AT_RE = re.compile(r"\(at\s+(-?[\d.]+)\s+(-?[\d.]+)(?:\s+(-?[\d.]+))?\s*\)")
_LAYER_RE = re.compile(r'\(layer\s+"([^"]+)"\)')
_FP_HDR_RE = re.compile(r'\(footprint\s+"([^"]+)"')
_VALUE_RE = re.compile(r'\(property\s+"Value"\s+"([^"]*)"')
_PAD_HDR_RE = re.compile(r'\(pad\s+"([^"]+)"\s+(\S+)\s+(\S+)')
_PAD_NET_RE = re.compile(r'\(net\s+(\d+)\s+"([^"]*)"\)')


def _parse_pads(block: str) -> dict[str, Pad]:
    """Walk every `(pad "..." ...)` sub-block and extract num/local/net."""
    pads: dict[str, Pad] = {}
    i = 0
    while True:
        idx = block.find('(pad ', i)
        if idx < 0:
            break
        # depth-aware end of this pad block
        depth = 0
        j = idx
        while j < len(block):
            if block[j] == "(":
                depth += 1
            elif block[j] == ")":
                depth -= 1
                if depth == 0:
                    j += 1
                    break
            j += 1
        pad_txt = block[idx:j]
        i = j

        hdr = _PAD_HDR_RE.search(pad_txt)
        if not hdr:
            continue
        num, _ptype, shape = hdr.group(1), hdr.group(2), hdr.group(3)
        at = _AT_RE.search(pad_txt)
        if not at:
            continue
        lx, ly = float(at.group(1)), float(at.group(2))
        lrot = float(at.group(3)) if at.group(3) else 0.0
        net = _PAD_NET_RE.search(pad_txt)
        if net:
            net_num, raw_net = int(net.group(1)), net.group(2)
        else:
            net_num, raw_net = 0, None
        pads[num] = Pad(
            num=num, lx=lx, ly=ly, lrot=lrot,
            net_num=net_num, net_name=_norm_net(raw_net),
            raw_net=raw_net, shape=shape,
        )
    return pads


def parse_board(text: str) -> dict[str, Footprint]:
    """Return {ref: Footprint} for every footprint in the .kicad_pcb text."""
    out: dict[str, Footprint] = {}
    seen_starts: set[int] = set()
    for m in _PROP_REF_RE.finditer(text):
        ref = m.group(1)
        start, end = extract_footprint_block(text, m.start())
        if start is None or start in seen_starts:
            continue
        seen_starts.add(start)
        block = text[start:end]

        hdr = _FP_HDR_RE.search(block)
        library = hdr.group(1) if hdr else ""
        # The footprint's own (at ...) and (layer ...) are the FIRST in the
        # block (they precede any property/pad sub-blocks).
        at = _AT_RE.search(block)
        layer = _LAYER_RE.search(block)
        value = _VALUE_RE.search(block)
        if not at or not layer:
            continue
        x, y = float(at.group(1)), float(at.group(2))
        rot = float(at.group(3)) if at.group(3) else 0.0

        out[ref] = Footprint(
            ref=ref,
            value=value.group(1) if value else "",
            library=library,
            layer=layer.group(1),
            x=x, y=y, rot=rot,
            pads=_parse_pads(block),
            block=block,
        )
    return out
