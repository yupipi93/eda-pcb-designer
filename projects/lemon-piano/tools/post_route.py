#!/usr/bin/env python3
"""Post-route pass for the Lemon Piano board (runs in the Docker image).

The cloud `/route` endpoint routes every net at the stateless default
0.2 mm (netclasses live in the project file, which the API never sees).
This pass enforces the YAML routing widths afterwards, WITHOUT creating
clearance violations (DECISIONS.md ADR-008):

  1. drop freerouting's sub-0.1 mm junk segments (LESSONS_LEARNED §2);
  2. clearance-aware widening: each segment is widened to its target
     (power nets → `trace_width_power`, others → `trace_width_signal`)
     but capped so that 0.2 mm copper clearance to every other-net pad,
     track and via — and 0.3 mm to the board edge — is preserved. The
     cap is computed from the freerouting CENTERLINES and the *target*
     widths of neighbours (one-shot, order-independent → idempotent).
     Floor = 0.2 mm (CONVENTIONS §7 minimum, always DRC-clean).
  3. re-run the ZONE_FILLER so the B.Cu GND fill honours the new widths
     (fills are stored in the file; /drc does not refill).

Usage:
    docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
        -v "$PWD":/work -w /work --entrypoint python3 \
        eda-pcb-designer:latest projects/lemon-piano/tools/post_route.py <pcb>
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pcbnew
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

from pcb_designer.kicad_pcb_io import remove_tiny_segments  # noqa: E402

CFG_PATH = REPO_ROOT / "projects" / "lemon-piano" / "lemon-piano.yaml"
POWER_NETS = {"/+5V", "/GND", "/VIN", "/VRAW"}
COPPER_CLEARANCE = 0.2   # mm, CONVENTIONS §7
EDGE_CLEARANCE = 0.3     # mm, CONVENTIONS §7


def seg_point_dist(ax, ay, bx, by, px, py) -> float:
    """Distance from point P to segment AB (mm)."""
    abx, aby = bx - ax, by - ay
    l2 = abx * abx + aby * aby
    if l2 == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * abx + (py - ay) * aby) / l2))
    return math.hypot(px - (ax + t * abx), py - (ay + t * aby))


def seg_rect_dist(ax, ay, bx, by, rx0, ry0, rx1, ry1) -> float:
    """Distance from segment AB to axis-aligned rect (0 if intersecting)."""
    steps = max(2, int(math.hypot(bx - ax, by - ay) / 0.05))
    best = float("inf")
    for i in range(steps + 1):
        t = i / steps
        px, py = ax + t * (bx - ax), ay + t * (by - ay)
        dx = max(rx0 - px, 0.0, px - rx1)
        dy = max(ry0 - py, 0.0, py - ry1)
        best = min(best, math.hypot(dx, dy))
        if best == 0.0:
            return 0.0
    return best


def seg_seg_dist(a, b) -> float:
    """Distance between two segments given as (x1,y1,x2,y2)."""
    ax, ay, bx, by = a
    cx, cy, dx, dy = b
    if _segs_intersect(ax, ay, bx, by, cx, cy, dx, dy):
        return 0.0
    return min(seg_point_dist(ax, ay, bx, by, cx, cy),
               seg_point_dist(ax, ay, bx, by, dx, dy),
               seg_point_dist(cx, cy, dx, dy, ax, ay),
               seg_point_dist(cx, cy, dx, dy, bx, by))


def _segs_intersect(ax, ay, bx, by, cx, cy, dx, dy) -> bool:
    def ccw(x1, y1, x2, y2, x3, y3):
        return (y3 - y1) * (x2 - x1) - (y2 - y1) * (x3 - x1)
    d1 = ccw(cx, cy, dx, dy, ax, ay)
    d2 = ccw(cx, cy, dx, dy, bx, by)
    d3 = ccw(ax, ay, bx, by, cx, cy)
    d4 = ccw(ax, ay, bx, by, dx, dy)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def main() -> None:
    pcb = Path(sys.argv[1] if len(sys.argv) > 1
               else REPO_ROOT / "projects/lemon-piano/kicad/lemon-piano.kicad_pcb")
    cfg = yaml.safe_load(CFG_PATH.read_text(encoding="utf-8"))
    w_sig = float(cfg["routing"]["trace_width_signal"])
    w_pow = float(cfg["routing"]["trace_width_power"])
    geom = cfg["geometry"]["pcb"]

    txt = pcb.read_text(encoding="utf-8")
    txt, n_tiny = remove_tiny_segments(txt)
    if n_tiny:
        print(f"  removed {n_tiny} tiny segment(s)")
    pcb.write_text(txt, encoding="utf-8")

    board = pcbnew.LoadBoard(str(pcb))

    # dangling-spur cleanup (non-GND nets; GND legitimately ends in the zone).
    # A segment end is "connected" if it lands on a same-net pad, via, or
    # another same-net track. Iterate to a fixed point.
    removed = 0
    while True:
        tracks = [t for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"]
        all_vias = [t for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]
        pad_list = []
        for fp in board.GetFootprints():
            for pad in fp.Pads():
                bb = pad.GetBoundingBox()
                pad_list.append((pad.GetNetname(),
                                 (bb.GetLeft() / 1e6 - 0.01, bb.GetTop() / 1e6 - 0.01,
                                  bb.GetRight() / 1e6 + 0.01, bb.GetBottom() / 1e6 + 0.01)))

        def end_connected(t, px, py):
            net = t.GetNetname()
            for pnet, (x0, y0, x1, y1) in pad_list:
                if pnet == net and x0 <= px <= x1 and y0 <= py <= y1:
                    return True
            for v in all_vias:
                if v.GetNetname() != net:
                    continue
                vp = v.GetPosition()
                if math.hypot(vp.x / 1e6 - px, vp.y / 1e6 - py) <= v.GetWidth() / 2e6 + 0.01:
                    return True
            for o in tracks:
                if o is t or o.GetNetname() != net or o.GetLayer() != t.GetLayer():
                    continue
                s, e = o.GetStart(), o.GetEnd()
                if seg_point_dist(s.x / 1e6, s.y / 1e6, e.x / 1e6, e.y / 1e6,
                                  px, py) <= o.GetWidth() / 2e6 + 0.01:
                    return True
            return False

        dangling = []
        for t in tracks:
            if t.GetNetname() == "/GND":
                continue
            s, e = t.GetStart(), t.GetEnd()
            if (not end_connected(t, s.x / 1e6, s.y / 1e6)
                    or not end_connected(t, e.x / 1e6, e.y / 1e6)):
                dangling.append(t)
        if not dangling:
            break
        for t in dangling:
            print(f"  removed dangling {t.GetNetname()} spur "
                  f"({t.GetStart().x / 1e6:.2f},{t.GetStart().y / 1e6:.2f})")
            board.RemoveNative(t)
            removed += 1
    if removed:
        pcbnew.SaveBoard(str(pcb), board)
        board = pcbnew.LoadBoard(str(pcb))

    def target(netname: str) -> float:
        return w_pow if netname in POWER_NETS else w_sig

    # obstacle inventories --------------------------------------------------
    pads = []                                # (layers, net, rect)
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            bb = pad.GetBoundingBox()
            rect = (bb.GetLeft() / 1e6, bb.GetTop() / 1e6,
                    bb.GetRight() / 1e6, bb.GetBottom() / 1e6)
            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_SMD:
                layers = {pad.GetLayer()}
            else:
                layers = {pcbnew.F_Cu, pcbnew.B_Cu}
            pads.append((layers, pad.GetNetname(), rect))

    def via_width(v) -> float:
        try:
            return v.GetWidth(pcbnew.B_Cu) / 1e6
        except TypeError:
            return v.GetWidth() / 1e6

    segs, vias = [], []
    for t in board.GetTracks():
        cls = t.GetClass()
        s, e = t.GetStart(), t.GetEnd()
        if cls == "PCB_TRACK":
            segs.append((t, t.GetLayer(), t.GetNetname(),
                         (s.x / 1e6, s.y / 1e6, e.x / 1e6, e.y / 1e6)))
        elif cls == "PCB_VIA":
            vias.append((t.GetNetname(), s.x / 1e6, s.y / 1e6, via_width(t)))

    # one-shot width solve --------------------------------------------------
    n_full = n_capped = 0
    for t, layer, net, line in segs:
        tw = target(net)
        cap = tw
        ax, ay, bx, by = line
        # board edge
        edge_d = min(ax - geom["x0"], geom["x1"] - ax, ay - geom["y0"],
                     geom["y1"] - ay, bx - geom["x0"], geom["x1"] - bx,
                     by - geom["y0"], geom["y1"] - by)
        cap = min(cap, 2 * (edge_d - EDGE_CLEARANCE))
        # other-net pads on this layer
        for layers, pnet, rect in pads:
            if pnet == net or layer not in layers:
                continue
            d = seg_rect_dist(ax, ay, bx, by, *rect)
            cap = min(cap, 2 * (d - COPPER_CLEARANCE))
        # other-net vias
        for vnet, vx, vy, vw in vias:
            if vnet == net:
                continue
            d = seg_point_dist(ax, ay, bx, by, vx, vy) - vw / 2
            cap = min(cap, 2 * (d - COPPER_CLEARANCE))
        # other-net tracks on this layer (both at their targets)
        for t2, layer2, net2, line2 in segs:
            if net2 == net or layer2 != layer:
                continue
            d = seg_seg_dist(line, line2)
            cap = min(cap, 2 * (d - COPPER_CLEARANCE) - target(net2))
        w = max(0.2, min(tw, math.floor(cap * 1000) / 1000))
        t.SetWidth(int(round(w * 1e6)))
        if w >= tw - 1e-9:
            n_full += 1
        else:
            n_capped += 1
            print(f"  capped {net} segment at ({ax:.2f},{ay:.2f}) "
                  f"to {w:.3f} mm (target {tw})")
    print(f"  widened {n_full} segment(s) to target, {n_capped} capped")

    filler = pcbnew.ZONE_FILLER(board)
    zones = list(board.Zones())
    filler.Fill(zones)
    print(f"  refilled {len(zones)} zone(s)")

    heal_zone_islands(board, filler, zones)

    pcbnew.SaveBoard(str(pcb), board)
    print(f"  saved {pcb}")


def heal_zone_islands(board, filler, zones) -> None:
    """LESSONS_LEARNED §12, automated: freerouting occasionally fences off a
    part of the B.Cu GND fill (fill needs min_thickness + clearance where a
    plain track only needs clearance). Detect islands, lay a short B.Cu GND
    stitch track across the narrowest pinch between the island and the main
    fill, refill, repeat. Aborts loudly if an island cannot be healed."""
    gnd = board.FindNet("/GND")

    def outlines():
        poly = zones[0].GetFilledPolysList(pcbnew.B_Cu)
        outs = []
        for i in range(poly.OutlineCount()):
            ch = poly.Outline(i)
            pts = [(ch.CPoint(k).x / 1e6, ch.CPoint(k).y / 1e6)
                   for k in range(ch.PointCount())]
            bb = ch.BBox()
            outs.append((bb.GetWidth() / 1e6 * bb.GetHeight() / 1e6, pts))
        return sorted(outs, key=lambda o: -o[0])

    def clear_of_others(x1, y1, x2, y2, w) -> bool:
        need = w / 2 + 0.2
        for fp in board.GetFootprints():
            for pad in fp.Pads():
                if pad.GetNetname() == "/GND":
                    continue
                if (pad.GetAttribute() == pcbnew.PAD_ATTRIB_SMD
                        and pad.GetLayer() != pcbnew.B_Cu):
                    continue
                bb = pad.GetBoundingBox()
                if seg_rect_dist(x1, y1, x2, y2, bb.GetLeft() / 1e6, bb.GetTop() / 1e6,
                                 bb.GetRight() / 1e6, bb.GetBottom() / 1e6) < need:
                    return False
        for t in board.GetTracks():
            if t.GetNetname() == "/GND":
                continue
            s, e = t.GetStart(), t.GetEnd()
            if t.GetClass() == "PCB_VIA":
                if (seg_point_dist(x1, y1, x2, y2, s.x / 1e6, s.y / 1e6)
                        < need + t.GetDrillValue() / 2e6 + 0.15):
                    return False
            elif t.GetLayer() == pcbnew.B_Cu:
                if (seg_seg_dist((x1, y1, x2, y2),
                                 (s.x / 1e6, s.y / 1e6, e.x / 1e6, e.y / 1e6))
                        < need + t.GetWidth() / 2e6):
                    return False
        return True

    for attempt in range(8):
        outs = outlines()
        if len(outs) <= 1:
            if attempt:
                print(f"  zone islands healed ({attempt} stitch(es))")
            return
        main_pts = outs[0][1]
        island_pts = outs[1][1]
        pairs = sorted(((math.hypot(ax - bx, ay - by), ax, ay, bx, by)
                        for ax, ay in island_pts for bx, by in main_pts),
                       key=lambda p: p[0])
        placed = False
        for d, ax, ay, bx, by in pairs[:400]:
            if d > 10.0:
                break
            if not clear_of_others(ax, ay, bx, by, 0.3):
                continue
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(int(ax * 1e6), int(ay * 1e6)))
            t.SetEnd(pcbnew.VECTOR2I(int(bx * 1e6), int(by * 1e6)))
            t.SetWidth(int(0.3 * 1e6))
            t.SetLayer(pcbnew.B_Cu)
            t.SetNet(gnd)
            board.Add(t)
            filler.Fill(zones)
            print(f"  stitched zone island: ({ax:.2f},{ay:.2f})->({bx:.2f},{by:.2f})")
            placed = True
            break
        if not placed:
            raise SystemExit(f"zone island could not be healed "
                             f"({len(outs)} fill fragments remain)")
    raise SystemExit("zone island healing did not converge in 8 attempts")


if __name__ == "__main__":
    main()
