#!/usr/bin/env python3
"""Build the Lemon Piano V5.5 base `.kicad_pcb` from `lemon-piano.yaml`.

Generative step with no cloud endpoint (AGENTS.md: footprint instantiation
is done headlessly with pcbnew inside the eda-pcb-designer Docker image):

    docker run --rm --entrypoint python3 -v "$PWD":/work -w /work \
        eda-pcb-designer:latest projects/lemon-piano/tools/build_board.py

What it does (single source of truth = the YAML + docs/NETLIST.md):
  1. Creates a fresh board, declares the 34 nets in the YAML's numeric order
     (asserts the resulting KiCad net codes match `nets.numbers`).
  2. Loads every footprint from the system KiCad 9 libraries, places it at
     the YAML `placements` coords (same rot/layer semantics as the cloud
     `/place` endpoint = `pcb_designer.placement.place_and_flip`).
  3. Assigns pad nets per NETLIST.md. For the vertical 0805 resistors the
     signal pad is chosen GEOMETRICALLY (north pad = signal, south = rail)
     so a pcbnew flip/rot convention change can never silently swap them —
     an explicit assertion then locks the outcome.
  4. Board outline (Edge.Cuts), anchor silk dividers, title + service-edge
     labels (regenerated from config every run, LESSONS_LEARNED §18).
  5. Text post-passes: B.Cu GND zone block (MT1 template, LESSONS_LEARNED
     §1/§3/§16), then a deterministic-UUID rewrite so re-runs are
     byte-identical (LESSONS_LEARNED §7). Each object still gets a unique
     UUID — never reused across objects.

Idempotency contract: running twice yields a byte-identical file. The
previous file (if different) is snapshotted to `<file>.bak6` first.
"""
from __future__ import annotations

import hashlib
import re
import sys
import uuid
from pathlib import Path

import pcbnew
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

CFG_PATH = REPO_ROOT / "projects" / "lemon-piano" / "lemon-piano.yaml"
FP_LIB = "/usr/share/kicad/footprints/{}.pretty"

MM = pcbnew.FromMM


def V(x_mm: float, y_mm: float) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(int(round(x_mm * 1e6)), int(round(y_mm * 1e6)))


# ── static tables (docs/NETLIST.md) ──────────────────────────────────────────

FOOTPRINTS: dict[str, tuple[str, str, str]] = {
    # ref: (library, footprint, value)
    "U1": ("Connector_PinSocket_2.54mm", "PinSocket_1x15_P2.54mm_Vertical", "Nano_socket_A"),
    "U2": ("Connector_PinSocket_2.54mm", "PinSocket_1x15_P2.54mm_Vertical", "Nano_socket_B"),
    "J1": ("TerminalBlock_Phoenix",
           "TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal", "5V_IN"),
    "J2": ("Connector_PinHeader_2.54mm", "PinHeader_1x08_P2.54mm_Vertical", "LEMON_KEYS"),
    "D1": ("Diode_THT", "D_DO-15_P5.08mm_Vertical_KathodeUp", "P6KE6.8A"),
    "D2": ("Diode_THT", "D_DO-41_SOD81_P5.08mm_Vertical_AnodeUp", "1N5817"),
    "C1": ("Capacitor_THT", "CP_Radial_D8.0mm_P3.50mm", "470uF/16V"),
    "C3": ("Capacitor_THT", "CP_Radial_D8.0mm_P3.50mm", "470uF/16V"),
    "C2": ("Capacitor_SMD", "C_0805_2012Metric_Pad1.18x1.45mm_HandSolder", "100nF"),
    "C4": ("Capacitor_SMD", "C_0805_2012Metric_Pad1.18x1.45mm_HandSolder", "100nF"),
    "L1": ("Inductor_THT", "L_Radial_D8.7mm_P5.00mm_Fastron_07HCP", "100uH"),
    "BUZ1": ("Buzzer_Beeper", "Buzzer_12x9.5RM7.6", "passive_buzzer"),
    "SW1": ("Button_Switch_THT", "SW_PUSH_6mm", "SENS+"),
    "SW2": ("Button_Switch_THT", "SW_PUSH_6mm", "SENS-"),
    "H1": ("MountingHole", "MountingHole_2.5mm_Pad_Via", "M2"),
    "H2": ("MountingHole", "MountingHole_2.5mm_Pad_Via", "M2"),
}
for _i in range(10):                       # D3..D12 = LED1..LED10
    FOOTPRINTS[f"D{_i + 3}"] = ("LED_THT", "LED_D3.0mm", f"GREEN_LED{_i + 1}")
for _i in range(1, 8):                     # key pull-ups
    FOOTPRINTS[f"R{_i}"] = ("Resistor_SMD",
                            "R_0805_2012Metric_Pad1.20x1.40mm_HandSolder", "220")
for _i in range(8, 18):                    # LED series
    FOOTPRINTS[f"R{_i}"] = ("Resistor_SMD",
                            "R_0805_2012Metric_Pad1.20x1.40mm_HandSolder", "220")
FOOTPRINTS["R18"] = ("Resistor_SMD",
                     "R_0805_2012Metric_Pad1.20x1.40mm_HandSolder", "10k")

# pad → net, by pad number (geometric parts R1..R18 handled separately)
PAD_NETS: dict[tuple[str, str], str] = {
    ("U1", "4"): "GND",
    ("U1", "5"): "LED1", ("U1", "6"): "LED2", ("U1", "7"): "LED3",
    ("U1", "8"): "LED4", ("U1", "9"): "LED5", ("U1", "10"): "LED6",
    ("U1", "11"): "LED7", ("U1", "12"): "LED8", ("U1", "13"): "LED9",
    ("U1", "14"): "LED10", ("U1", "15"): "SENS_PLUS",
    ("U2", "1"): "BUZZER",
    ("U2", "4"): "KEY1", ("U2", "5"): "KEY2", ("U2", "6"): "KEY3",
    ("U2", "7"): "KEY4", ("U2", "8"): "KEY5", ("U2", "9"): "KEY6",
    ("U2", "10"): "KEY7", ("U2", "11"): "SENS_MINUS",
    ("U2", "12"): "+5V", ("U2", "14"): "GND",
    ("J1", "1"): "VIN", ("J1", "2"): "GND",
    ("J2", "1"): "GND",
    ("J2", "2"): "KEY7", ("J2", "3"): "KEY6", ("J2", "4"): "KEY5",
    ("J2", "5"): "KEY4", ("J2", "6"): "KEY3", ("J2", "7"): "KEY2",
    ("J2", "8"): "KEY1",
    ("D1", "1"): "VIN", ("D1", "2"): "GND",
    ("D2", "1"): "VRAW", ("D2", "2"): "VIN",
    ("C1", "1"): "VRAW", ("C1", "2"): "GND",
    ("C2", "1"): "VRAW", ("C2", "2"): "GND",
    ("L1", "1"): "VRAW", ("L1", "2"): "+5V",
    ("C3", "1"): "+5V", ("C3", "2"): "GND",
    ("C4", "1"): "+5V", ("C4", "2"): "GND",
    ("BUZ1", "1"): "BUZZER", ("BUZ1", "2"): "GND",
    ("SW1", "1"): "SENS_PLUS", ("SW1", "2"): "GND",
    ("SW2", "1"): "SENS_MINUS", ("SW2", "2"): "GND",
    ("H1", "1"): "GND", ("H2", "1"): "GND",
}
for _i in range(10):                       # LED pads: 1=cathode, 2=anode
    PAD_NETS[(f"D{_i + 3}", "1")] = f"LED{_i + 1}_K"
    PAD_NETS[(f"D{_i + 3}", "2")] = f"LED{_i + 1}"

# vertical 0805s: (north-pad net, south-pad net) — north = smaller y
GEOMETRIC_NETS: dict[str, tuple[str, str]] = {}
for _i in range(1, 8):                     # pull-up: pin side north, +5V south
    GEOMETRIC_NETS[f"R{_i}"] = (f"KEY{_i}", "+5V")
GEOMETRIC_NETS["R18"] = ("SENS_MINUS", "+5V")
for _i in range(8, 18):                    # LED series: cathode north, GND south
    GEOMETRIC_NETS[f"R{_i}"] = (f"LED{_i - 7}_K", "GND")

# Every GND pad merges solid with the B.Cu zone (zone_connect 2,
# LESSONS_LEARNED §1). v0.0.2 DRC proved the SMD GND pads of R8..R17
# starve on thermal reliefs in the packed LED strip (spokes 1 < 2).

# expected pad positions (mm) — hard assertions against rot/flip surprises
EXPECTED_PADS = [
    ("U1", "1", 104.0, 122.62), ("U1", "15", 139.56, 122.62),
    ("U2", "1", 139.56, 107.38), ("U2", "15", 104.0, 107.38),
    ("J2", "1", 114.16, 103.0), ("J2", "8", 131.94, 103.0),
    ("J1", "1", 170.0, 105.9), ("J1", "2", 175.08, 105.9),
    ("D1", "1", 159.3, 103.8), ("D1", "2", 164.38, 103.8),
    ("D2", "1", 150.0, 103.8), ("D2", "2", 155.08, 103.8),
    ("C1", "1", 159.5, 116.0), ("C1", "2", 163.0, 116.0),
    ("L1", "1", 170.0, 116.0), ("L1", "2", 175.0, 116.0),
    ("C3", "1", 171.3, 125.4), ("C3", "2", 174.8, 125.4),
    ("BUZ1", "1", 146.5, 114.2), ("BUZ1", "2", 154.1, 114.2),
    ("D3", "1", 103.5, 128.3), ("D3", "2", 103.5, 125.76),
    ("D12", "1", 144.9, 128.3), ("D12", "2", 144.9, 125.76),
    ("H1", "1", 95.0, 115.0), ("H2", "1", 185.0, 115.0),
]

# hide silk references on the dense small parts (silk stays readable);
# the F.Fab layer keeps every ref for the fab/assembly docs.
HIDE_REF = ({f"D{i}" for i in range(3, 13)} | {f"R{i}" for i in range(1, 19)}
            | {"C2", "C4", "H1", "H2"})


def build(cfg: dict) -> str:
    geom = cfg["geometry"]["pcb"]
    version = cfg["project"]["version"]
    net_numbers: dict[str, int] = cfg["nets"]["numbers"]
    placements: dict[str, list] = cfg["placements"]

    board = pcbnew.CreateEmptyBoard()

    # design rules that live in the board file (CONVENTIONS §7)
    bds = board.GetDesignSettings()
    bds.m_TrackMinWidth = MM(0.2)
    bds.m_MinClearance = MM(0.2)
    bds.m_ViasMinSize = MM(0.6)
    bds.m_MinThroughDrill = MM(0.3)
    bds.m_CopperEdgeClearance = MM(0.3)

    # ── nets, in YAML numeric order ──────────────────────────────────────
    for name, num in sorted(net_numbers.items(), key=lambda kv: kv[1]):
        board.Add(pcbnew.NETINFO_ITEM(board, f"/{name}"))
        got = board.FindNet(f"/{name}").GetNetCode()
        if got != num:
            raise SystemExit(f"net {name}: expected code {num}, got {got}")

    # ── footprints ───────────────────────────────────────────────────────
    for ref in placements:
        lib, fpname, value = FOOTPRINTS[ref]
        fp = pcbnew.FootprintLoad(FP_LIB.format(lib), fpname)
        if fp is None:
            raise SystemExit(f"footprint not found: {lib}:{fpname}")
        fp.SetReference(ref)
        fp.SetValue(value)
        board.Add(fp)

        x, y, rot, layer = placements[ref]
        fp.SetPosition(V(x, y))
        if layer == "B.Cu":
            try:
                fp.Flip(V(x, y), True)
            except TypeError:
                fp.Flip(V(x, y), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        fp.SetOrientationDegrees(rot)

        ref_field = fp.Reference()
        if ref in HIDE_REF:
            ref_field.SetVisible(False)
        else:
            ref_field.SetTextSize(pcbnew.VECTOR2I(MM(0.8), MM(0.8)))
            ref_field.SetTextThickness(MM(0.13))
        fp.Value().SetVisible(False)

        # net assignment
        pads = list(fp.Pads())
        if ref in GEOMETRIC_NETS:
            north_net, south_net = GEOMETRIC_NETS[ref]
            a, b = pads
            north, south = (a, b) if a.GetPosition().y < b.GetPosition().y else (b, a)
            north.SetNet(board.FindNet(f"/{north_net}"))
            south.SetNet(board.FindNet(f"/{south_net}"))
        else:
            for pad in pads:
                net = PAD_NETS.get((ref, pad.GetNumber()))
                if net is not None:
                    pad.SetNet(board.FindNet(f"/{net}"))
        for pad in pads:
            if pad.GetNetname() == "/GND":
                pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)

    # reposition the visible refs into free silk pockets (v0.0.4: positions
    # tuned until /drc reports zero silk_overlap)
    for ref, (tx, ty, trot) in {"U1": (121.8, 120.7, 0),
                                "U2": (121.8, 109.3, 0),
                                "BUZ1": (150.3, 111.5, 0),
                                "J1": (167.0, 111.5, 0),
                                "J2": (109.0, 103.0, 0),
                                "D1": (161.84, 107.0, 0),
                                "D2": (152.54, 107.0, 0),
                                "C1": (161.16, 111.2, 0),
                                "C3": (178.3, 125.4, 90),
                                "L1": (178.9, 116.0, 90)}.items():
        fp = board.FindFootprintByReference(ref)
        r = fp.Reference()
        r.SetPosition(V(tx, ty))
        r.SetTextAngleDegrees(trot)
    for ref in ("SW1", "SW2"):   # the SENS+/SENS- silk labels identify them
        board.FindFootprintByReference(ref).Reference().SetVisible(False)

    # ── pad-position assertions ──────────────────────────────────────────
    for ref, num, ex, ey in EXPECTED_PADS:
        fp = board.FindFootprintByReference(ref)
        cands = [p.GetPosition() for p in fp.Pads() if p.GetNumber() == num]
        if not any(abs(p.x / 1e6 - ex) <= 0.01 and abs(p.y / 1e6 - ey) <= 0.01
                   for p in cands):
            got = ", ".join(f"({p.x / 1e6:.3f},{p.y / 1e6:.3f})" for p in cands)
            raise SystemExit(f"PAD ASSERTION FAILED {ref}.{num}: "
                             f"[{got}] != ({ex},{ey})")
    # SW pads: both "1" pads north (y=123.4), both "2" pads south (y=127.9)
    for ref in ("SW1", "SW2"):
        fp = board.FindFootprintByReference(ref)
        for pad in fp.Pads():
            want_y = 123.4 if pad.GetNumber() == "1" else 127.9
            if abs(pad.GetPosition().y / 1e6 - want_y) > 0.01:
                raise SystemExit(f"PAD ASSERTION FAILED {ref} pad "
                                 f"{pad.GetNumber()} y != {want_y}")
    # geometric resistors: KEY pad must be the one nearer its A-pin row
    for i in range(1, 8):
        fp = board.FindFootprintByReference(f"R{i}")
        for pad in fp.Pads():
            if pad.GetNetname() == f"/KEY{i}":
                if abs(pad.GetPosition().y / 1e6 - 109.6) > 0.05:
                    raise SystemExit(f"R{i} KEY pad not at y=109.6")

    # ── board outline ────────────────────────────────────────────────────
    rect = pcbnew.PCB_SHAPE(board)
    rect.SetShape(pcbnew.SHAPE_T_RECT)
    rect.SetStart(V(geom["x0"], geom["y0"]))
    rect.SetEnd(V(geom["x1"], geom["y1"]))
    rect.SetLayer(pcbnew.Edge_Cuts)
    rect.SetWidth(MM(0.1))
    board.Add(rect)

    # anchor silk dividers (MT1 style; inset so they don't touch Edge.Cuts)
    for ax in (cfg["geometry"]["anchors"]["left_x"],
               cfg["geometry"]["anchors"]["right_x"]):
        ln = pcbnew.PCB_SHAPE(board)
        ln.SetShape(pcbnew.SHAPE_T_SEGMENT)
        ln.SetStart(V(ax, geom["y0"] + 0.35))
        ln.SetEnd(V(ax, geom["y1"] - 0.35))
        ln.SetLayer(pcbnew.F_SilkS)
        ln.SetWidth(MM(0.15))
        board.Add(ln)

    # ── silk texts (regenerated every run from config) ───────────────────
    def text(s: str, x: float, y: float, layer=pcbnew.F_SilkS,
             h: float = 0.8, rot: float = 0.0, thick: float = 0.13):
        t = pcbnew.PCB_TEXT(board)
        t.SetText(s)
        t.SetPosition(V(x, y))
        t.SetLayer(layer)
        t.SetTextSize(pcbnew.VECTOR2I(MM(h), MM(h)))
        t.SetTextThickness(MM(thick))
        t.SetTextAngleDegrees(rot)
        if layer in (pcbnew.B_SilkS, pcbnew.B_Cu, pcbnew.B_Mask):
            t.SetMirrored(True)
        board.Add(t)

    text("LEMON PIANO V5.5", 140.0, 101.15, h=0.8)
    text(version, 130.5, 120.55, h=0.8)
    # keys header labels: pin1=GND then KEY7..KEY1 (west→east)
    for i, lab in enumerate(["G", "7", "6", "5", "4", "3", "2", "1"]):
        text(lab, 114.16 + 2.54 * i, 100.95, h=0.8)
    text("KEYS", 109.0, 100.95, h=0.8)
    text("+", 170.0, 109.4, h=1.0, thick=0.15)
    text("-", 175.08, 109.4, h=1.0, thick=0.15)
    text("5V IN", 178.8, 105.9, h=0.8, rot=90)
    text("SENS+", 152.95, 121.3, h=0.8)
    text("SENS-", 163.15, 121.3, h=0.8)
    text("1", 100.9, 128.3, h=0.8)
    text("10", 146.4, 124.0, h=0.8)
    text("Lemon Piano V5.5", 127.0, 116.5, layer=pcbnew.B_SilkS, h=1.0)
    text(version, 127.0, 119.0, layer=pcbnew.B_SilkS, h=1.0)

    # ── save + text post-passes ──────────────────────────────────────────
    out_dir = REPO_ROOT / cfg["project"]["kicad_project_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / cfg["project"]["kicad_pcb_file"]
    tmp = out.parent / ".build-tmp.kicad_pcb"
    if not pcbnew.SaveBoard(str(tmp), board):
        raise SystemExit(f"pcbnew.SaveBoard failed for {tmp}")
    txt = tmp.read_text(encoding="utf-8")
    tmp.unlink()
    for side in (".build-tmp.kicad_prl", ".build-tmp.kicad_pro"):
        (out.parent / side).unlink(missing_ok=True)

    txt = sort_footprint_blocks(txt)
    txt = inject_gnd_zone(txt, geom, net_numbers["GND"])
    txt = deterministic_uuids(txt)
    return persist(out, txt)


def sort_footprint_blocks(text: str) -> str:
    """pcbnew serialises footprints / texts / shapes ordered by their
    (random) creation UUIDs, which would defeat byte-stability. Re-order
    every movable top-level block canonically: footprints by reference
    (natural sort), then graphics/zones by uuid-stripped content. The
    fixed header blocks (version, generator, general, paper, layers,
    setup, net declarations) keep pcbnew's order."""
    # split (kicad_pcb ...) into depth-1 child blocks
    root = text.find("(kicad_pcb")
    children: list[tuple[str, str]] = []   # (keyword, block text)
    i = root + len("(kicad_pcb")
    depth = 1
    start = None
    while i < len(text) and depth > 0:
        ch = text[i]
        if ch == '"':                      # skip strings
            i += 1
            while i < len(text) and text[i] != '"':
                i += 2 if text[i] == "\\" else 1
        elif ch == "(":
            if depth == 1:
                start = i
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 1 and start is not None:
                block = text[start:i + 1]
                kw = re.match(r"\((\S+)", block).group(1)
                children.append((kw, block))
                start = None
        i += 1

    header_kws = {"version", "generator", "generator_version", "general",
                  "paper", "layers", "setup", "net", "property"}
    header = [b for kw, b in children if kw in header_kws]
    fps = [b for kw, b in children if kw == "footprint"]
    rest = [(kw, b) for kw, b in children
            if kw not in header_kws and kw != "footprint"]

    def natkey(block: str):
        m = re.search(r'\(property\s+"Reference"\s+"([A-Za-z]+)(\d+)"', block)
        return (m.group(1), int(m.group(2))) if m else ("~", 0)

    fps = [_sort_children(b) for b in sorted(fps, key=natkey)]
    stripped = re.compile(r'\(uuid "[0-9a-fA-F-]+"\)')
    rest.sort(key=lambda kb: (kb[0], stripped.sub("", kb[1])))

    body = "\n\t".join(header + fps + [b for _, b in rest])
    return text[:root] + "(kicad_pcb\n\t" + body + "\n)\n"


# pads keep pcbnew's stable serialisation order (library order — the
# verify.holes parser expects the main pad first); only the graphic
# children shuffle with their random UUIDs and need canonical sorting.
_MOVABLE_FP_KWS = {"fp_text", "fp_line", "fp_arc", "fp_circle", "fp_rect",
                   "fp_poly"}
_UUID_RE = re.compile(r'\(uuid "[0-9a-fA-F-]+"\)')


def _sort_children(block: str) -> str:
    """pcbnew also serialises a footprint's own children (fp_text, fp_line,
    pads...) in random-UUID order. Sort the movable ones by uuid-stripped
    content and pour them back into their original slots, so the category
    layout (properties → graphics → pads → model) is preserved."""
    open_end = block.find("\n")
    spans = []
    i = open_end
    depth = 1
    start = None
    while i < len(block):
        ch = block[i]
        if ch == '"':
            i += 1
            while i < len(block) and block[i] != '"':
                i += 2 if block[i] == "\\" else 1
        elif ch == "(":
            if depth == 1:
                start = i
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 1 and start is not None:
                spans.append((start, i + 1))
                start = None
            elif depth == 0:
                break
        i += 1

    children = [(re.match(r"\((\S+)", block[a:b]).group(1), a, b)
                for a, b in spans]
    movable = sorted((block[a:b] for kw, a, b in children
                      if kw in _MOVABLE_FP_KWS),
                     key=lambda c: (re.match(r"\((\S+)", c).group(1),
                                    _UUID_RE.sub("", c)))
    out = []
    last = open_end
    mi = iter(movable)
    for kw, a, b in children:
        out.append(block[last:a])
        out.append(next(mi) if kw in _MOVABLE_FP_KWS else block[a:b])
        last = b
    out.append(block[last:])
    return block[:open_end] + "".join(out)


def inject_gnd_zone(text: str, geom: dict, gnd_num: int) -> str:
    """B.Cu GND zone over the whole board (MT1 template: LESSONS_LEARNED
    §1/§3; no min_resolved_spokes anywhere near (fill ...), §16). The fill
    polygon itself is computed by the /route stage's ZONE_FILLER."""
    if '(net_name "/GND")' in text and "(zone" in text:
        return text
    zone = f'''\t(zone
\t\t(net {gnd_num})
\t\t(net_name "/GND")
\t\t(layer "B.Cu")
\t\t(uuid "00000000-0000-4000-8000-000000000000")
\t\t(hatch edge 0.5)
\t\t(connect_pads
\t\t\t(clearance 0.2)
\t\t)
\t\t(min_thickness 0.2)
\t\t(filled_areas_thickness no)
\t\t(fill yes
\t\t\t(thermal_gap 0.5)
\t\t\t(thermal_bridge_width 0.5)
\t\t)
\t\t(polygon
\t\t\t(pts
\t\t\t\t(xy {geom["x0"]} {geom["y0"]}) (xy {geom["x1"]} {geom["y0"]})
\t\t\t\t(xy {geom["x1"]} {geom["y1"]}) (xy {geom["x0"]} {geom["y1"]})
\t\t\t)
\t\t)
\t)'''
    final_paren = text.rstrip().rfind(")")
    return text[:final_paren] + "\n" + zone + "\n" + text[final_paren:]


def deterministic_uuids(text: str) -> str:
    """Rewrite every (uuid "...") with a deterministic, per-object-unique
    sequence so re-runs are byte-identical (LESSONS_LEARNED §7). UUIDs are
    never shared between objects — uniqueness comes from the counter."""
    ns = uuid.uuid5(uuid.NAMESPACE_DNS, "lemon-piano.pcb-designer")
    counter = [0]

    def sub(_m):
        counter[0] += 1
        return f'(uuid "{uuid.uuid5(ns, f"obj-{counter[0]}")}")'

    return re.sub(r'\(uuid "[0-9a-fA-F-]+"\)', sub, text)


def persist(out: Path, txt: str) -> str:
    if out.exists():
        old = out.read_text(encoding="utf-8")
        if old == txt:
            print(f"  {out.name}: unchanged (byte-stable)")
            return "unchanged"
        bak = out.with_suffix(out.suffix + ".bak6")
        if not bak.exists():
            bak.write_text(old, encoding="utf-8")
            print(f"  snapshot -> {bak.name}")
    out.write_text(txt, encoding="utf-8")
    print(f"  wrote {out} ({hashlib.sha256(txt.encode()).hexdigest()[:12]})")
    return "written"


def main() -> None:
    cfg = yaml.safe_load(CFG_PATH.read_text(encoding="utf-8"))
    print(f"Building {cfg['project']['full_name']} "
          f"{cfg['project']['version']} base board...")
    build(cfg)
    print("Done.")


if __name__ == "__main__":
    main()
