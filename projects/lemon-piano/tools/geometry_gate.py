#!/usr/bin/env python3
"""Lemon Piano geometry + routing assertions (mission gate 7d/7b).

Pure-text checks over the routed .kicad_pcb (no pcbnew needed):
  1. outline is exactly 100 x 30 mm at (90,100)-(190,130);
  2. exactly 2 mounting holes, mirror-symmetric about x=140 within 0.1 mm,
     at the short-edge extremes, both at board mid-height;
  3. the Nano mini-USB corridor to the WEST edge is free of tall parts
     (only H1 inside x<104, |y-115|<=9.5) and the key header / power
     terminal / LED bar / buttons sit on their service edges;
  4. every net in the YAML has copper (>=1 segment, or GND-zone), and
     every pad's net matches docs/NETLIST.md via the ground-truth file
     (that part is verify_placement's job — here we count copper);
  5. no courtyard overlaps, computed from the YAML pad_half/body_extent
     data (independent re-check of KiCad's courtyard DRC).

Exits non-zero on any failure.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
PROJ = REPO_ROOT / "projects" / "lemon-piano"
CFG = yaml.safe_load((PROJ / "lemon-piano.yaml").read_text(encoding="utf-8"))
PCB = PROJ / "kicad" / CFG["project"]["kicad_pcb_file"]

FAILS: list[str] = []


def check(ok: bool, msg: str) -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {msg}")
    if not ok:
        FAILS.append(msg)


def main() -> int:
    text = PCB.read_text(encoding="utf-8")
    geom = CFG["geometry"]["pcb"]

    # 1. outline ---------------------------------------------------------
    m = re.search(r'\(gr_rect\s*\(start ([\d.]+) ([\d.]+)\)\s*\(end ([\d.]+) ([\d.]+)\)'
                  r'[\s\S]*?\(layer "Edge.Cuts"\)', text)
    check(m is not None, "Edge.Cuts rectangle present")
    if m:
        x0, y0, x1, y1 = map(float, m.groups())
        check((x0, y0, x1, y1) == (geom["x0"], geom["y0"], geom["x1"], geom["y1"]),
              f"outline {x1 - x0:.1f} x {y1 - y0:.1f} mm at ({x0},{y0})")
        check(abs((x1 - x0) - 100.0) < 1e-6 and abs((y1 - y0) - 30.0) < 1e-6,
              "outline is exactly 100 x 30 mm")

    # 2. mounting holes --------------------------------------------------
    holes = {}
    for ref in ("H1", "H2"):
        mm_ = re.search(rf'\(property "Reference" "{ref}"', text)
        blk_start = text.rfind("(footprint", 0, mm_.start())
        at = re.search(r'\(at ([\d.\-]+) ([\d.\-]+)', text[blk_start:mm_.start() + 500])
        holes[ref] = (float(at.group(1)), float(at.group(2)))
    n_h = len(re.findall(r'\(property "Reference" "H\d+"', text))
    check(n_h == 2, f"exactly 2 mounting holes (found {n_h})")
    (h1x, h1y), (h2x, h2y) = holes["H1"], holes["H2"]
    cx = (geom["x0"] + geom["x1"]) / 2
    check(abs((cx - h1x) - (h2x - cx)) <= 0.1,
          f"H1/H2 mirror-symmetric about x={cx} (offsets {cx - h1x:.2f}/{h2x - cx:.2f})")
    check(abs(h1y - h2y) <= 0.1, f"H1/H2 same height (y {h1y} / {h2y})")
    check(h1x - geom["x0"] <= 10 and geom["x1"] - h2x <= 10,
          "holes at the short-edge extremes (<=10 mm from edge)")
    check(abs(h1y - (geom["y0"] + geom["y1"]) / 2) <= 0.1, "holes at board mid-height")

    # 3. orientation / service edges -------------------------------------
    pl = CFG["placements"]
    check(pl["U1"][0] < pl["U2"][0] + 36 and pl["U1"][0] == 104.0,
          "Nano socket rows start at x=104 (USB end faces west edge)")
    check(pl["J2"][1] <= 104.0, "keys header on the NORTH service edge")
    check(pl["J1"][1] <= 106.0, "power terminal on the NORTH service edge")
    check(all(pl[f"D{i}"][1] >= 126.0 for i in range(3, 13)),
          "LED bar on the SOUTH service edge")
    check(pl["SW1"][1] >= 122.0 and pl["SW2"][1] >= 122.0,
          "SENS buttons on the SOUTH service edge")
    # USB corridor: no F.Cu part with body in x<103, 105.5<y<124.5 except H1
    intruders = []
    for ref, (x, y, rot, layer) in pl.items():
        if ref in ("H1",) or layer != "F.Cu":
            continue
        if x < 103.0 and 105.5 < y < 124.5:
            intruders.append(ref)
    check(not intruders, f"mini-USB west corridor free of parts {intruders or ''}")

    # 4. copper per net ---------------------------------------------------
    net_numbers = CFG["nets"]["numbers"]
    seg_nets = [int(n) for n in re.findall(r'\(segment[\s\S]*?\(net (\d+)\)', text)]
    from collections import Counter
    seg_count = Counter(seg_nets)
    zone_gnd = bool(re.search(r'\(zone\s*\(net 2\)[\s\S]*?\(filled_polygon', text))
    missing = []
    for name, num in net_numbers.items():
        if name == "GND":
            if not (zone_gnd or seg_count.get(num)):
                missing.append(name)
        elif not seg_count.get(num):
            missing.append(name)
    check(zone_gnd, "GND zone present and filled on B.Cu")
    check(not missing, f"every net has copper ({len(net_numbers)} nets; "
                       f"missing: {missing or 'none'})")

    # 5. courtyard overlaps from YAML data --------------------------------
    def bbox(ref, pads_only=False):
        x, y, rot, layer = pl[ref]
        pins = CFG["pin_local_positions"].get(
            ref, [[0, 2.54 * k] for k in range(CFG["pin_counts"][ref])])
        ph = CFG["pad_half"].get(ref, [0.8, 0.8])
        pts = []
        for px, py in pins:
            for sx in (-1, 1):
                for sy in (-1, 1):
                    pts.append((px + sx * ph[0], py + sy * ph[1]))
        be = CFG.get("body_extent", {}).get(ref)
        if be and not pads_only:
            ox, oy = be["offset"]
            hx, hy = be["half"]
            for sx in (-1, 1):
                for sy in (-1, 1):
                    pts.append((ox + sx * hx, oy + sy * hy))
        out = []
        for px, py in pts:
            if layer == "B.Cu":       # flipped about local Y axis
                px = -px
            r = math.radians(rot)
            # KiCad: global = origin + R(rot)·local, +Y down, rot 90 => +Y->+X
            gx = x + px * math.cos(r) + py * math.sin(r)
            gy = y - px * math.sin(r) + py * math.cos(r)
            out.append((gx, gy))
        xs = [p[0] for p in out]
        ys = [p[1] for p in out]
        return min(xs), min(ys), max(xs), max(ys)

    th = set(CFG["th_footprints"])
    refs = list(pl)
    overlaps = []
    for i in range(len(refs)):
        for j in range(i + 1, len(refs)):
            a, b = refs[i], refs[j]
            la, lb = pl[a][3], pl[b][3]
            if la == lb:
                # same side: full courtyard vs full courtyard
                ba, bb = bbox(a), bbox(b)
            elif a in th or b in th:
                # THT vs opposite-side SMD: the THT part only occupies the
                # far side with its annuli — compare pad bbox vs full bbox
                ba = bbox(a, pads_only=a in th)
                bb = bbox(b, pads_only=b in th)
            else:
                continue              # SMD on opposite sides: no conflict
            if ba[0] < bb[2] and bb[0] < ba[2] and ba[1] < bb[3] and bb[1] < ba[3]:
                overlaps.append((a, b))
    check(not overlaps, f"no courtyard overlaps from YAML extents {overlaps or ''}")

    print()
    if FAILS:
        print(f"GEOMETRY GATE: {len(FAILS)} FAILURE(S)")
        return 1
    print("GEOMETRY GATE: ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
