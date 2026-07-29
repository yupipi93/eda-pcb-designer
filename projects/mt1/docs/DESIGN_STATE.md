# DESIGN_STATE.md — Estado actual del diseño

> **Snapshot vivo** del proyecto KiCad. Se actualiza en **cada iteración** que toque el esquemático, layout, BOM o reglas. Pensado para que cualquier modelo lo lea y sepa exactamente dónde estamos.

| Campo | Valor |
|---|---|
| **Revisión actual** | `v0.1.1` (**pipeline verification re-run — sin cambios funcionales sobre v0.1.0**) |
| **Fase** | `Pipeline build → route → render verificada end-to-end post-refactor. Misma geometría y placements que v0.1.0; routing regenerado por freerouting. Lista para fab.` |
| **Versión KiCad** | **9.0.7-1** (system) / **9.0.9** (pcbnew Python module) |
| **Estructura** | **Plana (single sheet)** — ADR-011 supersede ADR-006 (jerárquico) |
| **Última actualización** | 2026-05-23 (v0.1.1 — pipeline verification + fix imports render_overlay/cli.py) |
| **Última iteración (commit)** | `pendiente` (v0.1.1 pipeline verify) — previa v0.1.0 schematic sync → `5441186` (overlay tweak) → `3a5e74b` (DIM renders) |
| **Último ERC** | 2026-05-22 — **✅ 0 errores, 0 warnings** (`erc-v0.1.0.txt`, esquemático no tocado en v0.1.1) |
| **Último DRC** | 2026-05-23 — **41 warnings cosméticos + 0 errors + 0 unconnected** ✅ (`drc-v0.1.1-pipeline-verify.txt`; +1 silk_overlap + 1 track_dangling vs v0.1.0 por re-routing freerouting no determinista) |
| **Bloqueado por** | Nada. Pipeline canónico (place → autoroute → place) verificado. Próximo paso: generar gerbers + BOM para fab si se decide subir release. |

---

## 1. Fases del proyecto

Marcar con `[x]` cada fase completada. La fase activa lleva `[~]`.

- [x] **F0 — Setup inicial**: proyecto KiCad creado, AGENT/CONVENTIONS/STATE documentados, Q-001..Q-004 resueltas, buzzer añadido al diseño.
- [x] **F0.5 — Skeleton validado**: `.kicad_pro` configurado, `.kicad_pcb` con contorno 90×30 mm + 4 mounting holes + silkscreen, 5 sub-hojas jerárquicas creadas, ERC 0 violaciones, DRC 0 errores.
- [x] **F1 — Esquemático: bloque de alimentación** (J1 JST, F1 PTC, SW1 SPDT, D3 TVS, C1 22µF, TP3, TP4 + GND power flag). _Construido programáticamente._
- [x] **F2 — Esquemático: MCU** (U1 socket XIAO 2×11, C2 10µF, C4 100nF, TP1, TP2, 3× PWR_FLAG). _Pinout completo mapeado (D0..D17+BAT+3V3+GND), 13 hierarchical labels._
- [x] **F3 — Esquemático: sensores** (U2 socket LSM6DSO32, U3 socket BMP585, C3 10µF, C5/C6 100nF, TP5/TP6). _4 hier labels._
- [x] **F4 — Esquemático: almacenamiento** (U4 socket microSD, C7 100nF). _5 hier labels._
- [x] **F5 — Esquemático: interfaz** (SW2/SW3 6×6mm, R1/R2 330Ω, D1 verde, D2 rojo, BUZ1 buzzer 3V, TP7).
- [x] **F6 — ERC limpio ✅** (0 errores, 0 warnings con v0.0.3 flat schematic; mantenido en v0.1.0).
- [x] **F7 — Tools → Update PCB from Schematic** (completado en v0.0.10+; PCB en sync con schematic en v0.1.0).
- [x] **F8-F11 — Layout + rutado** (placement scripted vía `projects/mt1/tools/place_components.py` + autorouter freerouting v2.1.0 — ver `PLACEMENT_GUIDE.md` y ADR-013).
- [ ] **F12 — Generación de gerbers + BOM + pick-and-place** (vía `pcb-designer fab --config examples/mt1.yaml --version vX.Y.Z` → `projects/mt1/releases/vX.Y.Z/`).
- [ ] **F13 — Pedido a JLCPCB / PCBWay**.

---

## 2. Componentes (estado de cada uno — v0.1.0)

> **v0.1.0**: el `.kicad_pcb` contiene **19 footprints** (los 5 sockets
> de módulos + 6 mounting holes + el subsistema de batería + sensor
> VBAT). El `.kicad_sch` está sincronizado a partir de v0.1.0 vía
> `build_schematic.py` — los mismos 19 componentes salvo los mounting
> holes que son mecánicos (no aparecen en el schematic).
>
> Estado: `verified` = en `.kicad_sch` ∧ en `.kicad_pcb` con ERC + DRC
> limpios. `deferred` = fuera de scope de v0.1.0, ver
> `REMOVED_COMPONENTS.md`.

### 2.1 Componentes activos en v0.1.0

| Ref | Componente | Footprint | Librería | Estado | Notas |
|-----|------------|-----------|----------|--------|-------|
| `U1` | XIAO ESP32S3 socket izquierdo (D0..D6) | `PinSocket_1x07_P2.54mm_Vertical` | Connector_PinSocket_2.54mm | `verified` | Pin 1 = D0 = VBAT_SENSE |
| `U5` | XIAO ESP32S3 socket derecho (5V, GND, 3V3, D10..D7) | `PinSocket_1x07_P2.54mm_Vertical` | Connector_PinSocket_2.54mm | `verified` | Pin 1 = 5V no conectado |
| `U2` | LSM6DSO32 IMU breakout (Adafruit 4692) | `PinSocket_1x09_P2.54mm_Vertical` | Connector_PinSocket_2.54mm | `verified` | **B.Cu** — flota por debajo del PCB |
| `U3` | BMP585 barómetro breakout (Adafruit 6132) | `PinSocket_1x08_P2.54mm_Vertical` | Connector_PinSocket_2.54mm | `verified` | **B.Cu** — movido en v0.1.0 para liberar la franja batería |
| `U4` | microSD breakout (Adafruit) | `PinSocket_1x09_P2.54mm_Vertical` | Connector_PinSocket_2.54mm | `verified` | F.Cu, slot al borde y=130 |
| `J4` | Header proto 1×8 vertical (XIAO pins libres) | `PinHeader_1x08_P2.54mm_Vertical` | Connector_PinHeader_2.54mm | `verified` | J4.1 = VBAT_SENSE (test point), J4.2-4 = D1-D3 libres, J4.5-6 = DBG_TX/RX, J4.7 = 3V3, J4.8 = GND |
| **`J1`** | **JST-PH 2 pines (entrada LiPo)** | `JST_PH_S2B-PH-K_1x02_P2.00mm_Horizontal` | Connector_JST | **`verified`** | v0.1.0 — Pin 1 = BAT_P, Pin 2 = GND |
| **`SW1`** | **SPDT slide (battery disconnect)** | `SW_Slide_SPDT_Straight_CK_OS102011MS2Q` | Button_Switch_THT | **`verified`** | v0.1.0 — Pad 1 = común BAT_P, Pad 2 = ON (BAT_SW), Pad 3 = NC |
| **`J2`** | **Header 1×2 paralelo a SW1 (ext switch)** | `PinHeader_1x02_P2.54mm_Vertical` | Connector_PinHeader_2.54mm | **`verified`** | v0.1.0 — Pin 1 = BAT_P, Pin 2 = BAT_SW |
| **`J5`** | **Header 1×2 a pads BAT del XIAO** | `PinHeader_1x02_P2.54mm_Vertical` | Connector_PinHeader_2.54mm | **`verified`** | v0.1.0 — Pin 1 = BAT_SW, Pin 2 = GND. Cables manuales |
| **`R3`** | **100 kΩ 0805 1% (top divisor VBAT)** | `R_0805_2012Metric_Pad1.20x1.40mm_HandSolder` | Resistor_SMD | **`verified`** | v0.1.0 — entre BAT_SW y VBAT_SENSE |
| **`R4`** | **100 kΩ 0805 1% (bot divisor VBAT)** | idem | Resistor_SMD | **`verified`** | v0.1.0 — entre VBAT_SENSE y GND |
| **`C8`** | **100 nF 0805 X7R 50V (filtro ADC)** | `C_0805_2012Metric_Pad1.18x1.45mm_HandSolder` | Capacitor_SMD | **`verified`** | v0.1.0 — VBAT_SENSE a GND |
| `H1`-`H4` | Mounting holes M2 (anchor derecho 2×2) | `MountingHole_2.5mm_Pad_Via` | MountingHole | `placed` | (175,105)(185,105)(175,125)(185,125). Solo PCB, no schematic |
| `H5`-`H6` | Mounting holes M2 (anchor izquierdo 1×2) | `MountingHole_2.5mm_Pad_Via` | MountingHole | `placed` | (95,107)(95,123). Solo PCB, no schematic |

**Total v0.1.0**: 13 componentes electrónicos en BOM + 6 mounting holes.

### 2.2 Componentes diferidos (no presentes en v0.1.0)

Ver `REMOVED_COMPONENTS.md` para justificación detallada. Resumen:

| Ref | Componente | Estado | Si se reincorpora |
|---|---|---|---|
| `SW2`, `SW3` | Pulsadores BTN1/BTN2 6×6 SMD | `deferred` | BTN1 ya no es viable (D0 ocupado por VBAT_SENSE); BTN2 puede ir en D1 |
| `D1`, `D2` + `R1`, `R2` | LEDs verde/rojo + limitadores 330 Ω | `deferred` | Bumpear footprint de 0603 a 0805 (CONVENTIONS §4.1) |
| `D3` | TVS PESD3V3L1BA | `deferred` | Solo si una iteración demuestra problemas ESD reales |
| `F1` | PTC 500 mA hold | `deferred` | LiPo trae protección integrada — solo si flota un fail mode crítico |
| `BUZ1` | Buzzer activo 3V | `deferred` | El D11/GPIO38 no existe en el XIAO básico → reasignar a otro pin libre |
| `C1` | 22 µF bulk batería | `deferred` | LiPo + LDO XIAO son estables; añadir si el bringup muestra dips |
| `C2`-`C7` | Decoupling 0603/0402 | `deferred` | Breakouts ya traen decoupling local; bumpear a 0805 si se reincorpora |
| `TP1`-`TP7` | Test points 1 mm | `deferred` | J4 y J5 ya exponen las nets clave |

---

## 3. Nets (v0.1.0)

| Net           | Conecta a                                                            | Estado | Capa de routing |
|---------------|----------------------------------------------------------------------|--------|------------------|
| `BAT_P`       | J1.1 — SW1.1 — J2.1                                                 | `verified` | B.Cu (oculto desde F.Cu) |
| `BAT_SW`      | SW1.2 — J2.2 — R3.1 — J5.1                                          | `verified` | F.Cu + 1 link B.Cu |
| `VBAT_SENSE`  | R3.2 — R4.1 — C8.1 — J4.1 (test point) — **U1.1** (XIAO D0 ADC1_CH0) | `verified` | F.Cu |
| `GND`         | J1.2 — J5.2 — R4.2 — C8.2 — U5.2 — U2.3 — U3.3 — U4.2 — J4.8        | `verified` | Plano B.Cu continuo (zone fill 2398 vértices) |
| `+3V3`        | U5.3 (XIAO out) — U2.1 — U3.1 — U4.1 — J4.7                         | `verified` | F.Cu / B.Cu mixto |
| `I2C_SDA`     | U1.5 (XIAO D4) — U2.5 — U3.5                                        | `verified` | F.Cu + via para llegar a U3/U2 en B.Cu |
| `I2C_SCL`     | U1.6 (XIAO D5) — U2.4 — U3.4                                        | `verified` | Idem |
| `SDIO_CLK`    | U5.6 (XIAO D8) — U4.3                                                | `verified` | F.Cu |
| `SDIO_D0`     | U5.5 (XIAO D9) — U4.4                                                | `verified` | F.Cu |
| `SDIO_CMD`    | U5.4 (XIAO D10) — U4.5                                               | `verified` | F.Cu |
| `BTN2`        | U1.2 (XIAO D1) — J4.2                                                | `verified` | (No driver físico — solo expone el pin en proto header) |
| `LED1`        | U1.3 (XIAO D2) — J4.3                                                | `verified` | Idem |
| `LED2`        | U1.4 (XIAO D3) — J4.4                                                | `verified` | Idem |
| `DBG_TX`      | U1.7 (XIAO D6) — J4.5                                                | `verified` | F.Cu |
| `DBG_RX`      | U5.7 (XIAO D7) — J4.6                                                | `verified` | F.Cu |

> Total nets activas en v0.1.0: **15** (3 nuevas vs v0.0.17: `BAT_P`,
> `BAT_SW`, rename `BTN1`→`VBAT_SENSE`).

---

## 4. Mecánica

| Parámetro | Valor | Estado |
|---|---|---|
| Contorno PCB (Edge.Cuts) | **100 × 30 mm** rectangular (v0.0.10 dual anchor) | `applied` |
| Zona electrónica | 70 × 30 mm (x=100..170, y=100..130) | `applied` |
| Zona de anclaje izquierdo (sin componentes) | 10 × 30 mm (x=90..100, y=100..130) | `applied` |
| Zona de anclaje derecho (vacía en v0.0.13 — power section stripped) | 20 × 30 mm (x=170..190, y=100..130) | `applied` |
| Mounting holes | 6 × Ø 2.5 mm (M2 holgura) — H1..H4 en anchor dch (2×2) + H5..H6 en anchor izq (1×2) | `applied` |
| Conectores accesibles v0.0.13 | USB-C XIAO (`rot=180`) + slot microSD (`rot=270`) ambos al borde y=130 — JST removido | `applied` |
| Grosor | 1.6 mm FR4 | `pending` |
| Capas | 2 | `pending` |

---

## 5. Validación

| Check | Última vez | Resultado | Reporte |
|---|---|---|---|
| ERC | 2026-05-19 13:36 | ✅ **0 violaciones** (esquemático intacto) | `../validation/erc-skeleton.txt` |
| DRC v0.1.0 | 2026-05-22 | ✅ **39 warnings cosméticos + 0 errors + 0 unconnected** | `../validation/drc-v0.1.0-battery-power.txt` |
| `verify_layout()` v0.1.0 | 2026-05-22 | ✅ 19/19 dentro del PCB, anchor strips limpias, sin cross-layer TH conflicts | (stdout de `place_components.py`) |
| Render v0.1.0 3D + DIM | 2026-05-22 | ✅ módulos + tracks + plano GND continuo + silk dinámico "MT1 v0.1.0" | `../renders/v0.1.0-battery-power-{top,bottom,dim-front,dim-back}.png` |
| Overlay realista v0.1.0 | 2026-05-22 | ✅ 5 módulos top + 2 módulos bottom (BMP585 en B.Cu junto al LSM6) | `../overlays/v0.1.0-battery-power-realistic-{top,bottom}.png` |
| BOM coherente con `../../../../docs/pcb-design.md §6` | _pendiente_ | — | — |
| Pesos coherentes con `../../../../docs/ARCHITECTURE.md §6` | 2026-05-19 | ✅ (~38 g) | — |
| Footprints presentes en librería | _verificar al ejecutar receta_ | — | — |
| Pinout coherente con `../../../../docs/ARCHITECTURE.md §3` | 2026-05-19 | ✅ | — |

---

## 6. Archivos generados (regenerables)

| Archivo | Origen | Cuándo regenerar |
|---|---|---|
| `../validation/erc-*.txt` | `kicad-cli sch erc` | Cada iteración del esquemático |
| `../validation/drc-*.txt` | `kicad-cli pcb drc` | Cada iteración del PCB |
| `../validation/render-*.png` | `kicad-cli pcb render` | Para revisión visual |
| `../releases/v0.x/gerbers/` | `kicad-cli pcb export gerbers` | Antes de enviar a fabricación |
| `../releases/v0.x/bom.csv` | `kicad-cli sch export bom` | Idem |
| `../releases/v0.x/positions.csv` | `kicad-cli pcb export pos` | Idem |

> Todos los archivos en `validation/` y `fab/` están en `.gitignore` por defecto (excepto el README de cada `fab/v0.x/` si quieres versionar la release).

---

## Plantilla para actualizar este documento

Cuando hagas una iteración, copia/pega y rellena:

```markdown
| Revisión actual | `vX.Y` |
| Fase | `texto corto` |
| Última actualización | YYYY-MM-DD |
| Última iteración (commit) | <hash corto> — <subject> |
| Último ERC | YYYY-MM-DD HH:MM — <pass/fail, N violaciones> |
| Último DRC | YYYY-MM-DD HH:MM — <pass/fail, N violaciones> |
| Bloqueado por | <referencia a QUESTIONS.md o "nada"> |
```

Y actualiza la tabla de componentes / nets / fases según corresponda.
