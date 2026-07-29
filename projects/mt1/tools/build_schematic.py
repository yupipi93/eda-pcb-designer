#!/usr/bin/env python3
"""
Build the MT1 PCB schematic via kicad-sch-api — v0.1.0 with the
battery-management subsystem in sync with the PCB.

v0.1.0 additions on top of the previous slim canvas (5 module sockets
+ J4 proto header):

  Battery chain:
    J1 (JST-PH 2-pin)  – LiPo connector
    SW1 (SPDT slide)   – armament / disconnect switch
    J2 (1x2 header)    – parallel to SW1 for an OPTIONAL external switch
                         (jumper closed = always on; jumper open = SW1
                         controls)
    J5 (1x2 header)    – tap-out to the XIAO BAT+/BAT- pads on the
                         module's underside (manually-soldered wires)

  Voltage sense to the XIAO ADC (D0 / GPIO1):
    R3, R4 (100 kΩ 0805 HandSolder) – 1:2 divider
    C8 (100 nF 0805 HandSolder)     – RC filter at the ADC input

  Net rename: BTN1 → VBAT_SENSE. The pin used to be the BTN1 line in
  the original plan but SW2 (the button) was scoped out; D0 is now
  driven by the divider midpoint.

  PWR_FLAG added for BAT_P (raw battery rail, new power source net).

Schematic strategy unchanged: flat single sheet, local labels,
PWR_FLAGs. ERC clean by construction.

Run with:
    KICAD_SYMBOL_DIR=~/.local/share/AppImages/kicad-9.0.7/usr/share/kicad/symbols \
    /tmp/kicad-tool-venv/bin/python projects/mt1/tools/build_schematic.py
"""
import os
import sys
from pathlib import Path

import kicad_sch_api as ksa

# Make the pcb_designer package importable when this script is run directly
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from pcb_designer.schematic import (  # noqa: E402
    GRID,
    g,
    label_pin,
    nc_pin,
    auto_label,
    add_pwr_flag,
)

# Repathed for refactor/restructure-2026-05 (deep migration): script lives at
# projects/mt1/tools/, KiCad project at projects/mt1/kicad/
REPO_ROOT = Path(__file__).resolve().parents[3]
PROJ_DIR = REPO_ROOT / "projects" / "mt1" / "kicad"
SHEETS_DIR = PROJ_DIR / "sheets"


def build_slim_schematic():
    """Slim schematic — mirrors the PCB v0.0.14 contents exactly.

    Only the components that are physically placed on the PCB are
    instantiated here (5 modules + J4 prototyping header). Mounting holes
    H1..H6 are mechanical-only (handled directly by place_components.py)
    and don't appear in the schematic.

    The full design (power chain, UI, debug, decoupling, test points) is
    catalogued in `docs/REMOVED_COMPONENTS.md` — see §7 for the suggested
    reincorporation order, and §8 for how to re-add to the schematic. The
    pre-trim version lives in git history (commit a171c0c).
    """
    sch = ksa.create_schematic("mt1-pcb")
    sch.set_title_block(title="MT1 Flight Computer (v0.1.0 — battery + sensors)",
                        date="2026-05-22",
                        rev="v0.1.0", company="MultitecUA",
                        comments={1: "Battery management + VBAT sensing on D0/ADC1_CH0",
                                  2: "See docs/CHANGELOG.md v0.1.0 entry for the power-chain rationale."})

    # ==================================================================
    # MCU — XIAO ESP32S3 Plus (split into two 1x7 female sockets)
    # ==================================================================

    # U1 — XIAO LEFT header (7 pins): D0..D6
    sch.components.add(lib_id="Connector_Generic:Conn_01x07",
                       reference="U1", value="XIAO_left_socket",
                       position=g(120, 120),
                       footprint="Connector_PinSocket_2.54mm:PinSocket_1x07_P2.54mm_Vertical")
    auto_label(sch, "U1", {
        # D0 / GPIO1 / ADC1_CH0: in v0.1.0 this pin reads the LiPo voltage
        # via the R3/R4 divider midpoint (was BTN1 in pre-v0.1.0 plans).
        "1": ("VBAT_SENSE", "left"),
        "2": ("BTN2",    "left"),  # D1 / GPIO2
        "3": ("LED1",    "left"),  # D2 / GPIO3
        "4": ("LED2",    "left"),  # D3 / GPIO4
        "5": ("I2C_SDA", "left"),  # D4 / GPIO5
        "6": ("I2C_SCL", "left"),  # D5 / GPIO6
        "7": ("DBG_TX",  "left"),  # D6 / GPIO43 — routed to J4 in v0.0.14
    })

    # U5 — XIAO RIGHT header (7 pins): 5V, GND, 3V3, D10, D9, D8, D7
    sch.components.add(lib_id="Connector_Generic:Conn_01x07",
                       reference="U5", value="XIAO_right_socket",
                       position=g(150, 120),
                       footprint="Connector_PinSocket_2.54mm:PinSocket_1x07_P2.54mm_Vertical")
    auto_label(sch, "U5", {
        "1": (None, None),          # 5V (USB) — no consumer in slim design (NC)
        "2": ("GND",      "right"),
        "3": ("+3V3",     "right"),
        "4": ("SDIO_CMD", "right"), # D10 / GPIO9
        "5": ("SDIO_D0",  "right"), # D9  / GPIO8
        "6": ("SDIO_CLK", "right"), # D8  / GPIO7
        "7": ("DBG_RX",   "right"), # D7 / GPIO44 — routed to J4 in v0.0.14
    })

    # ==================================================================
    # J4 — Prototyping header (1x8) for unused XIAO pins
    # ==================================================================
    # Added in v0.0.14. Physically placed above the XIAO sockets on the
    # PCB; exposes the GPIOs that aren't currently routed to any sensor,
    # plus +3V3/GND so the user can drive new components in bench tests
    # with dupont wires.
    sch.components.add(lib_id="Connector_Generic:Conn_01x08",
                       reference="J4", value="proto_header",
                       position=g(50, 165),
                       footprint="Connector_PinHeader_2.54mm:PinHeader_1x08_P2.54mm_Vertical")
    auto_label(sch, "J4", {
        # J4.1 doubles as a VBAT_SENSE test point (same net as the
        # divider midpoint + XIAO D0). Probe with a multimeter to read
        # raw ADC input voltage.
        "1": ("VBAT_SENSE", "left"),
        "2": ("BTN2",   "left"),   # D1 / GPIO2 — free for a future button
        "3": ("LED1",   "left"),   # D2 / GPIO3 — free for a future LED
        "4": ("LED2",   "left"),   # D3 / GPIO4 — free for a future LED
        "5": ("DBG_TX", "left"),   # D6 / GPIO43
        "6": ("DBG_RX", "left"),   # D7 / GPIO44
        "7": ("+3V3",   "left"),
        "8": ("GND",    "left"),
    })

    # ==================================================================
    # SENSORS — LSM6DSO32 (1x9) + BMP585 (1x8). I²C bus only.
    # ==================================================================

    # U2 — LSM6DSO32 socket: 9 pins (Vin, 3Vo, GND, SCL, SDA, DO, CS, I1, I2)
    sch.components.add(lib_id="Connector_Generic:Conn_01x09",
                       reference="U2", value="LSM6DSO32_socket",
                       position=g(210, 120),
                       footprint="Connector_PinSocket_2.54mm:PinSocket_1x09_P2.54mm_Vertical")
    auto_label(sch, "U2", {
        "1": ("+3V3", "right"),
        "2": (None, None),         # 3Vo (LDO out — unused on breakout side)
        "3": ("GND", "right"),
        "4": ("I2C_SCL", "right"),
        "5": ("I2C_SDA", "right"),
        "6": (None, None),         # DO / SDO (I2C addr)
        "7": (None, None),         # CS
        "8": (None, None),         # I1 (INT1)
        "9": (None, None),         # I2 (INT2)
    })

    # U3 — BMP585 socket: 1x8 single row.
    # v0.1.2 (BLK-007 / POST-MORTEM-001 / ERRATA-001 §10): the Adafruit BMP585
    # header is  Vin 3Vo GND SCL [SDO] [SDA] CS INT  — SDO sits BETWEEN SCL and
    # SDA (unlike the LSM6, where SDA is pin 5). So I2C_SDA must land on pin 6
    # (real SDA), and pin 5 (SDO) stays NC (→ I2C address 0x47).
    #   1=Vin, 2=3Vo, 3=GND, 4=SCL, 5=SDO, 6=SDA, 7=CS, 8=INT
    sch.components.add(lib_id="Connector_Generic:Conn_01x08",
                       reference="U3", value="BMP585_socket",
                       position=g(245, 120),
                       footprint="Connector_PinSocket_2.54mm:PinSocket_1x08_P2.54mm_Vertical")
    auto_label(sch, "U3", {
        "1": ("+3V3", "right"),
        "2": (None, None),         # 3Vo
        "3": ("GND", "right"),
        "4": ("I2C_SCL", "right"),
        "5": (None, None),         # SDO (NC → addr 0x47)
        "6": ("I2C_SDA", "right"), # SDA real (pin 6)
        "7": (None, None),         # CS
        "8": (None, None),         # INT
    })

    # ==================================================================
    # STORAGE — microSD socket 1x9 (Adafruit SDIO/SPI breakout)
    # ==================================================================
    # Pin map: 1=3V, 2=GND, 3=CLK, 4=D0/SO, 5=CMD/SI, 6=D3/CS, 7=D1, 8=DAT2, 9=DET
    # SDIO-1 mode uses pins 1..5 only; the rest (6..9) are NC.
    sch.components.add(lib_id="Connector_Generic:Conn_01x09",
                       reference="U4", value="microSD_socket",
                       position=g(280, 120),
                       footprint="Connector_PinSocket_2.54mm:PinSocket_1x09_P2.54mm_Vertical")
    auto_label(sch, "U4", {
        "1": ("+3V3",     "right"),
        "2": ("GND",      "right"),
        "3": ("SDIO_CLK", "right"),
        "4": ("SDIO_D0",  "right"),
        "5": ("SDIO_CMD", "right"),
        "6": (None, None),
        "7": (None, None),
        "8": (None, None),
        "9": (None, None),
    })

    # ==================================================================
    # BATTERY CHAIN — v0.1.0
    #
    # Logical flow (LiPo+ → … → XIAO BAT+):
    #
    #     LiPo+  J1.1 ─ BAT_P ─┬─ SW1.1 (common)
    #                          │                     SW1.2 (throw A) ── BAT_SW ─┬─ J5.1 → XIAO BAT+
    #                          │                     SW1.3 (throw B, NC)         │
    #                          └─ J2.1 ── ext sw ── J2.2 ────────────────────────┤
    #                                                                            ├─ R3 100k ─┬─ VBAT_SENSE → D0/ADC1
    #                                                                            │           ├─ R4 100k ─┐
    #                                                                            │           └─ C8 100nF ┤
    #     LiPo−  J1.2 ─ GND ───────────────────────────────────────── J5.2 ──────┴───────────────────────┴─ GND plane
    #
    # SW1 and J2 in parallel: either path closed → BAT_SW energised.
    # Both open → system off. J2.3 (SW1's other throw) is left NC.
    # ==================================================================

    # J1 — LiPo battery in (1x02 pin header, v0.1.3; was a JST-PH).
    # v0.1.3 (2026-06-16): converted JST→pin header to free top-strip width
    # for the module mounting holes. Polarity follows the ADAFRUIT convention
    # → pin 1 = GND (−), pin 2 = + (BAT_P). Silk +/- on the PCB. NOTE:
    # vendor-dependent — verify the battery wiring with a multimeter (the
    # battery now mates via a wire/JST-to-header pigtail).
    sch.components.add(lib_id="Connector_Generic:Conn_01x02",
                       reference="J1", value="LiPo_battery_hdr",
                       position=g(40, 80),
                       footprint="Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical")
    auto_label(sch, "J1", {
        "1": ("GND",   "left"),   # Adafruit pin 1 = GND
        "2": ("BAT_P", "left"),   # Adafruit pin 2 = +
    })

    # SW1 — armament / battery disconnect (SPDT slide)
    # Pad map (per `SW_Slide_SPDT_Straight_CK_OS102011MS2Q`):
    #   1 = common, 2 = throw A (ON), 3 = throw B (OFF / NC)
    sch.components.add(lib_id="Switch:SW_SPDT",
                       reference="SW1", value="arming_switch",
                       position=g(60, 80),
                       footprint="Button_Switch_THT:SW_Slide_SPDT_Straight_CK_OS102011MS2Q")
    auto_label(sch, "SW1", {
        "1": ("BAT_P",  "left"),
        "2": ("BAT_SW", "right"),
        "3": (None, None),  # throw B → OFF position, intentionally NC
    })

    # J2 — external switch / jumper header (parallel to SW1)
    # Pin 1 = BAT_P (input side), Pin 2 = BAT_SW (output side).
    # Closing a jumper across J2 bypasses SW1 (system always-on).
    sch.components.add(lib_id="Connector_Generic:Conn_01x02",
                       reference="J2", value="ext_switch_header",
                       position=g(80, 80),
                       footprint="Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical")
    auto_label(sch, "J2", {
        "1": ("BAT_P",  "right"),
        "2": ("BAT_SW", "right"),
    })

    # ── VBAT voltage divider (R3 top, R4 bottom) + filter cap C8 ────────
    # V_adc = V_BAT * R4 / (R3 + R4) = V_BAT * 0.5
    # 4.20 V → 2.10 V ADC ; 3.00 V → 1.50 V ADC (full scale 3.1 V at 11 dB att.)
    sch.components.add(lib_id="Device:R",
                       reference="R3", value="100k",
                       position=g(105, 80),
                       footprint="Resistor_SMD:R_0805_2012Metric_Pad1.20x1.40mm_HandSolder")
    auto_label(sch, "R3", {
        "1": ("BAT_SW",     "up"),
        "2": ("VBAT_SENSE", "down"),
    })

    sch.components.add(lib_id="Device:R",
                       reference="R4", value="100k",
                       position=g(105, 100),
                       footprint="Resistor_SMD:R_0805_2012Metric_Pad1.20x1.40mm_HandSolder")
    auto_label(sch, "R4", {
        "1": ("VBAT_SENSE", "up"),
        "2": ("GND",        "down"),
    })

    sch.components.add(lib_id="Device:C",
                       reference="C8", value="100nF",
                       position=g(115, 100),
                       footprint="Capacitor_SMD:C_0805_2012Metric_Pad1.18x1.45mm_HandSolder")
    auto_label(sch, "C8", {
        "1": ("VBAT_SENSE", "up"),
        "2": ("GND",        "down"),
    })

    # J5 — switched-battery OUTPUT (1x02 pin header, v0.1.3; was a vertical
    # JST-PH in v0.1.2). Carries the switched rail BAT_SW and GND to the XIAO
    # BAT pads. v0.1.3: back to a pin header (frees space) + moved to the
    # service edge. Polarity: pin 1 = GND (−), pin 2 = + (BAT_SW).
    sch.components.add(lib_id="Connector_Generic:Conn_01x02",
                       reference="J5", value="LiPo_out_hdr",
                       position=g(130, 80),
                       footprint="Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical")
    auto_label(sch, "J5", {
        "1": ("GND",    "right"),  # Adafruit pin 1 = GND
        "2": ("BAT_SW", "right"),  # Adafruit pin 2 = +
    })

    # ==================================================================
    # PWR_FLAGs — every "power source" net needs an explicit flag for ERC.
    # ==================================================================
    add_pwr_flag(sch, (300, 80), "+3V3",  "01")
    add_pwr_flag(sch, (315, 80), "GND",   "02")
    # BAT_P is sourced by the LiPo (J1.1) → mark as power input so ERC
    # doesn't complain "power output net BAT_P not driven".
    add_pwr_flag(sch, (40, 70),  "BAT_P", "03")

    out = PROJ_DIR / "mt1-pcb.kicad_sch"
    sch.save(str(out))
    print(f"  mt1-pcb.kicad_sch -> {len(list(sch.components))} components")


def main():
    if "KICAD_SYMBOL_DIR" not in os.environ:
        for cand in (
            Path("/usr/share/kicad/symbols"),                                  # apt / PPA install
            Path.home() / ".local/share/AppImages/kicad-9.0.7/usr/share/kicad/symbols",  # AppImage
        ):
            if cand.is_dir():
                os.environ["KICAD_SYMBOL_DIR"] = str(cand)
                break
    print("Building MT1 slim schematic (mirrors PCB v0.0.14)...")
    build_slim_schematic()
    print("\nDone. Validate: kicad-cli sch erc projects/mt1/kicad/mt1-pcb.kicad_sch")
    print("Next: open KiCad → Tools → Update PCB from Schematic")


if __name__ == "__main__":
    main()
