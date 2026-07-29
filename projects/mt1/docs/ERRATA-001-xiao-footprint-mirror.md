# ERRATA-001 — Footprint del XIAO ESP32S3 ESPEJADO en MT1 v0.1.x

- **Severidad**: 🔴 CRÍTICA (la placa no funciona con el XIAO montado por la cara top tal como se diseñó)
- **Versiones afectadas**: v0.1.0, v0.1.1 (y todas las anteriores que compartan el placement del XIAO)
- **Fecha de descubrimiento**: 2026-06-13
- **Descubierto por**: Sergio (inspección física) + verificación geométrica sobre `mt1-pcb.kicad_pcb`
- **Estado**: ✅ **RESUELTO en v0.1.2** (2026-06-15) — des-espejado + sensores volteados de verdad + BMP585 SDA/SDO corregido; verificado por el gate anti-espejo (`pcb_designer.verify`), DRC y ERC. Ver el release v0.1.2 (`releases/v0.1.2/`, en el repo upstream), [POST-MORTEM-001](POST-MORTEM-001-mirror-rootcause.md) y BLK-007 (`docs/BLOCKERS.md`, en el repo upstream). Histórico: confirmado 2026-06-13 · workaround ADR-015 (XIAO en bottom) ya **no necesario** en v0.1.2.

---

## 1. Síntoma

Con la PCB ensamblada y el XIAO montado en la cara **top** (como manda el diseño), alimentando por USB:

- El XIAO **arranca** bien (boot, PSRAM, USB-CDC, firmware corriendo) — porque se alimenta por su **propio USB-C**, no por los pads de la PCB.
- **Ningún sensor I²C se detecta** (IMU `0x6A` y baro `0x46/0x47` ausentes), ni siquiera con un solo módulo puesto.
- Al insertar el **microSD**, el firmware detecta **`SDA<->SCL BRIDGED`** (las dos líneas I²C arrastrándose mutuamente) y el escaneo I²C se cuelga.
- La lectura de **VBAT** da valores imposibles (~6 V) → nodo flotante.

## 2. Causa raíz — footprint espejado

El footprint del XIAO (dos zócalos `PinSocket_1x07`, **U1** y **U5**) está colocado **en imagen especular**: está en la capa **F.Cu (top)** y el mapeo pin→net es correcto, **pero la disposición física de las dos filas es la de un módulo montado por la cara BOTTOM**.

Mapa extraído de `mt1-pcb.kicad_pcb` (posiciones globales, ambos zócalos `rot=180`):

```
U1 (x=150, columna IZQUIERDA)        U5 (x=165.24, columna DERECHA)
 pad1  D0  /VBAT_SENSE   y=124.00      pad1  5V   (NC)          y=124.00
 pad2  D1  /BTN2                       pad2  GND
 pad3  D2  /LED1                       pad3  +3V3
 pad4  D3  /LED2                       pad4  D10  /SDIO_CMD
 pad5  D4  /I2C_SDA                    pad5  D9   /SDIO_D0
 pad6  D5  /I2C_SCL                    pad6  D8   /SDIO_CLK
 pad7  D6  /DBG_TX       y=108.76      pad7  D7   /DBG_RX       y=108.76
```

En un XIAO ESP32S3 **real visto por arriba** (USB hacia el borde de servicio), la columna **D0–D6** y la columna **5V/GND/3V3/D10/D9/D8/D7** caen en lados **opuestos** a como están en la PCB. La placa tiene las dos filas en los **lados intercambiados** → es la imagen especular → equivale a un footprint dibujado para montaje por la cara **bottom**.

**Prueba geométrica (independiente de hacia dónde apunte el USB):** la quiralidad de los vectores `D0→5V` y `D0→D6` sale **opuesta** a la del XIAO físico. Concretamente, con las coordenadas de arriba el producto cruzado `(D0−5V) × (D6−D0)` da signo **positivo**, mientras que el del XIAO real da **negativo**. Signos opuestos ⇒ **espejo**, no una simple rotación.

## 3. Por qué explica TODOS los síntomas

Con el footprint espejado, al enchufar el XIAO real (pinout correcto) **todas las conexiones quedan cruzadas**; en particular **se intercambian el bus I²C y el SDIO**:

| Lo que hace el firmware | A dónde llega físicamente | Resultado observado |
|---|---|---|
| Maneja I²C en D4/D5 (GPIO5/6) | a las pistas del **microSD** | los sensores nunca ven SDA/SCL → **IMU/baro no detectados** |
| Maneja SDIO en D8/D9/D10 | a las pistas de los **sensores** | el microSD no responde por sus pines reales |
| Inserta el microSD | carga los pines I²C cruzados | el firmware lo ve como **"puente" SDA↔SCL** |
| Lee VBAT en D0 (GPIO1) | a una pista equivocada | lectura **flotante/absurda (~6 V)** |
| Alimenta por USB-C propio | (no usa los pads de la PCB) | el XIAO **arranca igual** aunque nada conecte |

## 4. Qué está BIEN (descartado como causa)

- **Firmware**: ✅ correcto. En protoboard con cableado por función (D4→SDA, D5→SCL, D8/9/10→SDIO) lee IMU + baro y monta la microSD (write/read OK). Build `xiao-esp32s3-plus` en la rama `feat/firmware-xiao-s3-pcb-bringup`.
- **Módulos** (LSM6DSO32, BMP585, lector microSD): ✅ los tres sanos y verificados en protoboard.
- **Diseño lógico / netlist / esquemático**: ✅ correcto. El pin→net del XIAO coincide con el pinout real (D4=SDA, D5=SCL, D8/9/10=SDIO, D0=VBAT_SENSE). El error es **geométrico** (placement de los footprints), no eléctrico-lógico.
- **DRC**: sin cortos ni clearances (solo warnings de silk + 1 `track_dangling` en `/I2C_SDA`, ver §7).
- **Ensamblaje/soldadura**: ✅ revisado por el usuario, correcto.

## 5. Evidencia experimental (bisección)

| Configuración | Puente SDA↔SCL | Sensores |
|---|---|---|
| XIAO solo, fuera de la PCB | No | — (XIAO sano) |
| XIAO en PCB, sin módulos | No | — |
| XIAO en PCB + solo baro | No | baro NO detectado |
| XIAO en PCB + solo IMU | No | IMU NO detectado |
| XIAO en PCB + solo microSD | **Sí** | — |
| **Protoboard** (XIAO + 3 módulos, cableado por función) | No | **IMU + baro + microSD TODO OK** |

La última fila es el control limpio: mismo firmware y mismos módulos, **fuera de la PCB → todo funciona**. El fallo es exclusivo del cobre de la PCB.

## 6. Workaround aplicado en v0.1.x (ver ADR-015)

Montar el **XIAO en la cara BOTTOM** de la PCB. Al estar los zócalos en through-hole, presentar el módulo desde la cara opuesta lo **espeja**, lo que **cancela** el espejo del footprint y restaura el mapeo correcto de pines.

**Verificación obligatoria antes de confiar en él:**
1. Continuidad: el pad **3V3** del XIAO debe llegar a la net `+3V3`, **GND** a `GND`, y D4/D5 a `/I2C_SDA` `/I2C_SCL`.
2. Re-ejecutar el bring-up del firmware: el I²C debe encontrar IMU `0x6A` + baro `0x46/0x47` y la microSD debe montar. Si aparece, el workaround funcionó.

**Caveats** (documentados en ADR-015): el USB-C y, según montaje, el slot microSD quedan orientados hacia la cara opuesta a la ranura de servicio; hay que verificar **clearance mecánico** con IMU (U2) y baro (U3), que ya van en la cara bottom; probablemente requiera **re-soldar los zócalos** (o el propio XIAO) en la cara bottom.

## 7. Fix correcto para v0.1.2 (ver BLK-007)

Des-espejar el footprint del XIAO en el placement: intercambiar las dos filas de zócalo (que la columna **D0–D6** caiga en el lado correcto para un módulo montado por **top**, dado el USB hacia la ranura de servicio), re-rutar y regenerar. Es casi seguro un bug en la colocación programática (`projects/mt1/tools/place_components.py` / `PLACEMENTS` / `pcb_designer.placement` con `flip_to_back`/`place_and_flip`): el XIAO va en top y **no** debería llevar espejo/flip, o las dos filas tienen la `x` intercambiada.

Aprovechar la v0.1.2 para resolver también:
- **`track_dangling` en `/I2C_SDA`** en `(120.99, 112.31)` — stub de 2.5 mm que apunta hacia el footprint del microSD (U4). Limpiarlo con un barrido extra de micro-stubs en `remove_tiny_segments`.
- **SDO del BMP585 flotante** → la dirección sale aleatoria entre `0x46`/`0x47`. Fijar SDO a un nivel (GND→0x46, 3V3→0x47) para dirección determinista.

## 8. Verificación del fix (cualquier revisión futura)

Tras des-espejar, **antes de fabricar**, comprobar la quiralidad del footprint del XIAO contra el pinout físico (vectores `D0→5V` y `D0→D6`), y tras montar, repetir la verificación de continuidad + bring-up del §6.

## 9. ACTUALIZACIÓN 2026-06-13 — SEGUNDO espejo CONFIRMADO: breakouts de sensores (B.Cu) montan al revés

Tras el workaround del XIAO (montado en bottom → microSD OK, bus limpio), los sensores I²C seguían sin funcionar: el **baro alimentado (LED ON) pero sin ACK**, el **IMU sin alimentación (LED OFF)**. Un análisis forense (9 agentes) verificó que el **cobre/netlist de los sensores es correcto** (pad→net consistente, las pistas I²C aterrizan exactamente en los pads de U2/U3, +3V3 llega a pad1). PERO el usuario, por **inspección física**, confirmó que el **BMP585 se enchufa ESPEJADO/al revés** en su socket.

**Causa raíz = el MISMO bug que el del XIAO.** `src/pcb_designer/placement.py::flip_to_back` solo hace string-replace de capas (F.*→B.*) y **no refleja coordenadas/orientación** al pasar a B.Cu. Consecuencias por tipo de footprint:
- XIAO (2 columnas, F.Cu): el bug se tradujo en columnas intercambiadas (§2).
- **Sensores U2/U3 (1 fila, B.Cu): el breakout de fila única, al montarse por la cara bottom, queda con su pin-1 / orientación ESPEJADOS respecto a la serigrafía y a la posición esperada.** El pad→net es correcto, pero el módulo físico entra reversed → SDA/SCL no aterrizan en el pin correcto del chip → alimentado pero sin ACK. (El análisis "solo-cobre" no lo detecta; se ve montando el módulo físicamente.)

**Workaround placas actuales — CONFIRMADO 2026-06-13:** montar cada breakout de sensor en la orientación **ESPEJADA** (al revés respecto a lo que indica la serigrafía de pin-1). Verificado empíricamente: el **LSM6DSO32 (IMU) montado "en espejo" pasa a detectarse en `0x6A` y entrega datos** (`a=(0.99,-5.53,19.25) m/s²`, giro vivo). La orientación "según serigrafía" NO funciona (alimentado pero sin ACK, o sin alimentación); la orientación espejada cancela el espejo del footprint y alinea Vin/GND/SDA/SCL correctamente. Aplicar lo mismo al BMP585. Verificar con el firmware de bring-up (IMU `0x6A`, baro `0x46/0x47`).

**Fix v0.1.2:** corregir `flip_to_back` para que refleje correctamente coordenadas y orientación (y la serigrafía/marcador de pin-1 quede bien en B.Silk para montaje por bottom). Verificar la quiralidad/orientación de TODOS los footprints en B.Cu (U2, U3) contra el pinout físico del breakout montado por la cara correspondiente, no solo el pad→net. Alternativa de diseño: mover los sensores a F.Cu (top) si el espejo no se corrige limpiamente.

**Otros hallazgos del forense (reales, para v0.1.2, NO causantes del fallo actual):**
- Net `/+3V3` con junta marginal en B.Cu `y=125` (≈41 µm centro-a-centro, ~159 µm de solape de cobre → conduce, pero frágil; el microSD comparte esa isla y funciona). Cerrar/re-rutear.
- `track_dangling` en `/I2C_SDA` en `(120.99, 112.31)` — stub muerto inofensivo, limpiar.

## 10. ACTUALIZACIÓN 2026-06-13 — TERCER error CONFIRMADO: footprint del BMP585 (U3) con SDA y SDO intercambiados

Hallazgo del usuario por inspección física, **confirmado de fuente autoritativa** (Adafruit Learn, guía BMP580/581/585 → Pinouts): *"SDO is the pin between SCL and SDA"*. El orden físico REAL del header del BMP585 es:

```
Vin · 3Vo · GND · SCL · SDO · SDA · CS · INT      (REAL, Adafruit)
Vin · 3Vo · GND · SCL · SDA · SDO · CS · INT      (lo que asumieron docs/footprint U3)
```

El footprint **U3 (BMP585)** mapea:
- pad4 = `/I2C_SCL` → pin físico SCL ✅
- pad5 = `/I2C_SDA` → pin físico **SDO** ❌ (el SDA del XIAO/D4 ataca el pin select de dirección)
- pad6 = NC → pin físico **SDA real** ❌ (la línea de datos del baro queda al aire)

→ El baro recibe Vin + GND + SCL correctos (por eso enciende y no cuelga el bus) pero **su SDA real no está conectado** → no hace ACK / no mide. **Independiente del espejo** (§9): es un error de orden de pines, no de orientación; ninguna orientación de montaje lo arregla (es un swap local de 2 pines adyacentes). El **IMU NO sufre esto** porque su SDA está en el pin 5 estándar (coincide con el footprint); solo el BMP585 tiene SDO antes que SDA.

**Workaround placas actuales:** llevar `/I2C_SDA` al pin SDA real del baro (pad6) y soltar el SDO:
- En placa: levantar el pin SDO del baro de pad5 (queda al aire → dir 0x47) y puentear pad5 (`/I2C_SDA`) → pad6 (SDA real). SCL/Vin/GND ya OK → ACK en 0x47.
- O montar el baro fuera del socket y cablear por función (`Vin→3V3, GND→GND, SCL→D5, SDA→D4`), dejando SDO/CS/INT al aire (como en protoboard, donde funcionaba).

**Fix v0.1.2:** intercambiar la asignación de pads **SDA↔SDO** en el footprint del BMP585 (U3) para que `/I2C_SDA` caiga en el pin 6 (SDA real) y el pad del pin 5 (SDO) quede NC o a GND (dirección fija). Corregir también el pinout en `docs/components/bmp585-barometer.md` (ya actualizado). **Verificar el pinout de CADA breakout contra su datasheet/silk real, no asumir orden uniforme entre sensores.**

Fuentes: [Adafruit BMP580/581/585 — Pinouts](https://learn.adafruit.com/adafruit-bmp580-bmp581-and-bmp585-temperature-and-pressure-sensor/pinouts), [guía completa](https://learn.adafruit.com/adafruit-bmp580-bmp581-and-bmp585-temperature-and-pressure-sensor).

## Referencias

- BLK-007 (`docs/BLOCKERS.md`, en el repo upstream) — bloqueo y plan de fix v0.1.2.
- ADR-015 (`docs/DECISIONS.md`, en el repo upstream) — decisión del workaround (XIAO en cara bottom).
- Firmware de bring-up con auto-diagnóstico de bus (idle-level + stuck-low + SDA↔SCL bridge test): rama `feat/firmware-xiao-s3-pcb-bringup`, `services/telemetry-cloud/firmware/src/main.cpp` (repo upstream).
- `docs/pcb-design.md §2` (repo upstream `multi-rocket-avionica`) — pinout funcional del XIAO.
- `docs/components/xiao-esp32s3-plus.md` (repo upstream `multi-rocket-avionica`) — pinout físico de referencia.
