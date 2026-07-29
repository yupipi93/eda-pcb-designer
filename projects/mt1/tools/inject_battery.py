#!/usr/bin/env python3
"""Inject the v0.1.0 battery-management subsystem footprints into the
MT1 `.kicad_pcb` using KiCad's `pcbnew` Python API.

Components added (all on F.Cu, top strip y=100..107):

  - J1: JST-PH 2-pin horizontal — LiPo battery in (BAT_P, GND).
  - SW1: SPDT slide CK OS102011MS2Q — battery disconnect.
        Pad 1 (common)  → BAT_P
        Pad 2 (throw A) → BAT_SW   (system powered when slider here)
        Pad 3 (throw B) → no_connect (system OFF when slider here)
  - J2: 1x2 pin header — parallel to SW1 contacts so the user can wire
        an EXTERNAL switch. Pin 1 = BAT_P, Pin 2 = BAT_SW.
  - J5: 1x2 pin header — manual jumper to the XIAO BAT+ / BAT- pads
        on the underside of the module. Pin 1 = BAT_SW, Pin 2 = GND.
  - R3, R4: 100 kΩ 0805 HandSolder — voltage divider for VBAT sensing.
  - C8: 100 nF 0805 HandSolder — ADC filter cap on VBAT_SENSE.

Net plumbing:

  - New nets added:  /BAT_P, /BAT_SW
  - Existing net renamed: /BTN1 → /VBAT_SENSE (D0/GPIO1 was previously
    labelled BTN1 in the schematic but SW2 was never present on the
    PCB; the pin is now ADC1_CH0 driven by the resistor divider).
  - U1.1 pad keeps net 6 (the rename is in-place).

The function is idempotent: re-running detects existing refs and skips.
Default positions are placeholders — `place_components.py`'s
`place_and_flip_footprints()` will move each component to its final
location after this step.

Invocation: called by `place_components.py` as a pre-step, before the
string-based file mutations. Saves the board after edits.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make the pcb_designer package importable when this script is run directly
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from pcb_designer.injection import _rename_net_in_file  # noqa: E402

try:
    import pcbnew
except ImportError:
    print("ERROR: pcbnew Python module not found (need KiCad 9 system install).",
          file=sys.stderr)
    raise


# Standard KiCad 9 footprint library root.
KICAD_FP_ROOT = Path("/usr/share/kicad/footprints")


# (ref, library, footprint_name, pad_net_assignments)
# pad_net_assignments maps pad number (str, as the KiCad API returns it) to
# the desired net name. None means "leave unconnected".
TARGETS = [
    ("J1",  "Connector_JST.pretty",
     "JST_PH_S2B-PH-K_1x02_P2.00mm_Horizontal",
     {"1": "/BAT_P", "2": "/GND"}),
    ("SW1", "Button_Switch_THT.pretty",
     "SW_Slide_SPDT_Straight_CK_OS102011MS2Q",
     {"1": "/BAT_P", "2": "/BAT_SW", "3": None}),
    ("J2",  "Connector_PinHeader_2.54mm.pretty",
     "PinHeader_1x02_P2.54mm_Vertical",
     {"1": "/BAT_P", "2": "/BAT_SW"}),
    ("J5",  "Connector_PinHeader_2.54mm.pretty",
     "PinHeader_1x02_P2.54mm_Vertical",
     {"1": "/BAT_SW", "2": "/GND"}),
    # R3/R4/C8 midpoint uses the EXISTING /BTN1 net (which is the U1.1
    # pad — D0/GPIO1). The `inject_battery_section()` post-step renames
    # the net to /VBAT_SENSE via text substitution after SaveBoard,
    # because pcbnew's SetNetname() doesn't update the lookup table
    # in-process.
    ("R3",  "Resistor_SMD.pretty",
     "R_0805_2012Metric_Pad1.20x1.40mm_HandSolder",
     {"1": "/BAT_SW", "2": "/BTN1"}),
    ("R4",  "Resistor_SMD.pretty",
     "R_0805_2012Metric_Pad1.20x1.40mm_HandSolder",
     {"1": "/BTN1", "2": "/GND"}),
    ("C8",  "Capacitor_SMD.pretty",
     "C_0805_2012Metric_Pad1.18x1.45mm_HandSolder",
     {"1": "/BTN1", "2": "/GND"}),
]


def _ensure_net(board, name: str):
    """Return the NETINFO_ITEM for `name`, creating it if missing."""
    n = board.FindNet(name)
    if n is not None and n.GetNetname() == name:
        return n
    new_net = pcbnew.NETINFO_ITEM(board, name)
    board.Add(new_net)
    return board.FindNet(name)


def _has_footprint(board, ref: str) -> bool:
    for fp in board.GetFootprints():
        if fp.GetReference() == ref:
            return True
    return False


def _add_footprint(board, ref: str, library: str, fp_name: str,
                   pad_nets: dict) -> bool:
    """Load a footprint from the system KiCad library and add it to the
    board with the given pad net assignments. Position is a placeholder
    (0, 0) — the layout pass moves it later."""
    lib_path = KICAD_FP_ROOT / library
    fp = pcbnew.FootprintLoad(str(lib_path), fp_name)
    if fp is None:
        print(f"  [ERROR] can't load {library}/{fp_name}")
        return False
    fp.SetReference(ref)
    # Placeholder position; place_components.py overrides via PLACEMENTS.
    fp.SetPosition(pcbnew.VECTOR2I(int(150e6), int(140e6)))

    for pad in fp.Pads():
        pin = pad.GetNumber()
        if pin not in pad_nets:
            continue
        net_name = pad_nets[pin]
        if net_name is None:
            continue
        net = _ensure_net(board, net_name)
        pad.SetNet(net)

    board.Add(fp)
    print(f"  added {ref} ({fp_name}) at placeholder pos")
    return True


def inject_battery_section(pcb_path: Path) -> int:
    """Idempotent: load board, add /BAT_P and /BAT_SW nets, add missing
    battery footprints with proper pad-net assignments, save, then
    post-process the file to rename /BTN1 → /VBAT_SENSE consistently
    (pcbnew's SetNetname doesn't update the lookup table, so renaming
    in-process is unreliable — text substitution is robust).
    Returns number of new footprints added."""
    board = pcbnew.LoadBoard(str(pcb_path))

    # 1. Ensure /BAT_P and /BAT_SW exist as new nets (BAT chain).
    _ensure_net(board, "/BAT_P")
    _ensure_net(board, "/BAT_SW")

    # 2. Add missing footprints. R3/R4/C8 midpoint pads use the existing
    #    /BTN1 net; we rename to /VBAT_SENSE in step 4.
    added = 0
    for ref, library, fp_name, pad_nets in TARGETS:
        if _has_footprint(board, ref):
            continue
        if _add_footprint(board, ref, library, fp_name, pad_nets):
            added += 1

    # 3. Save the board (so the new footprints + nets land on disk).
    pcbnew.SaveBoard(str(pcb_path), board)
    print(f"  saved {pcb_path.name} ({added} new footprint{'s' if added != 1 else ''})")

    # 4. Text-pass: rename /BTN1 → /VBAT_SENSE everywhere in the file.
    _rename_net_in_file(pcb_path, "/BTN1", "/VBAT_SENSE")

    return added


def main():
    import argparse
    p = argparse.ArgumentParser()
    # Repathed for refactor/restructure-2026-05 (deep migration): script at projects/mt1/tools/,
    # KiCad project at projects/mt1/kicad/
    _repo_root = Path(__file__).resolve().parents[3]
    p.add_argument("--pcb", type=Path,
                   default=_repo_root / "projects" / "mt1" / "kicad" / "mt1-pcb.kicad_pcb")
    args = p.parse_args()
    inject_battery_section(args.pcb)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
