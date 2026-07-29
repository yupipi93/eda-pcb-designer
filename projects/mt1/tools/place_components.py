#!/usr/bin/env python3
"""v0.0.12 layout for the MT1 PCB — MODULES-ONLY reset.

This iteration is a CLEAN SLATE for the placement exploration. Every
non-module footprint (power chain, UI, debug header, decoupling caps,
test points) is REMOVED from the .kicad_pcb so that only the
interconnected modules + structural mounting holes remain. See
`docs/REMOVED_COMPONENTS.md` for the full catalog and re-incorporation
guide.

Modules kept in placement (5 footprint instances + 6 mounting holes):
  U1, U5  XIAO ESP32S3 Plus  — paired 1x7 sockets, USB-C end at +Y
  U2      LSM6DSO32 IMU      — B.Cu, long axis along PCB X (rocket axis)
  U3      BMP585 barometer   — F.Cu
  U4      microSD            — F.Cu, SD slot end at +Y (service edge)
  H1..H4  right anchor 2x2   — structural mounting (M2)
  H5..H6  left anchor 1x2    — structural mounting (M2)

Layout rationale (TOP view, USB-C/SD facing y=130 long edge):

  y=100  ┌──────┬─────────────────────────────────────────────┬──────┐
         │      │ [U4 microSD]   [U3 BMP585]  [XIAO U1+U5]    │      │
         │ ANCH │   F.Cu rot=270   F.Cu rot=0   F.Cu rot=180  │ ANCH │
         │ LEFT │   slot to +Y     pads at left  USB-C to +Y  │ RIGHT│
         │ H5,H6│                                             │ H1..4│
  y=130  └──────┴─────────────────────────────────────────────┴──────┘
                  ↑                                  ↑
             SD slot                              USB-C
             (y=130 service edge)              (y=130 service edge)

  BOTTOM view (B.Cu):
         The IMU U2 lives under the U4 microSD region with its 25.4mm
         long axis along PCB X (rocket longitudinal). Its 1x9 pin row
         sits at y=127 (between the y=130 edge and the U4 pad row at
         y=108), giving cross-layer TH clearance.

Design decisions that drove this layout:
  - U4 and XIAO sit on TOP because they need USER ACCESS (SD slot,
    USB-C). Both have their service openings on the SAME long edge
    (y=130), as required by CONVENTIONS §8.
  - U2 LSM6 sits on BOTTOM with rot=90 so its 25.4mm body axis aligns
    with PCB X (rocket longitudinal axis) — IMU off-axis errors
    minimized. Cleared from U4 drill row and XIAO drill columns.
  - U3 BMP585 sits on TOP between U4 and XIAO. Its 17.78mm body width
    fits the 22.46mm gap between their breakout bodies, and its pin
    column at x=129 is well clear of all neighboring TH columns.
  - Right anchor (x>170) is now empty (power section removed) — only
    the H1-H4 mounting holes remain in that strip.
  - All three TOP modules cluster their pin rows toward the LEFT side
    of their respective breakout bodies, leaving X gaps of 1.5+ mm
    between hovering breakout bodies (no pin-header/body collisions).

Usage:
  1. (Optional) Run build_schematic.py if pinouts changed (NOT needed
     for this iteration — schematic is unchanged).
  2. (Optional) KiCad PCB Editor -> Tools -> Update PCB from Schematic
     (NOT needed — would re-add the removed components).
  3. python3 projects/mt1/tools/place_components.py
  4. Inspect renders under projects/mt1/renders/.

NOTE: this script is now a thin **MT1 orchestrator**. The algorithmic
helpers (`extract_footprint_block`, `force_pad_zone_connect`,
`remove_tiny_segments`, `LAYER_PAIRS`, `flip_to_back/_to_front`,
`place_and_flip`, `resize_outline`, `reposition_silk`, `_seg/_route_l/_route_u`,
`strip_3d_model_blocks`) live in the board-agnostic `pcb_designer.*`
package. This file binds MT1's `PLACEMENTS`, `KEEP_REFS`, `PIN_COUNT`,
`PAD_HALF`, `BODY_EXTENT`, `PIN_LOCAL_POSITIONS`, `TH_FOOTPRINTS`,
`NET_NUMBERS`, `VERSION_TAG` plus the v0.0.15 GND-zone definition and
the J4-header / 'Made on Earth' silk-label injections (which are
MT1-specific). See README.md §2 for the package vs orchestrator
split.
"""
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Make the pcb_designer package importable when this script is run directly
# (projects/mt1/tools/place_components.py is two levels below the repo root; the
# package lives at src/pcb_designer, three levels up from this tools/ dir).
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from pcb_designer.kicad_pcb_io import (  # noqa: E402  (sys.path tweak above)
    _extract_footprint_block,
    _strip_3d_model_blocks,
    remove_tiny_segments,
)
from pcb_designer.geometry import (  # noqa: E402
    resize_outline as _resize_outline_impl,
    reposition_silk as _reposition_silk_impl,
    make_title_silk,
    _rotate_cw,
)
from pcb_designer.placement import (  # noqa: E402
    _LAYER_PAIRS,
    _flip_footprint_block_to_back,
    _flip_footprint_block_to_front,
    place_and_flip as _place_and_flip_impl,
)
from pcb_designer.injection import (  # noqa: E402
    force_pad_zone_connect,
    remove_non_module_footprints as _remove_non_module_footprints_impl,
)
from pcb_designer.routing import (  # noqa: E402
    _seg,
    _route_l,
    _route_u,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
PROJ = REPO_ROOT / "projects" / "mt1" / "kicad"
PCB_PATH = PROJ / "mt1-pcb.kicad_pcb"
VAL = REPO_ROOT / "projects" / "mt1" / "validation"
RENDERS = REPO_ROOT / "projects" / "mt1" / "renders"

# ----------------------------------------------------------------------------
# PCB GEOMETRY: unchanged from v0.0.11
#   100 x 30 mm = 10mm left anchor + 70mm electronic + 20mm right anchor
# ----------------------------------------------------------------------------
PCB_X0, PCB_Y0 = 90.0, 100.0
PCB_X1, PCB_Y1 = 190.0, 130.0
LEFT_ANCHOR_X  = 100.0
RIGHT_ANCHOR_X = 170.0

# ----------------------------------------------------------------------------
# PLACEMENTS: (x_mm, y_mm, rotation_deg, layer)
# Only modules + mounting holes. Everything else is removed from the
# .kicad_pcb by `remove_non_module_footprints()`.
# ----------------------------------------------------------------------------
PLACEMENTS = {
    # ── Mounting holes ──
    "H1": (175, 105, 0, "F.Cu"),
    "H2": (185, 105, 0, "F.Cu"),
    "H3": (175, 125, 0, "F.Cu"),
    "H4": (185, 125, 0, "F.Cu"),
    "H5": (95, 107, 0, "F.Cu"),
    "H6": (95, 123, 0, "F.Cu"),

    # ===================== F.Cu (TOP SIDE) =====================
    # microSD U4: pin row at y=108 (interior), body extending toward
    # y=130 (slot at the service edge). rot=270 means pin row goes -X
    # from anchor pin 1 — anchor sits at the RIGHT end of the pin row.
    # v0.1.4 (2026-06-18): pin row dropped y=108→110.5 (d_U4=+2.5mm) as part of
    # the full-board relayout that separates the microSD and IMU subsystems by
    # 7.0mm in Y. This pulls U4's body mount holes MH5/MH6 down to y≈128, fully
    # clear of U2 (which moved UP). All 6 mount holes conserved.
    "U4": (125, 110.5, 270, "F.Cu"),

    # BMP585 U3: moved to B.Cu in v0.1.0. Originally on F.Cu but its
    # 25.4mm body (x=128.49..146.27, y=100.87..126.27 at rot=180) was
    # blocking the new battery subsystem in the top strip y=100..107.
    # With U3 on B.Cu the breakout floats below the PCB instead of above,
    # freeing all of F.Cu's top strip. I²C nets (SDA, SCL) get one extra
    # via going F.Cu↔B.Cu — freerouting handles this trivially.
    # v0.1.2-fix2 (2026-06-16): rotated 180° (was 145,125,180) so pad1/Vin sits
    # at the TOP (y=107.22) — a B.Cu single-row module inserts from below, which
    # REVERSES its pin order vs the socket numbering, so the breakout's Vin
    # physically lands at the end opposite pad1 of a top-style footprint. Same
    # holes (y107.22..125), reversed pad order. Confirms ERRATA-001 §9.
    "U3": (145, 107.22, 0, "B.Cu"),

    # XIAO ESP32S3 Plus (paired 1x7 sockets), rot=180 so the USB-C end
    # (pin 1 side) points to +Y (service edge y=130).
    # v0.1.2 (BLK-007 / POST-MORTEM-001): U1 (D0–D6) and U5 (power/SDIO) X
    # SWAPPED vs v0.1.x. At rot=180 the canonical "left" column (D0–D6) must
    # land on the PHYSICAL RIGHT (x larger); the old layout put D0 on the
    # left → mirror image. D0 column now at x=165.24, power column at x=150.
    "U1": (165.24, 124, 180, "F.Cu"),   # D0–D6  → RIGHT
    "U5": (150,    124, 180, "F.Cu"),   # power/SDIO → LEFT

    # J4: prototyping header for unused XIAO pins. Placed ABOVE the XIAO
    # body in the F.Cu strip y=100..105.88. 1x8 vertical, rot=90 (pin row
    # horizontal). Pin mapping (8 pins):
    #   1: BTN1 (D0), 2: BTN2 (D1), 3: LED1 (D2), 4: LED2 (D3),
    #   5: DBG_TX (D6), 6: DBG_RX (D7), 7: +3V3, 8: GND.
    # v0.1.3 (2026-06-17): shifted right to x=152 (anchor=pad1; pads run +X to
    # pad8≈169.8, clearing H1@175) and dropped to y=103 so it no longer crosses
    # the top edge — frees the top-strip space for J5.
    "J4": (152, 103, 90, "F.Cu"),

    # ── v0.1.3 battery subsystem (aligned along the top edge y=103) ──
    # v0.1.3 (2026-06-17): J1 and J5 are 1x02 pin headers (was JST). The three
    # connectors J1/J2/J5 are placed HORIZONTAL (rot 90) — a 1x02 header's
    # courtyard is ~6.2mm in the pin-row direction, so vertical headers over
    # the microSD socket (U4, pads at y=108) collided with U4 or overran the
    # top edge; horizontal headers are only ~3.6mm tall in Y, clearing both
    # U4 (y≥106) and the module bodies (y≥107). C8 (the VBAT_SENSE filter cap)
    # was moved to B.Cu at x=128 (under R3, left of mount hole MH3@132.4) to
    # keep it well clear of J5's through-hole pads (assembly clearance). Result
    # is a neat top-edge row J1·SW1·J2·R3·R4 (left) + J5 (right of MH3), with
    # the BMP585 mount hole MH3 in the x≈132 gap. +/- polarity silk sits at
    # J1 (-@GND,+@BAT_P) and J5 (-@GND,+@BAT_SW). NOTE: footprint swaps + the
    # 6 module mount holes (MH*) are applied with pcbnew, not re-injected here.
    #
    # J1: LiPo battery in (pin header, horizontal). pad1=GND(-), pad2=BAT_P(+).
    "J1":  (101.5, 103.0, 90, "F.Cu"),
    # SW1: SPDT arming slide. pad1=BAT_P, pad2=BAT_SW, pad3=NC.
    "SW1": (110.5, 103.0,  0, "F.Cu"),
    # J2: parallel keyswitch header (OR with SW1, horizontal). pad1=BAT_P, pad2=BAT_SW.
    "J2":  (122.0, 103.0, 90, "F.Cu"),
    # Voltage divider on BAT_SW (R3 BAT_SW→VBAT_SENSE, R4 VBAT_SENSE→GND).
    "R3":  (129.0, 103.0,  0, "F.Cu"),
    "R4":  (133.0, 103.0,  0, "F.Cu"),
    # C8 (VBAT_SENSE filter) on B.Cu, x=128 — clear of J5's TH pads + MH3.
    "C8":  (128.0, 103.0,  0, "B.Cu"),
    # J5: switched-battery tap-out (pin header, horizontal). pad1=GND(-), pad2=BAT_SW(+).
    "J5":  (139.0, 103.0, 90, "F.Cu"),

    # ===================== B.Cu (BOTTOM SIDE) =====================
    # LSM6DSO32 U2: rot=270 (pad1/Vin at the RIGHT, x_max — bottom-mount
    # reversal, same as U3). v0.1.3: pin row raised y=127→124 so its pads
    # clear the microSD mount holes (y≈126.9) and it sits closer to the
    # longitudinal axis; its own mount holes land at y≈111.4 (clear of U4).
    # v0.1.4 (2026-06-18): full-board relayout — pin row raised y=124→119.5
    # (d_U2=-4.5mm). The two single-row sensor sockets U2 (IMU) and U4 (microSD)
    # had interleaving body mount holes: U4's holes (MH5/MH6) dropped into U2's
    # courtyard/pads (4 solder_mask_bridge + 2 npth_inside_courtyard) while U2's
    # holes (MH1/MH2) sat over U4's pad row. The fix separates the subsystems by
    # 7.0mm in Y (U2 up 4.5, U4 down 2.5) — verified against the WHOLE board:
    # MH1/MH2 now clear U4's courtyard by ≥0.86mm, MH5/MH6 clear the bottom edge
    # by ≥0.89mm, and U2's pad row (now y≈119.5) sits in open area between the
    # top header row (y≈103) and the sensor band. All 6 mount holes conserved.
    "U2": (123.32, 119.5, 270, "B.Cu"),

    # ── module mounting holes (M2, 2.1mm NPTH) ──
    # Measured from each breakout's real hole positions; added to the board
    # via pcbnew with the courtyard-free MT_MountHole_M2 footprint. Recorded
    # here for reference (positions in mm). v0.1.4: IMU(U2) holes moved with
    # U2 by d_U2=(0,-4.5); microSD(U4) holes moved with U4 by d_U4=(0,+2.5).
    #   IMU LSM6 (U2):  MH1 (123.171,106.793)  MH2 (102.941,106.725)
    #   Baro BMP585(U3):MH3 (132.316,105.969)  MH4 (132.309,126.336)
    #   microSD (U4):   MH5 (125.124,127.970)  MH6 (104.380,128.109)
}


# ============================================================================
# FOOTPRINT REMOVAL (new in v0.0.12)
# ============================================================================

# Refs we KEEP in the .kicad_pcb. Anything else (J1, SW*, D*, R*, C*, F1,
# TP*, J2, J3) gets stripped out. The schematic still has them — see
# REMOVED_COMPONENTS.md for the catalog + reincorporation guide.
KEEP_REFS = set(PLACEMENTS.keys())


def remove_non_module_footprints(text: str) -> tuple:
    """Thin wrapper binding MT1's KEEP_REFS to the pcb_designer implementation."""
    return _remove_non_module_footprints_impl(text, KEEP_REFS)


# ============================================================================
# MUTATION HELPERS (unchanged from v0.0.11)
# ============================================================================

# Wrappers: bind MT1 board constants → call pcb_designer.geometry impls.
# Keeping the local names (resize_pcb_outline, reposition_silkscreen,
# _make_title_silk) so the rest of the script doesn't need updating.

def resize_pcb_outline(text: str) -> str:
    return _resize_outline_impl(text, PCB_X0, PCB_Y0, PCB_X1, PCB_Y1)


def reposition_silkscreen(text: str) -> str:
    return _reposition_silk_impl(text, LEFT_ANCHOR_X, RIGHT_ANCHOR_X,
                                 PCB_Y0, PCB_Y1, VERSION_TAG)


def _make_title_silk() -> str:
    return make_title_silk(VERSION_TAG)


# _LAYER_PAIRS + flip helpers + place_and_flip migrated to pcb_designer.placement.
# Thin wrapper here binds MT1's PLACEMENTS dict and exposes the legacy name.

def place_and_flip_footprints(text: str) -> tuple:
    return _place_and_flip_impl(text, PLACEMENTS)


def _inject_j4_silk_labels_only(text: str) -> str:
    """The J4 footprint already exists but its per-pin silk labels were
    wiped (e.g., by KiCad GUI sync). Inject the 8 `(fp_text user "...")`
    elements into the existing J4 footprint block."""
    # Find the J4 footprint block.
    m = re.search(r'\(property\s+"Reference"\s+"J4"', text)
    if not m:
        return text
    fp_start, fp_end = _extract_footprint_block(text, m.start())
    if fp_start is None:
        return text

    pin_labels = ["D0", "D1", "D2", "D3", "D6", "D7", "3V3", "GND"]
    labels = []
    for i, lbl in enumerate(pin_labels):
        labels.append(
            f'\t\t(fp_text user "{lbl}"\n'
            f'\t\t\t(at -2.6 {i*2.54} 90)\n'
            f'\t\t\t(layer "F.SilkS")\n'
            f'\t\t\t(uuid "j4lbl{i:02d}-0000-4000-8000-{i:012d}")\n'
            f'\t\t\t(effects (font (size 0.8 0.8) (thickness 0.15)))\n'
            f'\t\t)'
        )
    labels_block = "\n" + "\n".join(labels) + "\n\t"

    # Insert before the closing paren of the J4 footprint block.
    # Walk backward from fp_end to find the position just before the last ')'.
    insert_pos = fp_end - 1  # Just before the final ')'.
    # Skip backward whitespace.
    while insert_pos > fp_start and text[insert_pos - 1] in " \t":
        insert_pos -= 1
    print(f"  Re-injected 8 silk labels (D0..GND) into existing J4 block")
    return text[:insert_pos] + labels_block + text[insert_pos:]


def inject_j4_header(text: str) -> str:
    """If J4 (prototyping header) is missing, inject it as a 1x8 vertical
    pin header with pads bound to the existing nets for unused XIAO pins:
        pin 1 → BTN1 (net 11),    pin 2 → BTN2 (net 12)
        pin 3 → LED1 (net 9),     pin 4 → LED2 (net 10)
        pin 5 → DBG_TX (net 26),  pin 6 → DBG_RX (net 30)
        pin 7 → +3V3 (net 4),     pin 8 → GND (net 2)

    Net numbers are read from the existing (net N "/name") declarations
    at the top of the .kicad_pcb. Since this iteration doesn't modify the
    schematic, those net numbers are stable.
    """
    if '"Reference" "J4"' in text:
        # J4 footprint is already in the .kicad_pcb (e.g., after a KiCad
        # GUI "Update PCB from Schematic" that re-built it from the
        # library). Check whether the per-pin silk labels survived — if
        # not, inject them into the existing block.
        if '"D0"' in text and '"GND"' in text:
            return text
        return _inject_j4_silk_labels_only(text)

    x, y, rot, _layer = PLACEMENTS["J4"]
    # Pin mapping: index → (net_number, net_name).
    pin_nets = [
        (11, "/BTN1"),
        (12, "/BTN2"),
        (9,  "/LED1"),
        (10, "/LED2"),
        (26, "/DBG_TX"),
        (30, "/DBG_RX"),
        (4,  "/+3V3"),
        (2,  "/GND"),
    ]

    pads = []
    for i, (net_n, net_name) in enumerate(pin_nets):
        pad_shape = "rect" if i == 0 else "circle"
        pad_y = i * 2.54
        pads.append(
            f'\t\t(pad "{i+1}" thru_hole {pad_shape}\n'
            f'\t\t\t(at 0 {pad_y})\n'
            f'\t\t\t(size 1.7 1.7)\n'
            f'\t\t\t(drill 1)\n'
            f'\t\t\t(layers "*.Cu" "*.Mask")\n'
            f'\t\t\t(remove_unused_layers no)\n'
            f'\t\t\t(net {net_n} "{net_name}")\n'
            f'\t\t\t(pinfunction "Pin_{i+1}")\n'
            f'\t\t\t(pintype "passive")\n'
            f'\t\t\t(uuid "j4{i+1:02d}aaaa-0000-4000-8000-{i+1:012d}")\n'
            f'\t\t)'
        )
    pads_block = "\n".join(pads)

    # Silkscreen labels next to each pin so the user can read "D0", "D1",
    # ..., "3V3", "GND" without a datasheet. Labels at -X side in module
    # local (= below pad row at rot=90 PCB placement, toward the XIAO body
    # — away from the PCB top edge).
    pin_labels = ["D0", "D1", "D2", "D3", "D6", "D7", "3V3", "GND"]
    silk_labels = []
    for i, lbl in enumerate(pin_labels):
        silk_labels.append(
            f'\t\t(fp_text user "{lbl}"\n'
            f'\t\t\t(at -2.6 {i*2.54} 90)\n'
            f'\t\t\t(layer "F.SilkS")\n'
            f'\t\t\t(uuid "j4lbl{i:02d}-0000-4000-8000-{i:012d}")\n'
            f'\t\t\t(effects (font (size 0.8 0.8) (thickness 0.15)))\n'
            f'\t\t)'
        )
    labels_block = "\n".join(silk_labels)

    j4_block = f'''\t(footprint "Connector_PinHeader_2.54mm:PinHeader_1x08_P2.54mm_Vertical"
\t\t(layer "F.Cu")
\t\t(uuid "j4000000-0000-4000-8000-000000000000")
\t\t(at {x} {y} {rot})
\t\t(descr "Pin header 1x08 2.54mm vertical — prototyping unused XIAO pins")
\t\t(property "Reference" "J4"
\t\t\t(at 0 -2.77 {rot})
\t\t\t(layer "F.SilkS")
\t\t\t(uuid "j4ref0000-0000-4000-8000-000000000001")
\t\t\t(effects (font (size 1 1) (thickness 0.15)))
\t\t)
\t\t(property "Value" "proto_header"
\t\t\t(at 0 20.55 {rot})
\t\t\t(layer "F.Fab")
\t\t\t(hide yes)
\t\t\t(uuid "j4val0000-0000-4000-8000-000000000002")
\t\t\t(effects (font (size 1 1) (thickness 0.15)))
\t\t)
\t\t(property "Footprint" ""
\t\t\t(at 0 0 0)
\t\t\t(unlocked yes)
\t\t\t(layer "F.Fab")
\t\t\t(hide yes)
\t\t\t(uuid "j4fp00000-0000-4000-8000-000000000003")
\t\t\t(effects (font (size 1.27 1.27) (thickness 0.15)))
\t\t)
\t\t(attr through_hole)
{labels_block}
{pads_block}
\t)'''

    final_paren = text.rstrip().rfind(")")
    return text[:final_paren] + "\n" + j4_block + "\n" + text[final_paren:]


def inject_made_on_earth_label(text: str) -> str:
    """Inject the 'Made on Earth / by MultitecUA' silk on B.SilkS at the LEFT
    (lateral) side, two lines, mirrored so it reads from the bottom view.
    No-op if any 'Made on Earth' text already exists.

    v0.1.2: was a single centred line at (140,115) which collided visually
    with the U3 sensor area — removed in favour of this lateral two-line
    label (overlay/silk review 2026-06-15)."""
    if 'Made on Earth' in text:
        return text

    label = '''\t(gr_text "Made on Earth"
\t\t(at 105 114 0)
\t\t(layer "B.SilkS")
\t\t(uuid "made00000-0000-4000-8000-aaaa11111111")
\t\t(effects
\t\t\t(font (size 1.5 1.5) (thickness 0.25))
\t\t\t(justify mirror)
\t\t)
\t)
\t(gr_text "by MultitecUA"
\t\t(at 105 116.5 0)
\t\t(layer "B.SilkS")
\t\t(uuid "made00000-0000-4000-8000-aaaa11111112")
\t\t(effects
\t\t\t(font (size 1.5 1.5) (thickness 0.25))
\t\t\t(justify mirror)
\t\t)
\t)'''
    final_paren = text.rstrip().rfind(")")
    print(f"  Injected 'Made on Earth / by MultitecUA' on B.SilkS at (105, 114) [lateral]")
    return text[:final_paren] + "\n" + label + "\n" + text[final_paren:]


# ============================================================================
# ROUTING — v0.0.15 first pass
# ============================================================================
# Net numbers fixed by KiCad after the GUI "Update PCB from Schematic" in
# v0.0.14. The schematic is slim now (8 components), so the netlist is
# stable across runs as long as build_schematic.py isn't touched.
NET_NUMBERS = {
    "GND":       2,
    "+3V3":      3,
    "LED1":      4,
    "LED2":      5,
    "BTN1":      6,
    "BTN2":      7,
    "I2C_SDA":   8,
    "I2C_SCL":   9,
    "SDIO_CMD": 10,
    "SDIO_D0":  11,
    "SDIO_CLK": 12,
    "DBG_TX":   21,
    "DBG_RX":   25,
}

TRACE_WIDTH = 0.25       # mm — signals
TRACE_WIDTH_PWR = 0.4    # mm — +3V3 / GND traces (wider per CONVENTIONS §7)


def inject_routing(text: str) -> str:
    """v0.0.15 routing — minimal: GND zone only.

    Idempotent: removes any prior (segment ...)/(zone ...) we generated,
    then re-inserts. Just adds a B.Cu GND zone that covers the entire
    PCB. KiCad's connectivity engine then sees all GND pads as connected
    via the zone (no thermal-fill polygon needed for DRC).

    All SIGNAL routing (J4↔XIAO, I²C, SDIO, +3V3 chain) is intentionally
    LEFT FOR THE GUI: simple Manhattan in code produced 16 track-crossings
    and 8 short-circuits because B.Cu traces unavoidably run through TH
    pads on F.Cu (and vice versa) without vias. KiCad's push-and-shove
    interactive router handles this in seconds — let the user do it.
    """
    # Strip any prior segments we generated (uuid prefix "trace*") so
    # they don't pile up across re-runs. Segments laid down by freerouting
    # have different UUIDs and are NOT touched.
    text = re.sub(r'\n\t\(segment[\s\S]*?\(uuid \"trace[\s\S]*?\"\)\s*\)',
                  '', text)

    # Detect if a GND zone on B.Cu already exists. If yes, leave its
    # (filled_polygon) intact but make sure the SETTINGS match what we
    # want (clearance 0.2, min_thickness 0.2). v0.0.16 used clearance
    # 0.4 which left only 40µm of copper between adjacent TH anti-pads
    # at 2.54mm pitch — well below the 0.25mm min_thickness, so the
    # filler fragmented the zone into isolated islands. Tightening the
    # clearance keeps slivers wide enough to survive the filler.
    has_gnd_zone = bool(re.search(
        r'\(zone\s+\(net 2\)\s+\(net_name \"/GND\"\)\s+\(layer \"B\.Cu\"\)',
        text))
    if has_gnd_zone:
        # Patch the existing zone's settings in-place. The autorouter will
        # recompute (filled_polygon) on the next run with the new values.
        text = re.sub(
            r'(\(zone\s+\(net 2\)\s+\(net_name "/GND"\)\s+\(layer "B\.Cu"\)'
            r'[\s\S]*?\(connect_pads\s+\(clearance )[\d.]+(\))',
            r'\g<1>0.2\g<2>', text, count=1)
        text = re.sub(
            r'(\(zone\s+\(net 2\)\s+\(net_name "/GND"\)\s+\(layer "B\.Cu"\)'
            r'[\s\S]*?\(min_thickness )[\d.]+(\))',
            r'\g<1>0.2\g<2>', text, count=1)

    routes: list[str] = []

    # ─── GND zone on B.Cu (covers the entire PCB) ─────────────────────────
    # Zones in KiCad need to be "refilled" to actually create copper fills;
    # the (filled_polygon) below is a manually-computed rectangular fill so
    # kicad-cli render shows the plane. KiCad GUI will recompute it cleanly
    # the first time you open the board (Edit → Fill All Zones, B).
    # NOTE: tried `(min_resolved_spokes 1)` inside (fill ...) to fix the
    # remaining starved_thermal warning on U3.3 GND, but it crashes
    # pcbnew (segfault during LoadBoard). The setting is exposed in the
    # KiCad GUI under zone properties → can be toggled there if the
    # warning bothers you; the pad IS electrically connected to GND via
    # the zone, the warning is purely about thermal-relief soldering
    # quality and tolerable for a prototype.
    gnd_zone = f'''\t(zone
\t\t(net {NET_NUMBERS["GND"]})
\t\t(net_name "/GND")
\t\t(layer "B.Cu")
\t\t(uuid "gndzone0-0000-4000-8000-000000000001")
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
\t\t\t\t(xy {PCB_X0} {PCB_Y0}) (xy {PCB_X1} {PCB_Y0})
\t\t\t\t(xy {PCB_X1} {PCB_Y1}) (xy {PCB_X0} {PCB_Y1})
\t\t\t)
\t\t)
\t)'''

    # Note: GND zone stitching is handled in run_autorouter.py's
    # _add_gnd_stitches() so the bridges are present when ZONE_FILLER runs
    # (otherwise the filler computes islands as if no stitches existed and
    # DRC still reports unconnected polygons even after stitches are added).

    n_seg = sum(1 for r in routes if r.startswith('\t(segment'))
    if has_gnd_zone:
        # Zone already in file (possibly with a (filled_polygon) computed
        # by ZONE_FILLER) — don't touch it.
        insertion = "\n" + "\n".join(routes) + "\n" if routes else ""
        print(f"  Injected {n_seg} trace segments — GND zone already present, left intact")
    else:
        # First run on this board: define the zone here so the autorouter
        # picks it up when ExportSpecctraDSN reads the file.
        insertion = "\n" + "\n".join(routes) + "\n" + gnd_zone + "\n"
        print(f"  Injected {n_seg} trace segments + 1 GND zone on B.Cu")
    if not insertion:
        return text
    final_paren = text.rstrip().rfind(")")
    return text[:final_paren] + insertion + text[final_paren:]


def inject_mounting_holes(text: str) -> str:
    holes = [(ref, PLACEMENTS[ref][0], PLACEMENTS[ref][1])
             for ref in ("H1", "H2", "H3", "H4", "H5", "H6")]
    existing = re.findall(r'"Reference"\s+"(H[1-6])"', text)
    needed = [h for h in holes if h[0] not in existing]
    if not needed:
        return text

    print(f"  Injecting {len(needed)} mounting holes: {[h[0] for h in needed]}")

    fps = []
    for ref, x, y in needed:
        uuid_base = f"b{ref[1]:0>7}-0000-4000-8000-{ref[1]:0>12}"
        fps.append(f'''	(footprint "MountingHole:MountingHole_2.5mm_Pad_Via"
		(layer "F.Cu")
		(uuid "{uuid_base}")
		(at {x} {y} 0)
		(descr "Mounting Hole 2.5mm M2")
		(property "Reference" "{ref}"
			(at 0 -3.5 0)
			(layer "F.SilkS")
			(uuid "{uuid_base[:8]}-1001-4000-8000-000000000001")
			(effects (font (size 0.8 0.8) (thickness 0.15)))
		)
		(property "Value" "MountingHole"
			(at 0 3.5 0)
			(unlocked yes)
			(layer "F.Fab")
			(hide yes)
			(uuid "{uuid_base[:8]}-1002-4000-8000-000000000002")
			(effects (font (size 0.8 0.8) (thickness 0.15)))
		)
		(property "Footprint" ""
			(at 0 0 0)
			(unlocked yes)
			(layer "F.Fab")
			(hide yes)
			(uuid "{uuid_base[:8]}-1003-4000-8000-000000000003")
			(effects (font (size 1.27 1.27) (thickness 0.15)))
		)
		(property "Datasheet" ""
			(at 0 0 0)
			(unlocked yes)
			(layer "F.Fab")
			(hide yes)
			(uuid "{uuid_base[:8]}-1004-4000-8000-000000000004")
			(effects (font (size 1.27 1.27) (thickness 0.15)))
		)
		(property "Description" ""
			(at 0 0 0)
			(unlocked yes)
			(layer "F.Fab")
			(hide yes)
			(uuid "{uuid_base[:8]}-1005-4000-8000-000000000005")
			(effects (font (size 1.27 1.27) (thickness 0.15)))
		)
		(attr exclude_from_pos_files exclude_from_bom)
		(pad "1" thru_hole circle
			(at 0 0)
			(size 5 5)
			(drill 2.5)
			(layers "*.Cu" "*.Mask")
			(remove_unused_layers no)
			(uuid "{uuid_base[:8]}-2000-4000-8000-000000000010")
		)
	)''')

    final_paren = text.rstrip().rfind(")")
    insertion = "\n" + "\n".join(fps) + "\n"
    return text[:final_paren] + insertion + text[final_paren:]


# ============================================================================
# VERIFICATION
# ============================================================================

# Pin count for each footprint. Mounting holes count as 1 (single pad).
# 1xN sockets at rot=0 have pin 1 at origin, pins extending +Y at 2.54 pitch.
PIN_COUNT = {
    "U1": 7, "U5": 7, "U2": 9, "U3": 8, "U4": 9,
    "J4": 8,
    "H1": 1, "H2": 1, "H3": 1, "H4": 1, "H5": 1, "H6": 1,
    # v0.1.0 battery subsystem:
    "J1": 2, "SW1": 3, "J2": 2, "J5": 2,
    "R3": 2, "R4": 2, "C8": 2,
}

# Pad half-size at rot=0 (half_X, half_Y) — for the single-pin courtyard;
# the bbox of a multi-pin row is computed by walking all pad positions and
# expanding by this pad half-size. 0.5mm courtyard is included.
PAD_HALF = {
    "U1": (1.25, 1.25), "U5": (1.25, 1.25), "U2": (1.25, 1.25),
    "U3": (1.25, 1.25), "U4": (1.25, 1.25),
    "J4": (1.25, 1.25),
    "H1": (2.75, 2.75), "H2": (2.75, 2.75), "H3": (2.75, 2.75),
    "H4": (2.75, 2.75), "H5": (2.75, 2.75), "H6": (2.75, 2.75),
    # v0.1.0 battery subsystem: JST/switch/headers have slightly larger
    # pads + bigger courtyard. 0805 SMD has smaller courtyard (~1mm).
    "J1":  (1.30, 1.30),
    "SW1": (1.30, 1.50),
    "J2":  (1.30, 1.30),
    "J5":  (1.30, 1.30),
    "R3":  (0.90, 0.90),
    "R4":  (0.90, 0.90),
    "C8":  (0.90, 0.90),
}

# Body (breakout PCB) extent — half_X, half_Y in the LOCAL footprint frame
# at rot=0 (pin 1 at origin, pin row +Y, body extending +X). Body offset
# from pin 1 in (offset_X, offset_Y). Set to None for footprints with no
# overhanging body (mounting holes, paired sockets — XIAO is special-cased
# below as a combined body).
BODY_EXTENT = {
    "U2": ((8.89, 12.7), (7.62, 11.43)),   # LSM6 breakout 17.78x25.4
    "U3": ((8.89, 12.7), (7.62, 11.43)),   # BMP585 breakout 17.78x25.4
    "U4": ((11.4, 12.7), (10.13, 11.43)),  # microSD breakout 22.8x25.4
}

# Through-hole footprints — drill holes consume space on BOTH layers.
# (J1, SW1, J2, J5 are THT; R3/R4/C8 are SMD 0805 → not in this set.)
TH_FOOTPRINTS = {"U1", "U2", "U3", "U4", "U5", "J4",
                 "H1", "H2", "H3", "H4", "H5", "H6",
                 "J1", "SW1", "J2", "J5"}

# Override for footprints whose pin row is NOT the default vertical
# 2.54mm pitch (1×N socket). Each value is a list of (x, y) tuples in
# the footprint-local frame (before rotation).
PIN_LOCAL_POSITIONS = {
    "J1":  [(0.0, 0.0), (2.0, 0.0)],          # JST-PH 2-pin, 2.0mm pitch
    "SW1": [(0.0, 0.0), (2.0, 0.0), (4.0, 0.0)],  # SPDT slide, 2.0mm pitch
    "J2":  [(0.0, 0.0), (0.0, 2.54)],         # 1x2 vertical pin header (pins along +Y in local frame)
    "J5":  [(0.0, 0.0), (0.0, 2.54)],         # idem
    "R3":  [(-1.0, 0.0), (1.0, 0.0)],         # 0805 HandSolder, 2mm pad pitch
    "R4":  [(-1.0, 0.0), (1.0, 0.0)],
    "C8":  [(-1.0, 0.0), (1.0, 0.0)],
}


def _rotate_cw(point, rot_deg):
    """Rotate `point` by `rot_deg` clockwise around origin."""
    th = math.radians(rot_deg)
    cos_t, sin_t = math.cos(th), math.sin(th)
    return (point[0]*cos_t + point[1]*sin_t,
            -point[0]*sin_t + point[1]*cos_t)


def _pad_bbox(ref):
    """Bbox enclosing all pad courtyards of `ref` in board coordinates."""
    x, y, rot, _ = PLACEMENTS[ref]
    ph_x, ph_y = PAD_HALF.get(ref, (1.5, 1.5))
    # Pad positions in footprint-local frame.
    if ref in PIN_LOCAL_POSITIONS:
        locals_ = PIN_LOCAL_POSITIONS[ref]
    else:
        n = PIN_COUNT.get(ref, 1)
        locals_ = [(0.0, k * 2.54) for k in range(n)]
    rotated = [_rotate_cw(p, rot) for p in locals_]
    pads = [(x + r[0], y + r[1]) for r in rotated]
    xs = [p[0] for p in pads]
    ys = [p[1] for p in pads]
    # ph_x/ph_y are isotropic for pads, so rotation doesn't change them.
    return (min(xs) - ph_x, min(ys) - ph_y,
            max(xs) + ph_x, max(ys) + ph_y)


def _body_bbox(ref):
    """Body bbox of a single breakout PCB in board coords. None if no body."""
    if ref not in BODY_EXTENT:
        return None
    (hw, hh), (ox, oy) = BODY_EXTENT[ref]
    x, y, rot, _ = PLACEMENTS[ref]
    cx_off, cy_off = _rotate_cw((ox, oy), rot)
    cx, cy = x + cx_off, y + cy_off
    # At rot=90/270 the half extents swap.
    if rot in (90, 270):
        hw, hh = hh, hw
    return (cx - hw, cy - hh, cx + hw, cy + hh)


def _xiao_body_bbox():
    """XIAO body straddles U1 and U5 — single combined body, centered on
    the bbox of both pin rows."""
    pad_bboxes = [_pad_bbox("U1"), _pad_bbox("U5")]
    x_min = min(b[0] for b in pad_bboxes) + 1.25  # subtract pad courtyard
    x_max = max(b[2] for b in pad_bboxes) - 1.25
    y_min = min(b[1] for b in pad_bboxes) + 1.25
    y_max = max(b[3] for b in pad_bboxes) - 1.25
    cx, cy = (x_min + x_max) / 2, (y_min + y_max) / 2
    # XIAO real_size_mm = [17.78, 21.0]. At any rot, body extends ±8.89 X
    # and ±10.5 Y relative to the pin-row bbox center (pin row is 15.24mm
    # span between U1 and U5, body 21mm tall, 17.78mm wide).
    u1_rot = PLACEMENTS["U1"][2]
    if u1_rot in (0, 180):
        hw, hh = 8.89, 10.5
    else:  # 90, 270
        hw, hh = 10.5, 8.89
    return (cx - hw, cy - hh, cx + hw, cy + hh)


def _overlaps(a, b):
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def verify_layout():
    print("\n=== verify_layout() ===")

    # 1. Inside PCB outline
    out_of_bounds = []
    for ref, (x, y, _rot, _layer) in PLACEMENTS.items():
        if not (PCB_X0 < x < PCB_X1 and PCB_Y0 < y < PCB_Y1):
            out_of_bounds.append((ref, x, y))
    if out_of_bounds:
        print(f"  [WARN] {len(out_of_bounds)} footprint(s) outside PCB outline:")
        for r, x, y in out_of_bounds:
            print(f"         {r} at ({x},{y})")
    else:
        print(f"  OK   all {len(PLACEMENTS)} footprints inside outline")

    # 2. LEFT anchor strip (x<LEFT_ANCHOR_X) — only mounting holes allowed
    intruders_left = [
        (r, x) for r, (x, _y, _rot, _l) in PLACEMENTS.items()
        if x < LEFT_ANCHOR_X and not r.startswith("H")
    ]
    if intruders_left:
        print(f"  [WARN] non-anchor component(s) in LEFT anchor strip:")
        for r, x in intruders_left:
            print(f"         {r} at x={x}")
    else:
        print(f"  OK   LEFT anchor strip (x<{LEFT_ANCHOR_X}) is component-free")

    # 3. RIGHT anchor strip — only mounting holes allowed (power section removed)
    intruders_right = [
        (r, x) for r, (x, _y, _rot, _l) in PLACEMENTS.items()
        if x > RIGHT_ANCHOR_X and not r.startswith("H")
    ]
    if intruders_right:
        print(f"  [WARN] non-anchor component(s) in RIGHT anchor strip:")
        for r, x in intruders_right:
            print(f"         {r} at x={x}")
    else:
        print(f"  OK   RIGHT anchor strip (x>{RIGHT_ANCHOR_X}) only has holes")

    # 4. Connector orientation
    print(f"  Connector orientation (USB-C/SD -> long edge y={PCB_Y1}):")
    for ref in ("U1", "U5", "U4"):
        x, y, rot, _ = PLACEMENTS[ref]
        side = "BOTTOM" if (PCB_Y1 - y) < (y - PCB_Y0) else "TOP"
        print(f"         {ref} at ({x},{y}) rot={rot} -> closer to {side} edge")

    # 5. Body bboxes (also assert PCB-edge clearance)
    print(f"  Body bboxes:")
    for ref in ("U4", "U3", "U2"):
        bb = _body_bbox(ref)
        clear = min(bb[0] - PCB_X0, PCB_X1 - bb[2],
                    bb[1] - PCB_Y0, PCB_Y1 - bb[3])
        flag = "" if clear >= 0 else "  ⚠ OFF-PCB"
        print(f"         {ref} body=({bb[0]:.2f},{bb[1]:.2f},{bb[2]:.2f},{bb[3]:.2f})"
              f"  edge_clear={clear:+.2f}mm{flag}")
    xb = _xiao_body_bbox()
    xclear = min(xb[0] - PCB_X0, PCB_X1 - xb[2],
                 xb[1] - PCB_Y0, PCB_Y1 - xb[3])
    print(f"         XIAO body=({xb[0]:.2f},{xb[1]:.2f},{xb[2]:.2f},{xb[3]:.2f})"
          f"  edge_clear={xclear:+.2f}mm")

    # 6. Same-layer pad bbox overlaps (hard fail)
    refs = list(PLACEMENTS.keys())
    overlaps_pad = []
    for i, a in enumerate(refs):
        for b in refs[i+1:]:
            if PLACEMENTS[a][3] != PLACEMENTS[b][3]:
                continue
            if _overlaps(_pad_bbox(a), _pad_bbox(b)):
                overlaps_pad.append((a, b))
    if overlaps_pad:
        print(f"  [WARN] {len(overlaps_pad)} same-layer pad-bbox overlap(s):")
        for a, b in overlaps_pad:
            print(f"         {a} <-> {b}")
    else:
        print(f"  OK   no same-layer pad-bbox overlaps")

    # 7. Same-layer body bbox overlaps (breakout PCBs hovering on the SAME
    #    face would physically collide)
    bodies = {}
    for ref in refs:
        bb = _body_bbox(ref)
        if bb is not None:
            bodies[ref] = (bb, PLACEMENTS[ref][3])
    # XIAO body straddles U1+U5; group both refs onto a single virtual entry.
    bodies["XIAO"] = (_xiao_body_bbox(), PLACEMENTS["U1"][3])
    # Suppress duplicate per-socket bodies from the comparison (we don't
    # individually model U1/U5 bodies).
    body_refs = [r for r in bodies if r not in ("U1", "U5")]
    overlaps_body = []
    for i, a in enumerate(body_refs):
        for b in body_refs[i+1:]:
            if bodies[a][1] != bodies[b][1]:
                continue
            if _overlaps(bodies[a][0], bodies[b][0]):
                overlaps_body.append((a, b))
    if overlaps_body:
        print(f"  [WARN] {len(overlaps_body)} same-layer body-bbox overlap(s):")
        for a, b in overlaps_body:
            print(f"         {a} <-> {b}")
    else:
        print(f"  OK   no same-layer body-bbox overlaps")

    # 8. Cross-layer TH-pad conflicts (drill holes block both sides)
    cross = []
    for i, a in enumerate(refs):
        for b in refs[i+1:]:
            if PLACEMENTS[a][3] == PLACEMENTS[b][3]:
                continue
            if a not in TH_FOOTPRINTS and b not in TH_FOOTPRINTS:
                continue
            if _overlaps(_pad_bbox(a), _pad_bbox(b)):
                cross.append((a, b))
    if cross:
        print(f"  [WARN] {len(cross)} cross-layer TH-pad conflict(s):")
        for a, b in cross:
            la, lb = PLACEMENTS[a][3], PLACEMENTS[b][3]
            print(f"         {a}({la}) <-> {b}({lb})")
    else:
        print(f"  OK   no cross-layer TH-pad conflicts")

    # 9. Layer distribution
    f_cu = sum(1 for v in PLACEMENTS.values() if v[3] == "F.Cu")
    b_cu = sum(1 for v in PLACEMENTS.values() if v[3] == "B.Cu")
    print(f"  Layer distribution: F.Cu={f_cu}, B.Cu={b_cu}")
    print("=== end verify_layout ===\n")


# ============================================================================
# MAIN
# ============================================================================

VERSION_TAG = "v0.1.4"


def main():
    if not PCB_PATH.exists():
        print(f"ERROR: {PCB_PATH} not found")
        return 1

    verify_layout()

    backup = PCB_PATH.with_suffix(".kicad_pcb.bak6")
    shutil.copy2(PCB_PATH, backup)
    print(f"Backup -> {backup.name}")

    # v0.1.0: ensure the battery-management footprints exist BEFORE the
    # string-based passes. The injector uses pcbnew's Python API to
    # load → add missing fps with proper net assignments → save, then
    # text-renames /BTN1 → /VBAT_SENSE. Idempotent: a re-run with all
    # 7 components already present is a no-op (save still happens).
    print("\nInjecting battery subsystem (J1, SW1, J2, J5, R3, R4, C8)...")
    try:
        from inject_battery import inject_battery_section
    except ImportError:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).parent))
        from inject_battery import inject_battery_section
    inject_battery_section(PCB_PATH)

    text = PCB_PATH.read_text()

    print(f"\nResizing PCB outline to {PCB_X1-PCB_X0:.0f} x {PCB_Y1-PCB_Y0:.0f} mm...")
    text = resize_pcb_outline(text)
    text = reposition_silkscreen(text)

    print("\nStripping non-module footprints...")
    text, removed = remove_non_module_footprints(text)
    if removed:
        print(f"  Removed {len(removed)}: {removed}")
    else:
        print(f"  (nothing to remove — already stripped)")

    print("\nInjecting mounting holes if missing...")
    text = inject_mounting_holes(text)

    print("\nInjecting J4 prototyping header if missing...")
    text = inject_j4_header(text)

    print("\nInjecting 'Made on Earth by MultitecUA' label if missing...")
    text = inject_made_on_earth_label(text)

    print("\nInjecting first-pass routing (segments + GND zone)...")
    text = inject_routing(text)

    print("\nPlacing footprints + B.Cu flips...")
    text, updated, not_found = place_and_flip_footprints(text)
    print(f"  Placed: {updated}/{len(PLACEMENTS)}")
    if not_found:
        print(f"  Not found in PCB: {not_found}")

    # v0.0.17: every GND TH pad gets zone_connect=2 (solid) so the GND
    # plane merges directly with the pad. Reason: the project rule
    # `min_resolved_spokes=2` together with the anti-pad rings of
    # neighbouring TH pads fragments the zone fill and starves single
    # pads at random (U3.3 in v0.0.16, U5.2 in the first v0.0.17 trial).
    # Applying solid connection to every GND pad makes the ground plane
    # robust regardless of how freerouting lays tracks around the pad
    # columns. Trade-off: hand-soldering these pads needs more heat — fine
    # for prototypes; soak with a 60W iron.
    print("\nForcing solid GND connection on every GND TH pad...")
    for ref, pad in [("U2", "3"), ("U3", "3"), ("U4", "2"),
                      ("U5", "2"), ("J4", "8")]:
        text = force_pad_zone_connect(text, ref, pad, mode=2)

    # Strip sub-0.1mm segments left dangling by freerouting (v0.0.16 saw a
    # 0.0847mm /LED2 stub at (151.75, 100.41)).
    print("\nStripping sub-0.1mm dangling segments...")
    text, n_drop = remove_tiny_segments(text, max_len_mm=0.1)
    if n_drop:
        print(f"  Dropped {n_drop} micro-stub segment(s)")
    else:
        print(f"  (none to drop)")

    PCB_PATH.write_text(text)
    print(f"\nSaved: {PCB_PATH.name}")

    VAL.mkdir(parents=True, exist_ok=True)
    drc_out = VAL / f"drc-{VERSION_TAG}.txt"
    print("\nRunning DRC...")
    r = subprocess.run(
        ["kicad-cli", "pcb", "drc", str(PCB_PATH), "--output", str(drc_out)],
        capture_output=True, text=True)
    if r.stdout.strip():
        for line in r.stdout.strip().splitlines()[-6:]:
            print(f"  {line}")

    RENDERS.mkdir(parents=True, exist_ok=True)
    print("\nRendering top + bottom views (3D)...")
    for side, name in [("top",    f"{VERSION_TAG}-top.png"),
                       ("bottom", f"{VERSION_TAG}-bottom.png")]:
        out_png = RENDERS / name
        r2 = subprocess.run(
            ["kicad-cli", "pcb", "render", str(PCB_PATH),
             "--output", str(out_png), "--side", side,
             "--background", "opaque", "--width", "1800", "--height", "900"],
            capture_output=True, text=True)
        if r2.returncode == 0:
            print(f"  {side}: {name}")
        else:
            print(f"  {side}: FAILED — {r2.stderr.strip().splitlines()[-1] if r2.stderr else 'no stderr'}")

    # PCB-editor-style 2D "DIM" renders (front + back, no flip). Vector
    # plot via kicad-cli + custom themes — traces are crisp and clearly
    # readable for routing inspection. See projects/mt1/tools/render_dim.py for details.
    print("\nRendering DIM front + back (2D, PCB-editor style)...")
    dim_script = Path(__file__).parent / "render_dim.py"
    r3 = subprocess.run(
        ["python3", str(dim_script), "--version", VERSION_TAG],
        capture_output=True, text=True)
    if r3.returncode == 0:
        for line in r3.stdout.strip().splitlines():
            if line.strip():
                print(f"  {line}")
    else:
        print(f"  DIM renders FAILED — {r3.stderr.strip().splitlines()[-1] if r3.stderr else 'no stderr'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
