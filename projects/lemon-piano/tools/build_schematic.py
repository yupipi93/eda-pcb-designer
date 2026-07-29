#!/usr/bin/env python3
"""Build the Lemon Piano V5.5 schematic via kicad-sch-api.

Mirrors the PCB exactly (docs/NETLIST.md): 43 electrical components
(mounting holes H1/H2 are mechanical-only and stay out of the schematic,
MT1 convention). Flat single sheet, local labels, PWR_FLAGs on the three
power-source nets. Net names come out as "/<NAME>" matching the board.

Runs inside the eda-pcb-designer Docker image:

    docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
        -v "$PWD":/work -w /work --entrypoint python3 \
        eda-pcb-designer:latest projects/lemon-piano/tools/build_schematic.py

Idempotent: fixed title-block date, deterministic UUID rewrite pass.
"""
from __future__ import annotations

import os
import re
import sys
import uuid
from pathlib import Path

import kicad_sch_api as ksa

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from pcb_designer.schematic import add_pwr_flag, auto_label, g  # noqa: E402

import yaml  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
PROJ_DIR = REPO_ROOT / "projects" / "lemon-piano" / "kicad"
CFG = yaml.safe_load((REPO_ROOT / "projects/lemon-piano/lemon-piano.yaml")
                     .read_text(encoding="utf-8"))

R_FP = "Resistor_SMD:R_0805_2012Metric_Pad1.20x1.40mm_HandSolder"
C_FP = "Capacitor_SMD:C_0805_2012Metric_Pad1.18x1.45mm_HandSolder"
SOCKET_FP = "Connector_PinSocket_2.54mm:PinSocket_1x15_P2.54mm_Vertical"


def build() -> None:
    version = CFG["project"]["version"]
    sch = ksa.create_schematic("lemon-piano")
    sch.set_title_block(
        title="Lemon Piano V5.5 Board",
        date="2026-07-30",
        rev=version, company="Lemon Piano",
        comments={1: "V5 game board + V5.5 power-entry filter (TVS + Schottky + CLC pi)",
                  2: "Netlist ground truth: projects/lemon-piano/docs/NETLIST.md"})

    # ── Nano sockets (2×15) ─────────────────────────────────────────────
    sch.components.add(lib_id="Connector_Generic:Conn_01x15",
                       reference="U1", value="Nano_socket_A",
                       position=g(60, 100), footprint=SOCKET_FP)
    auto_label(sch, "U1", {
        "1": None,                     # TX1
        "2": None,                     # RX0
        "3": None,                     # RST
        "4": ("GND", "left"),
        "5": ("LED1", "left"),         # D2
        "6": ("LED2", "left"),
        "7": ("LED3", "left"),
        "8": ("LED4", "left"),
        "9": ("LED5", "left"),
        "10": ("LED6", "left"),
        "11": ("LED7", "left"),
        "12": ("LED8", "left"),
        "13": ("LED9", "left"),
        "14": ("LED10", "left"),       # D11
        "15": ("SENS_PLUS", "left"),   # D12
    })
    sch.components.add(lib_id="Connector_Generic:Conn_01x15",
                       reference="U2", value="Nano_socket_B",
                       position=g(90, 100), footprint=SOCKET_FP)
    auto_label(sch, "U2", {
        "1": ("BUZZER", "right"),      # D13
        "2": None,                     # 3V3
        "3": None,                     # AREF
        "4": ("KEY1", "right"),        # A0
        "5": ("KEY2", "right"),
        "6": ("KEY3", "right"),
        "7": ("KEY4", "right"),
        "8": ("KEY5", "right"),
        "9": ("KEY6", "right"),
        "10": ("KEY7", "right"),       # A6
        "11": ("SENS_MINUS", "right"), # A7
        "12": ("+5V", "right"),        # 5V pin — rail feeds here
        "13": None,                    # RST
        "14": ("GND", "right"),
        "15": None,                    # VIN (unused by design)
    })

    # ── service-edge connectors ─────────────────────────────────────────
    sch.components.add(lib_id="Connector:Screw_Terminal_01x02",
                       reference="J1", value="5V_IN",
                       position=g(30, 40),
                       footprint="TerminalBlock_Phoenix:TerminalBlock_Phoenix_"
                                 "MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal")
    auto_label(sch, "J1", {"1": ("VIN", "right"), "2": ("GND", "right")})

    sch.components.add(lib_id="Connector_Generic:Conn_01x08",
                       reference="J2", value="LEMON_KEYS",
                       position=g(120, 100),
                       footprint="Connector_PinHeader_2.54mm:PinHeader_1x08_P2.54mm_Vertical")
    auto_label(sch, "J2", {
        "1": ("GND", "right"),
        "2": ("KEY7", "right"), "3": ("KEY6", "right"), "4": ("KEY5", "right"),
        "5": ("KEY4", "right"), "6": ("KEY3", "right"), "7": ("KEY2", "right"),
        "8": ("KEY1", "right"),
    })

    # ── power-entry filter ──────────────────────────────────────────────
    sch.components.add(lib_id="Device:D_TVS", reference="D1", value="P6KE6.8A",
                       position=g(45, 50),
                       footprint="Diode_THT:D_DO-15_P5.08mm_Vertical_KathodeUp")
    auto_label(sch, "D1", {"1": ("VIN", "up"), "2": ("GND", "down")})

    sch.components.add(lib_id="Device:D_Schottky", reference="D2", value="1N5817",
                       position=g(60, 40),
                       footprint="Diode_THT:D_DO-41_SOD81_P5.08mm_Vertical_AnodeUp")
    auto_label(sch, "D2", {"1": ("VRAW", "right"), "2": ("VIN", "left")})

    sch.components.add(lib_id="Device:C_Polarized", reference="C1", value="470uF/16V",
                       position=g(75, 50),
                       footprint="Capacitor_THT:CP_Radial_D8.0mm_P3.50mm")
    auto_label(sch, "C1", {"1": ("VRAW", "up"), "2": ("GND", "down")})

    sch.components.add(lib_id="Device:C", reference="C2", value="100nF",
                       position=g(85, 50), footprint=C_FP)
    auto_label(sch, "C2", {"1": ("VRAW", "up"), "2": ("GND", "down")})

    sch.components.add(lib_id="Device:L", reference="L1", value="100uH",
                       position=g(95, 40),
                       footprint="Inductor_THT:L_Radial_D8.7mm_P5.00mm_Fastron_07HCP")
    auto_label(sch, "L1", {"1": ("VRAW", "left"), "2": ("+5V", "right")})

    sch.components.add(lib_id="Device:C_Polarized", reference="C3", value="470uF/16V",
                       position=g(105, 50),
                       footprint="Capacitor_THT:CP_Radial_D8.0mm_P3.50mm")
    auto_label(sch, "C3", {"1": ("+5V", "up"), "2": ("GND", "down")})

    sch.components.add(lib_id="Device:C", reference="C4", value="100nF",
                       position=g(115, 50), footprint=C_FP)
    auto_label(sch, "C4", {"1": ("+5V", "up"), "2": ("GND", "down")})

    # ── key pull-ups + SENS− pull-up ────────────────────────────────────
    for i in range(1, 8):
        sch.components.add(lib_id="Device:R", reference=f"R{i}", value="220",
                           position=g(140 + 12 * (i - 1), 40), footprint=R_FP)
        auto_label(sch, f"R{i}", {"1": ("+5V", "up"), "2": (f"KEY{i}", "down")})
    sch.components.add(lib_id="Device:R", reference="R18", value="10k",
                       position=g(140 + 12 * 7, 40), footprint=R_FP)
    auto_label(sch, "R18", {"1": ("+5V", "up"), "2": ("SENS_MINUS", "down")})

    # ── LED bar + series resistors ──────────────────────────────────────
    for i in range(1, 11):
        led_ref = f"D{i + 2}"
        r_ref = f"R{i + 7}"
        x = 140 + 12 * (i - 1)
        sch.components.add(lib_id="Device:LED", reference=led_ref,
                           value=f"GREEN_LED{i}", position=g(x, 80),
                           footprint="LED_THT:LED_D3.0mm")
        auto_label(sch, led_ref, {"2": (f"LED{i}", "up"),      # anode
                                  "1": (f"LED{i}_K", "down")})  # cathode
        sch.components.add(lib_id="Device:R", reference=r_ref, value="220",
                           position=g(x, 95), footprint=R_FP)
        auto_label(sch, r_ref, {"2": (f"LED{i}_K", "up"), "1": ("GND", "down")})

    # ── UI ──────────────────────────────────────────────────────────────
    sch.components.add(lib_id="Device:Buzzer", reference="BUZ1",
                       value="passive_buzzer", position=g(30, 80),
                       footprint="Buzzer_Beeper:Buzzer_12x9.5RM7.6")
    auto_label(sch, "BUZ1", {"1": ("BUZZER", "left"), "2": ("GND", "left")})

    sch.components.add(lib_id="Switch:SW_Push", reference="SW1", value="SENS+",
                       position=g(30, 95),
                       footprint="Button_Switch_THT:SW_PUSH_6mm")
    auto_label(sch, "SW1", {"1": ("SENS_PLUS", "left"), "2": ("GND", "right")})

    sch.components.add(lib_id="Switch:SW_Push", reference="SW2", value="SENS-",
                       position=g(30, 110),
                       footprint="Button_Switch_THT:SW_PUSH_6mm")
    auto_label(sch, "SW2", {"1": ("SENS_MINUS", "left"), "2": ("GND", "right")})

    # ── PWR_FLAGs: VIN is sourced by J1; +5V by the choke; GND by J1.2 ──
    add_pwr_flag(sch, (30, 25), "VIN", "01")
    add_pwr_flag(sch, (40, 25), "+5V", "02")
    add_pwr_flag(sch, (50, 25), "GND", "03")

    out = PROJ_DIR / CFG["project"]["kicad_sch_file"]
    sch.save(str(out))
    txt = out.read_text(encoding="utf-8")
    txt = deterministic_uuids(txt)
    out.write_text(txt, encoding="utf-8")
    print(f"  {out.name} -> {len(list(sch.components))} components")


def deterministic_uuids(text: str) -> str:
    """Deterministic per-object UUIDs (byte-stable re-runs, unique each).

    Builds an old→new map in order of first appearance, then applies it
    to EVERY occurrence — including the sheet-instance `(path "/<uuid>")`
    references, which must stay consistent with the root sheet's uuid."""
    ns = uuid.uuid5(uuid.NAMESPACE_DNS, "lemon-piano.sch.pcb-designer")
    mapping: dict[str, str] = {}
    uuid_re = re.compile(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
    for m in uuid_re.finditer(text):
        if m.group(0) not in mapping:
            mapping[m.group(0)] = str(uuid.uuid5(ns, f"obj-{len(mapping) + 1}"))
    return uuid_re.sub(lambda m: mapping[m.group(0)], text)


def main() -> None:
    if "KICAD_SYMBOL_DIR" not in os.environ:
        cand = Path("/usr/share/kicad/symbols")
        if cand.is_dir():
            os.environ["KICAD_SYMBOL_DIR"] = str(cand)
    print("Building lemon-piano schematic...")
    build()
    print("Validate: kicad-cli sch erc projects/lemon-piano/kicad/lemon-piano.kicad_sch")


if __name__ == "__main__":
    main()
