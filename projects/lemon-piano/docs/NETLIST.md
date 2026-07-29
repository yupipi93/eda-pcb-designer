# NETLIST.md — Lemon Piano V5.5 Board

Ground truth for the PCB. Extracted 2026-07-30 from the `arduino-lemon-piano`
repo — **no value, pin or part invented here**. Sources:

| Source | What it fixes |
|---|---|
| `versions/v5.5-power-filter/HARDWARE.md` | power-entry filter chain, part values, BOM delta |
| `versions/v5-led-bar/HARDWARE.md` (pin map, 2026-07-28) | every Nano pin assignment |
| `tools/wiring_diagrams.py` → `build_v5_5()` (DRC-validated wirewright contract) | the authoritative net list (58 nets rendering, 0 violations) |

> The V5 HARDWARE.md *BOM table* contains two stale rows ("Passive buzzer D8",
> "SENS + on D7"). The 2026-07-28 pin map in the same file and the
> `build_v5_5()` contract agree and override them: **buzzer = D13,
> SENS + = D12, SENS − = A7**. Recorded in DECISIONS.md (ADR-001).

## Circuit summary

V5 game board (7 lemon keys pulled up 220 Ω to the rail, player holds GND;
ten-LED progress bar on D2–D11; SENS± buttons; passive buzzer) **plus** the
V5.5 power-entry filter: 5 V in → P6KE6.8A TVS shunt → 1N5817 series Schottky
→ 470 µF ‖ 100 nF → 100 µH power choke → 470 µF ‖ 100 nF → the +5 V rail
(also AVcc = ADC reference — that is the whole point of the filter).

The Nano is **socketed**: two 1×15 2.54 mm female rows (U1/U2), mini-USB end
facing the WEST board edge (flash access; USB power stays behind the 1N5817
so it cannot back-feed the filter — `HARDWARE.md` powering rule 2).

## Components (26 + 18 R + 2 H = 45 footprints)

| Ref | Value | Footprint (KiCad 9 lib) | Source line |
|---|---|---|---|
| U1 | Nano socket row A (Nano pins 1–15: TX1,RX0,RST,GND,D2…D12) | `Connector_PinSocket_2.54mm:PinSocket_1x15_P2.54mm_Vertical` | v5 HARDWARE pin map |
| U2 | Nano socket row B (Nano pins 16–30: D13,3V3,AREF,A0…A7,5V,RST,GND,VIN) | idem | idem |
| J1 | 5V_IN screw terminal | `TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal` | v5.5 BOM "5 V input pigtail / barrel jack" → terminal (ADR-003) |
| J2 | LEMON_KEYS 1×8 header (GND + KEY7…KEY1) | `Connector_PinHeader_2.54mm:PinHeader_1x08_P2.54mm_Vertical` | keys A0–A6 + GND clip (ADR-004) |
| D1 | P6KE6.8A (TVS, 600 W) | `Diode_THT:D_DO-15_P5.08mm_Vertical_KathodeUp` | v5.5 HARDWARE filter table |
| D2 | 1N5817 (Schottky) | `Diode_THT:D_DO-41_SOD81_P5.08mm_Vertical_AnodeUp` | idem |
| C1 | 470u/16V (input reservoir) | `Capacitor_THT:CP_Radial_D8.0mm_P3.50mm` | idem |
| C2 | 100nF X7R (input ceramic) | `Capacitor_SMD:C_0805_2012Metric_Pad1.18x1.45mm_HandSolder` | idem + CONVENTIONS §4 |
| L1 | 100uH ≥1 A power choke (e.g. Fastron 07HCP-101K, 1.3 A) | `Inductor_THT:L_Radial_D8.7mm_P5.00mm_Fastron_07HCP` | idem ("drum or toroid, ≥1 A") |
| C3 | 470u/16V (output reservoir) | `Capacitor_THT:CP_Radial_D8.0mm_P3.50mm` | idem |
| C4 | 100nF X7R (output ceramic) | 0805 HandSolder | idem |
| R1–R7 | 220 (key pull-ups KEY1…KEY7 = A0…A6) | `Resistor_SMD:R_0805_2012Metric_Pad1.20x1.40mm_HandSolder` | v5 HARDWARE "220 Ω pull-up per key" |
| R8–R17 | 220 (LED series, LED1…LED10) | idem | v5 HARDWARE "one per LED" |
| R18 | 10k (SENS− external pull-up on A7) | idem | v5 HARDWARE "A7 has no internal pull-up" |
| D3–D12 | GREEN LED 1…10 | `LED_THT:LED_D3.0mm` | v5 HARDWARE "Green LEDs ×10" (3 mm: ADR-005) |
| BUZ1 | passive buzzer | `Buzzer_Beeper:Buzzer_12x9.5RM7.6` | v5 HARDWARE (D13) + CONVENTIONS §5 |
| SW1 | SENS + push button (D12, to GND, internal pull-up) | `Button_Switch_THT:SW_PUSH_6mm` | v5 HARDWARE pin map |
| SW2 | SENS − push button (A7, to GND, R18 pull-up) | idem | idem |
| H1, H2 | M2 mounting hole | `MountingHole:MountingHole_2.5mm_Pad_Via` | board spec (2 anchors) |

## Nano socket pin map (physical, USB end = WEST)

`U1` = SOUTH row, pin 1 at west; `U2` = NORTH row, pin 1 at east.
`U2.k` = Nano pin (15+k). Rows 15.24 mm apart, 2.54 mm pitch.

```
   x=104                                                    x=139.56
U2: VIN GND RST 5V A7 A6 A5 A4 A3 A2 A1 A0 AREF 3V3 D13   (y=107.38, pin15→pin1)
        [ mini-USB faces x=90 west edge ]
U1: TX1 RX0 RST GND D2 D3 D4 D5 D6 D7 D8 D9 D10 D11 D12   (y=122.62, pin1→pin15)
```

## Nets (KiCad net number → name → pads)

| # | Net | Pads |
|---|---|---|
| 1 | /+5V | U2.12 (5V), L1.2, C3.1(+), C4.1, R1.1…R7.1, R18.1 |
| 2 | /GND | U1.4, U2.14, J1.2, J2.1, D1.2(A), C1.2(−), C2.2, C3.2(−), C4.2, R8.1…R17.1, BUZ1.2, SW1.2(×2), SW2.2(×2), H1.1, H2.1 |
| 3 | /VIN | J1.1(+), D1.1(K), D2.2(A) |
| 4 | /VRAW | D2.1(K), C1.1(+), C2.1, L1.1 |
| 5–11 | /KEY1…/KEY7 | U2.4…U2.10 (A0…A6), R1.2…R7.2, J2.8…J2.2 (KEY1=J2.8 … KEY7=J2.2) |
| 12 | /SENS_MINUS | U2.11 (A7), R18.2, SW2.1(×2) |
| 13 | /SENS_PLUS | U1.15 (D12), SW1.1(×2) |
| 14 | /BUZZER | U2.1 (D13), BUZ1.1(+) |
| 15–24 | /LED1…/LED10 | U1.5…U1.14 (D2…D11) → D3.2…D12.2 (anodes) |
| 25–34 | /LED1_K…/LED10_K | D3.1…D12.1 (cathodes) → R8.2…R17.2 |

Unconnected (by design): U1.1 (TX1), U1.2 (RX0), U1.3 (RST), U2.2 (3V3),
U2.3 (AREF), U2.13 (RST), U2.15 (Nano VIN — the filtered rail feeds the 5V
pin directly, exactly like the breadboard rail; VIN would insert the Nano's
own regulator and drop the 4.7 V rail further).

Wirewright-contract cross-check (`build_v5_5`): net `vin` = {J1.vout,
DTVS.cathode, DS.anode} ✓ /VIN; `vraw` = {DS.cathode, CF1.a, CF2.a, LF1.a} ✓
/VRAW; `vfilt` = {LF1.b, CF3.a, CF4.a, rail 5V} ✓ /+5V; `pgnd` + `nanognd` +
key/button/LED grounds ✓ /GND; `kn0..kn6` (pin+fruit clip+pull-up low side)
✓ /KEY1…7; `a0..a9`/`c0..c9`/`g0..g9` ✓ /LEDn + /LEDn_K; `buzsig` ✓ /BUZZER;
`SUPsig` ✓ /SENS_PLUS; `sdnsig` (A7+button+R.b) ✓ /SENS_MINUS; `sdnpu`/`kp*`
(pull-up highs) ✓ /+5V. All 58 diagram nets accounted for.

## Current / width budget

Worst case board draw ≈ 200 mA (10 LEDs ≈ 150 mA + Nano ≈ 30 mA + margin —
v5 HARDWARE "All ten lit ≈ 150 mA"). Power path (VIN→VRAW→+5V, GND returns)
routed at 0.5 mm (≥ 0.4 spec); signals 0.25 mm. LED/key currents ≤ 15 mA.
