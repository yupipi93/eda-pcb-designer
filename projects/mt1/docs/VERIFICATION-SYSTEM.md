# Sistema de verificación física de placement (anti-espejo)

Gate automático que valida la correspondencia **pin físico ↔ pad ↔ net ↔ orientación de montaje** del `.kicad_pcb` contra una **fuente de verdad** del pinout real de cada módulo. Nace de [POST-MORTEM-001](POST-MORTEM-001-mirror-rootcause.md): DRC/ERC/`verify_layout()` validan el cobre dibujado (internamente coherente) pero **nada** modelaba el componente físico, así que 3 espejos críticos llegaron a fabricación.

## Por qué hace falta (lo que NO cubrían las verificaciones previas)

| Capa | Valida | Punto ciego |
|---|---|---|
| ERC | netlist lógico | no sabe del componente físico |
| DRC | cortos/clearances en cobre | el cobre espejado de 1 columna coincide → invisible |
| `verify_layout()` | bounding boxes, contornos, solapes | no mira pad→net→pin ni quiralidad |
| render overlay (fotos) | aspecto realista | "calibra para que se vea bien" → oculta el espejo |
| **`verify` (este)** | **pin físico ↔ pad ↔ net ↔ cara** | — |

## Uso

```bash
# Reporte humano + enumeración de pines (exit ≠ 0 si hay fallos)
python3 projects/mt1/tools/verify_placement.py

# Salida máquina (CI / hooks)
python3 projects/mt1/tools/verify_placement.py --json

# Otro board / ground-truth
python3 projects/mt1/tools/verify_placement.py --pcb <ruta.kicad_pcb> --ground-truth <ruta.yaml>
```

Integrado en el pipeline como etapa `verify` **entre `route` y `fab`** (`src/pcb_designer/pipeline.py`): si falla, **no se generan gerbers**.

## Las 4 comprobaciones (cada una caza un fallo conocido)

| Check | Qué hace | Caza |
|---|---|---|
| **C1 Quiralidad** | Signo del producto cruz de una tríada de pines no colineales (coords globales) vs. el esperado según `mount_side`. | XIAO con columnas D0/potencia intercambiadas (espejo). |
| **C2 Integridad de flip** | Todo footprint en B.Cu debe tener `(justify mirror)` en sus textos (firma de un volteo real de KiCad). Si no, fue un `flip_to_back` falso (solo renombró capas). | Sensores U2/U3 que entran en espejo al montarse por bottom. |
| **C3 pad→net→función** | Por pad: el net asignado debe casar con la función del pin **físico** (del ground-truth). | BMP585 con SDA/SDO intercambiados (SDA al aire). |
| **C4 Conectividad por intención** | Cada bus clave (I²C, SDIO, +3V3) debe tocar exactamente el conjunto de pads previsto. | Red de seguridad general (corrobora C3). |

## Fuente de verdad — `projects/mt1/ground-truth/components.yaml`

Pinout **físico real** de cada módulo (de su datasheet/silkscreen), independiente del esquemático y del footprint:

```yaml
components:
  BMP585:
    refs: [U3]
    mount_side: bottom            # cara del CUERPO del módulo (top=F.Cu, bottom=B.Cu)
    source: "Adafruit BMP585 Pinouts"
    pins:
      "U3.5": {func: SDO, net: null}        # pin físico 5 = SDO (NO SDA)
      "U3.6": {func: SDA, net: /I2C_SDA}    # pin físico 6 = SDA real
    # chirality_triad: SOLO para piezas multi-columna (no colineales)
```

- `pins["<ref>.<pad>"]` → `{func, net}`. `net` es la red que ESE pin físico debe llevar (intención). `null` = NC.
- `chirality_triad` → 3 pines no colineales con coords en el marco **local canónico** de la pieza (vista por su cara de componente, +Y arriba). El verificador deriva el signo esperado en el board según `mount_side`. Solo para piezas con ≥2 columnas (las de 1 fila son colineales → la quiralidad no se define con geometría; las cubre C2).

### Añadir un componente

1. Mirar el silkscreen/datasheet del módulo y anotar el orden físico de pines.
2. Añadir el bloque a `components.yaml` con `refs`, `mount_side`, `pins` (func + net esperado).
3. Si tiene ≥2 columnas, añadir `chirality_triad`.
4. Re-ejecutar `verify_placement.py`.

## Interpretar el reporte

- Bloques **C1–C4** con `[PASS]/[FAIL]` por componente + detalle de cada discrepancia.
- **Enumeración de pines**: por footprint, tabla `pad → global(x,y) → net actual → función física → net esperado → ok`, con la cara/`at` y si es vista top o bottom. Es la tabla que un humano usa para revisar la placa antes de fabricar.

## Estado actual del board (v0.1.x)

Sobre `mt1-pcb.kicad_pcb` el gate reporta **5 fallos** (los 3 bugs conocidos):

- C1 → `XIAO_ESP32S3` ESPEJADO.
- C2 → `LSM6DSO32 (U2)` y `BMP585 (U3)` flip falso.
- C3 → `BMP585 (U3)` SDA/SDO intercambiados.
- C4 → `/I2C_SDA` toca el pad equivocado.

Tras el fix v0.1.2 (BLK-007, en `docs/BLOCKERS.md` del repo upstream: swap U1/U5, footprint BMP585, volteo real) el gate debería salir en verde.

## Tests

`tests/unit/test_verify.py` — geometría (posición global de pad con rot/espejo) + **regresión de oro**: contra el board actual el verificador DEBE reportar exactamente esos 5 fallos y PASAR las partes correctas (prueba de que no da falsos positivos).

```bash
.venv/bin/python -m pytest tests/unit/test_verify.py -v
```

## Limitaciones / trabajo futuro

- C2 detecta el flip falso por ausencia de `(justify mirror)`; cuando se corrija `flip_to_back` para hacer un volteo real, este check pasará a verde automáticamente.
- C1 requiere `chirality_triad` (solo multi-columna). Las piezas de 1 fila dependen de C2 + C3.
- Posible extensión: render anotado que pinte el pad-1 real y el vector pin1→pin2 sobre la foto del overlay (que un espejo se vea a simple vista).
</content>
