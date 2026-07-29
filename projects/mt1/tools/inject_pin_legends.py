#!/usr/bin/env python3
"""Inject per-pad silkscreen pin legends on BOTH faces of the MT1 board.

Every module/connector pad gets its function name printed in silkscreen so the
pinout is readable from either side of the board (the module body hides the
silk on its own face; the opposite-face copy stays visible). Labels come from
the GROUND-TRUTH physical pin names (projects/mt1/ground-truth/components.yaml)
for the breakout modules, and from an explicit map for the bare connectors.

The text per pad is VERIFIED against the pad's actual net: for module pads whose
ground-truth pin carries a net, the label is only emitted if the board pad sits
on that net (mismatches are reported and abort, so a wrong label can't ship).

Idempotent: removes its own previous output (silk text at height TH) before
re-emitting, so it is safe to re-run / call from the pipeline.

  F+B (no pre-existing per-pin silk):  U1 U2 U3 U4 U5 J2
  B only (F already exists):           J1 J5 (the +/- polarity) and J4 (proto)

Run with the SYSTEM python (pcbnew):
    python3 projects/mt1/tools/inject_pin_legends.py [board.kicad_pcb]
"""
from __future__ import annotations

import sys
from pathlib import Path

import pcbnew
import yaml

NM = 1_000_000
TH = 0.8           # silk text height (mm) — board min text height rule = 0.8mm
TW = 0.65          # silk text width (mm) — narrower so longer names (INT1/DAT2) fit
THK = 0.12         # stroke thickness (mm)
OFFSET = 2.0       # mm from pad center to label center (perpendicular, outward)

PCB_DIR = Path(__file__).resolve().parents[3]
DEFAULT_PCB = PCB_DIR / "projects" / "mt1" / "kicad" / "mt1-pcb.kicad_pcb"
GT_PATH = PCB_DIR / "projects" / "mt1" / "ground-truth" / "components.yaml"

# Bare connectors are not in the ground-truth (it only models the breakouts).
CONN_LABELS = {
    "J1": {"1": "-", "2": "+"},                 # LiPo in   (GND, BAT_P)
    "J5": {"1": "-", "2": "+"},                 # LiPo out  (GND, BAT_SW)
    "J2": {"1": "BAT", "2": "SW"},              # keyswitch (BAT_P, BAT_SW)
    "J4": {"1": "D0", "2": "D1", "3": "D2", "4": "D3",
           "5": "D6", "6": "D7", "7": "3V3", "8": "GND"},
}
# Outward perpendicular direction (unit, away from the module body) per ref.
HINT = {"U1": (1, 0), "U5": (-1, 0), "U2": (0, 1), "U3": (-1, 0), "U4": (0, 1),
        "J1": (0, 1), "J2": (0, 1), "J5": (0, 1), "J4": (0, 1)}
FB_REFS = {"U1", "U2", "U3", "U4", "U5", "J2"}   # emit on F + B silk
B_ONLY = {"J1", "J5", "J4"}                       # F silk already present


def build_labels(gt: dict):
    """{ref: {pad: func}} from ground-truth modules + connector overrides, and
    {ref.pad: expected_net} for verification."""
    labels, expnet = {}, {}
    for comp in gt["components"].values():
        for pin, info in comp.get("pins", {}).items():
            ref, pad = pin.split(".")
            labels.setdefault(ref, {})[pad] = str(info["func"])
            expnet[pin] = info.get("net")
    for ref, d in CONN_LABELS.items():
        labels[ref] = dict(d)
    return labels, expnet


def inject(pcb_path: Path) -> int:
    gt = yaml.safe_load(GT_PATH.read_text())
    labels, expnet = build_labels(gt)
    bd = pcbnew.LoadBoard(str(pcb_path))

    # pass 1 (read-only): pad global positions + nets
    pads = []   # (ref, padnum, x, y, net)
    for fp in bd.GetFootprints():
        ref = fp.GetReference()
        if ref not in labels:
            continue
        for pd in fp.Pads():
            p = pd.GetPosition()
            pads.append((ref, pd.GetNumber(), p.x / NM, p.y / NM, pd.GetNetname()))

    # verify label<->net for module pads with an expected net
    mism = []
    for ref, num, x, y, net in pads:
        key = f"{ref}.{num}"
        want = expnet.get(key)
        if want is not None and net != want:
            mism.append(f"{key} label={labels[ref].get(num)} net={net} expected={want}")
    if mism:
        print("ABORT: label<->net mismatches (would mislabel a pad):")
        for m in mism:
            print("  ", m)
        return 1

    # idempotency: drop our previous silk output. Generator labels are the only
    # board-level silk text in the small-height band (0.45–0.85mm); the version
    # label, ANCHOR/Made-on-Earth, ref designators and the connector +/- are all
    # ≥1mm, so they survive. Robust to a prior run using a different height.
    removed = 0
    for d in list(bd.GetDrawings()):
        if isinstance(d, pcbnew.PCB_TEXT) and d.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS):
            if 0.45 < d.GetTextHeight() / NM < 0.85:
                bd.RemoveNative(d)
                removed += 1

    # pass 2: emit labels
    n = 0
    for ref, num, x, y, net in pads:
        lab = labels[ref].get(num)
        if lab is None:
            continue
        dx, dy = HINT[ref]
        px, py = x + dx * OFFSET, y + dy * OFFSET
        ang = 0 if dx != 0 else 90      # text reads perpendicular to the pad row
        layers = ((pcbnew.F_SilkS, False), (pcbnew.B_SilkS, True)) if ref in FB_REFS \
            else ((pcbnew.B_SilkS, True),)
        for layer, mirror in layers:
            t = pcbnew.PCB_TEXT(bd)
            t.SetText(lab)
            t.SetLayer(layer)
            t.SetMirrored(mirror)
            t.SetTextSize(pcbnew.VECTOR2I(int(TW * NM), int(TH * NM)))
            t.SetTextThickness(int(THK * NM))
            t.SetTextAngle(pcbnew.EDA_ANGLE(ang, pcbnew.DEGREES_T))
            t.SetPosition(pcbnew.VECTOR2I(int(px * NM), int(py * NM)))
            bd.Add(t)
            n += 1

    pcbnew.SaveBoard(str(pcb_path), bd)
    print(f"  pin legends: removed {removed} prior, emitted {n} silk labels "
          f"({len(FB_REFS)} refs F+B, {len(B_ONLY)} refs B-only) · 0 net mismatches")
    return 0


if __name__ == "__main__":
    pcb = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PCB
    raise SystemExit(inject(pcb))
