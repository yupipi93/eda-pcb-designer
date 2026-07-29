# CONVENTIONS.md — Reglas duras de diseño

> **Nota (repo standalone)**: §2, §4–§7 y §9–§10 son convenciones
> generales del toolkit. §1, §3 y §8 son las convenciones concretas del
> board MT1 (el worked example en `projects/mt1/`) — trátalas como
> ejemplo de cómo fijar las tuyas, no como reglas del toolkit.

> Reglas inmutables salvo decisión registrada en `DECISIONS.md`. Cualquier desviación que se vea en el proyecto sin ADR correspondiente es un **bug** a corregir.

---

## 1. Identificación del proyecto KiCad

| Item | Valor |
|---|---|
| Carpeta del proyecto | `../projects/mt1/kicad/` |
| Nombre interno | `mt1-pcb` (cohete MT1, primera PCB del programa MT) |
| Revisión actual | `v0.1` (cambia con cada release a fabricación) |
| Autor | MultitecUA |

> Nombrado de revisiones: `v<major>.<minor>` donde major aumenta con cambios de footprint físico (= necesita re-fabricar prototipo), minor con cambios sólo de firmware/cableado interno.

---

## 2. Reference designators

| Prefijo | Tipo de componente | Ejemplo |
|---|---|---|
| `U`  | Circuitos integrados (módulos, chips activos) | `U1`=XIAO, `U2`=LSM6DSO32 breakout |
| `J`  | Conectores | `J1`=JST batería, `J2`=microSD slot |
| `SW` | Interruptores y pulsadores | `SW1`=switch armado, `SW2`/`SW3`=botones |
| `D`  | Diodos, LEDs, TVS | `D1`/`D2`=LEDs, `D3`=TVS |
| `R`  | Resistencias | `R1`, `R2`… |
| `C`  | Capacitores | `C1`, `C2`… |
| `L`  | Inductores | `L1`… |
| `F`  | Fusibles (incluido PTC) | `F1`=PTC batería |
| `Y`  | Cristales / osciladores | (no usados en esta rev) |
| `BUZ`| Zumbadores / buzzers | `BUZ1`=buzzer activo de estado |
| `TP` | Test points | `TP1`=3V3, `TP2`=GND, `TP3`=BAT_P, `TP4`=BAT_SW, `TP5`=SDA, `TP6`=SCL, `TP7`=BUZ_PWM |
| `H`  | Mounting holes (agujeros mecánicos) | `H1`–`H4` |

> **Numeración**: secuencial dentro del prefijo, en el orden en que aparecen en el esquemático leyendo izquierda→derecha, arriba→abajo.

---

## 3. Net names (nombres de redes)

Nombres en MAYÚSCULAS, con `_` como separador. Sin caracteres especiales (KiCad acepta más, pero queremos diffs limpios).

### Power nets

| Net name | Descripción |
|---|---|
| `BAT_P` | Positivo de batería (antes del switch y la protección) |
| `BAT_SW` | Positivo después del switch (alimentación armada) |
| `+3V3` | Riel regulado de 3.3 V (salida del LDO interno del XIAO) |
| `GND` | Masa común |
| `+5V_USB` | 5 V desde el USB-C (sólo si se usa antes del XIAO; normalmente queda interno) |

### Signal nets

| Net name | Descripción | Pin XIAO | GPIO |
|---|---|---|---|
| `I2C_SDA` | Bus I²C SDA (IMU + BARO) | D4 | GPIO5 |
| `I2C_SCL` | Bus I²C SCL (IMU + BARO) | D5 | GPIO6 |
| `SDIO_CLK` | microSD clock | D8 | GPIO7 |
| `SDIO_D0` | microSD data 0 | D9 | GPIO8 |
| `SDIO_CMD` | microSD comando | D10 | GPIO9 |
| `BTN1` | Pulsador de usuario 1 | D0 | GPIO1 |
| `BTN2` | Pulsador de usuario 2 | D1 | GPIO2 |
| `LED1` | LED estado general (verde) | D2 | GPIO3 |
| `LED2` | LED logging activo (rojo) | D3 | GPIO4 |
| `BUZ_PWM` | Buzzer de estado (PWM capable) | D11 | GPIO38 |

> Cualquier net adicional sigue el patrón: nombre semántico antes que pin físico (`BTN_ARM` mejor que `GPIO1`).

---

## 4. Valores estándar de componentes pasivos

### 4.1 Restricción de tamaño SMD (hand-solder ergonomics)

**Todo nuevo pasivo SMD usa tamaño 0805 (2.0 × 1.25 mm) o mayor.**

Razón: el bringup de los prototipos MT1 se hace con soldadura manual sin
punta de precisión. 0603 (1.6 × 0.8 mm) y especialmente 0402 (1.0 × 0.5
mm) son demasiado pequeños para soldar fiable sin estación de aire
caliente / paste + reflow.

Aplicabilidad:
- Resistencias, capacitores, inductores, fusibles, diodos SMD: **0805
  mínimo**, 1206 acepta si la disipación lo pide.
- ICs con pitch QFN/SOIC ≥ 0.5 mm están OK (manejables con punta fina +
  flujo).
- Cuando se reincorporen los pasivos descartados (R1/R2 LED limiters,
  D1/D2 LEDs, caps decoupling), bumpear de 0603 (diseño original) a
  0805. El silk se reposiciona en ese momento.

### 4.2 Valores recomendados

| Aplicación | Valor | Footprint | Tolerancia |
|---|---|---|---|
| Pull-up I²C | 4.7 kΩ | **0805** | 1 % |
| Pull-down genérico | 10 kΩ | **0805** | 1 % |
| Limitación LED a 3V3 (≈5 mA) | 330 Ω | **0805** | 1 % |
| Divisor sensor VBAT (R3, R4) | 100 kΩ | **0805** HandSolder | 1 % |
| Filtro ADC en sensor VBAT (C8) | 100 nF X7R | **0805** HandSolder | 10 % |
| Decoupling cerca de IC | 100 nF X7R | **0805** | 10 % |
| Bulk decoupling 3V3 | 10 µF X7R | **0805** | 10 % |
| Bulk batería | 22 µF X7R | 0805 | 10 % |
| Debounce pulsador | 100 nF X7R | **0805** | 10 % |
| PTC batería | 500 mA hold | 1812 | — |
| TVS batería | PESD3V3L1BA | SOD-323 | — |

> Si un cálculo concreto exige otro valor, ese cálculo se documenta en
> `DECISIONS.md`. Las celdas en negrita son cambios desde 0603 → 0805
> tras la restricción §4.1.

---

## 5. Footprints por defecto

| Categoría | Footprint preferido |
|---|---|
| Resistencias / capacitores genéricos | **0805 HandSolder** (`Resistor_SMD:R_0805_2012Metric_Pad1.20x1.40mm_HandSolder`, `Capacitor_SMD:C_0805_2012Metric_Pad1.18x1.45mm_HandSolder`) — pads extendidos para soldadura manual |
| Decoupling 100 nF cerca de IC | **0805** (NO 0402 — ver §4.1) |
| LEDs de estado | **0805** (`LED_SMD:LED_0805_2012Metric`) |
| Pulsadores | SMD 4 pines, **6 × 6 mm** (`Button_Switch_SMD:SW_SPST_TL3342`) o equivalente |
| Switch armado | SPDT slide, 2.54 mm pitch (`Button_Switch_THT:SW_Slide_1P2T_CK_OS102011MS2QN1`) |
| Conector JST batería | `JST_PH_S2B-PH-K_1x02_P2.00mm_Horizontal` |
| Headers para XIAO | Pin-headers hembra 2.54 mm de 2×11 (lado superior del XIAO) |
| Headers para breakouts (LSM6DSO32, BMP585, microSD) | Pin-headers hembra 2.54 mm 1×N según breakout |
| PTC | 1812 (`Resistor_SMD:R_1812_4532Metric`) |
| TVS | SOD-323 (`Diode_SMD:D_SOD-323`) |
| Buzzer activo SMD | `Buzzer_SMD:Buzzer_12x9.5RM7.6` o equivalente (9-12 mm Ø) |
| Test points (pad SMD 1 mm) | `TestPoint:TestPoint_Pad_1.0x1.0mm` |
| Mounting holes | `MountingHole:MountingHole_2.5mm_Pad_Via` (M2 con holgura) |

---

## 6. Librerías a usar (orden de preferencia)

1. **Librerías nativas de KiCad** (`Device`, `Connector`, `Switch`, `LED`, `Diode`, `Resistor_SMD`, `Capacitor_SMD`, …).
2. **Espressif KiCad Library** (instalada vía PCM): `Espressif` — para el XIAO ESP32S3 Plus.
3. **Adafruit KiCad Library** (vía GitHub): para los breakouts LSM6DSO32, BMP585, microSD.
4. **SnapMagic / SnapEDA**: como último recurso para piezas raras.
5. **Símbolos custom del proyecto**: en `projects/<board>/libraries/` — usar SÓLO si las anteriores no lo tienen y registrar el motivo en el `DECISIONS.md` del board.

> **NO** copiar símbolos manualmente desde otros proyectos sin revisar pinout. Verificar siempre con el datasheet antes de incorporar.

---

## 7. Reglas de PCB (DRC)

Cargar como Design Rules en `mt1-pcb.kicad_pro`. Estos valores son **mínimos**; usar más cuando se pueda.

| Regla | Valor | Razón |
|---|---|---|
| Ancho mínimo de traza | **0.20 mm** (8 mil) | Compatible con JLCPCB / PCBWay sin upcharge |
| Clearance mínimo | **0.20 mm** (8 mil) | Idem |
| Ancho traza de potencia (3V3, GND, BAT) | **0.50 mm** (20 mil) | Capacidad de corriente |
| Vía estándar — perforación | 0.30 mm | Idem |
| Vía estándar — pad | 0.60 mm | |
| Vía de potencia — perforación | 0.40 mm | |
| Vía de potencia — pad | 0.80 mm | |
| Clearance traza ↔ borde de PCB | **0.30 mm** | Margen del fabricante |
| Anillo mínimo de pad | 0.15 mm | |

### Stack-up de PCB

- **2 capas** FR4 1.6 mm, 1 oz de cobre por cara, acabado HASL libre de Pb (cambiar a ENIG si se llega a soldadura SMT serie).

```
TOP    (componentes + señales)
       FR4 1.6 mm
BOTTOM (plano GND continuo + señales que no quepan en top)
```

### Autorouter

Desde v0.0.16 las trazas se generan automáticamente con
[`projects/mt1/tools/run_autorouter.py`](../projects/mt1/tools/run_autorouter.py) (orquestador
MT1 que delega en [`pcb_designer.autorouter`](../src/pcb_designer/autorouter.py)):
pipeline `pcbnew → freerouting v2.1.0 → pcbnew + ZONE_FILLER` headless,
~3-4 s por iteración. El JAR vendored vive en `vendor/freerouting.jar`.
El plano GND vive en una **`(zone)` B.Cu** definida por
`projects/mt1/tools/place_components.py` y rellenada por `ZONE_FILLER` con thermal
reliefs. Ver ADR-013 (repo upstream `multi-rocket-avionica`, `pcb/projects/mt1/docs/DECISIONS.md`) para la
justificación y el flujo (MT1-specific).

Si necesitas overrides locales (rutado manual de un net crítico),
hazlo en KiCad GUI tras correr el autorouter — el script preserva los
segmentos con UUIDs distintos a los autogenerados.

---

## 8. Layout — reglas de colocación

| Regla | Justificación |
|---|---|
| **IMU LSM6DSO32 en el eje longitudinal del cohete** | Minimiza offset del IMU al centro de masas → cálculos de actitud más limpios. |
| **BMP585 cerca del orificio de venteo** | Necesita acceso al aire exterior; lejos de fuentes de calor (XIAO, LDO). |
| **USB-C y microSD en el mismo borde** | Una sola ranura de servicio en el cuerpo del cohete. |
| **Switch de armado en borde lateral accesible** | Operación pre-vuelo. |
| **LEDs visibles a través de la ventana / cuerpo translúcido** | Verificación de armado. |
| **Cada LED pegado a SU resistencia limitadora** (`D1`↔`R1`, `D2`↔`R2`, ≤ 3 mm de separación, mismo eje) | Comprensión visual del circuito (qué resistencia limita qué LED se lee de un vistazo), depuración rápida con sonda, y la traza LED→R queda corta evitando que la corriente de conmutación del GPIO acople ruido. Aplicar a cualquier LED de estado que se añada en el futuro. |
| **Conector JST orientado hacia el compartimento de la batería** | El cable sale recto, sin doblar. |
| **Mounting holes en la zona de anclaje** (20 × 30 mm) | Aislar la fijación de las trazas. |
| **Cero componentes en la zona de anclaje** | La zona puede ser mecanizada/ranurada. |
| **Plano de masa continuo en BOTTOM** | Integridad de señal, antena GPS futura. |
| **Trazas SDIO emparejadas y < 30 mm** | Integridad de señal a 25 MHz. |

---

## 9. Unidades y formato

- Dimensiones: **mm** en todos los documentos y archivos KiCad.
- Tensiones: V (con decimales para sub-1 V).
- Corrientes: mA por defecto, A para > 1 A.
- Tiempos: ms / µs.
- Temperaturas: °C.
- Strings en KiCad: ASCII puro; **sin tildes ni eñes** en `Reference`, `Value` ni footprints (evita problemas de codificación con `kicad-cli`). Sí pueden ir en `Description` y comentarios libres.

---

## 10. Output de fabricación esperado

Cuando se genere el paquete para enviar al fabricante, debe incluir:

```
fab/v0.x/
├── gerbers/                 (F.Cu, B.Cu, F.Mask, B.Mask, F.SilkS, B.SilkS, Edge.Cuts)
├── drill/                   (NPTH + PTH)
├── bom.csv                  (BOM Adafruit-style: Reference, Value, Footprint, LCSC, Manufacturer)
├── positions.csv            (pick-and-place, mm)
├── 3d-render.png            (vista superior e inferior)
└── README.md                (instrucciones para el fabricante: stack-up, acabado, color, …)
```

> Antes de exportar: revisión de ERC + DRC limpios, BOM verificado con stock real en JLCPCB / Mouser.
