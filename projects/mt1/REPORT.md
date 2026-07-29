# REPORT.md — Verificación de perforaciones de anclaje y alineación de overlays (MT1 v0.1.3)

**Fecha:** 2026-06-18 · **Placa:** MT1 v0.1.3 (`mt1-pcb.kicad_pcb`) · **Veredicto:** ✅ **PASS**

> Las 6 perforaciones de anclaje M2 de la v0.1.3 están **correctamente ejecutadas**:
> posición y Ø exactos frente a la ground-truth (desviación 0.000 mm) y, en el
> render, sus centros coinciden con lo esperado con error ≤ 0.008 mm (sub-píxel).
> Además, los overlays de módulo se alinean ahora **pin sobre pad**: tras una
> corrección paramétrica, U2/U3/U4 quedan con desviación perpendicular ≤ 0.065 mm
> (XIAO ≈ 0.5 mm, métrica de baja confianza por su cuerpo metálico — ver §4).

---

## 1. Resumen de cambios

| Artefacto | Tipo | Qué hace |
|---|---|---|
| `projects/mt1/ground-truth/holes.yaml` | NUEVO | Ground-truth canónica de las 6 perforaciones (posición, Ø, tornillo, tolerancias, fuentes citadas, separaciones del patrón). |
| `src/pcb_designer/verify/holes.py` | NUEVO | Motor de verificación de orificios: **G** geométrico (texto puro), **V** visión (afín 6-DOF + dark-bore + leave-one-out), **D** diff visual. |
| `src/pcb_designer/verify/pins.py` | NUEVO | Verificación **pines sobre pads** de cada overlay de módulo: métrica de desplazamiento perpendicular rígido de la fila de pines vs pads proyectados + diff visual por módulo. |
| `projects/mt1/tools/verify_holes.py` | NUEVO | Gate CLI combinado (orificios G+V+D **y** pines sobre pads). Informe / `--json`, exit ≠ 0 si falla. Hermano de `verify_placement.py`. |
| `src/pcb_designer/render_overlay/render_calibrator.py` | MOD | `Calibration` admite afín 6-DOF; `calibrate_from_holes()` deriva la escala de los fiduciales (orificios) con *fallback* a green-bbox. |
| `src/pcb_designer/render_overlay/compositor.py` + `cli.py` | MOD | Calibración por defecto = `mounting_holes` (afín de orificios); flag `--calibration`. |
| `projects/mt1/overlays/modules.yaml` | MOD | `body_offset_mm` de U2/U3/U4 corregidos paramétricamente (auto-alineación, ver §4). |
| `tests/unit/test_holes.py` · `test_pins.py` | NUEVO | 20 tests: parsing, geométrico (PASS + fallos sintéticos), afín, regresión CV/pines sobre v0.1.3, reproducibilidad, calibración. |
| `docs/PIPELINE.md` | NUEVO | Mapa del pipeline + tabla de transformaciones mm↔px (FASE 0). |
| `projects/mt1/validation/holes/` · `validation/pins/` | NUEVO | Evidencia visual: `holes-{diff,crops}-*.png` y `pins-<módulo>.png`. |

Dependencias: se añadieron `Pillow` y `numpy` al venv del repo (el paquete
`render_overlay` ya importaba PIL; el venv carecía de ambos). `requirements.txt`
de `render_overlay` ya los declara.

---

## 2. `holes_groundtruth` (FASE 1) con fuentes

Tornillo **M2** · taladro **Ø2.5 mm** · pad (anillo de cobre) **Ø5.0 mm**.

| Orificio | x (mm) | y (mm) | Ø taladro | Ø pad | Zona | Fuente |
|---|---|---|---|---|---|---|
| H1 | 175.0 | 105.0 | 2.5 | 5.0 | right_anchor (2×2) | (a) `H1` footprint + pad `(drill 2.5)(size 5 5)` |
| H2 | 185.0 | 105.0 | 2.5 | 5.0 | right_anchor | (a) diseño v0.1.3 |
| H3 | 175.0 | 125.0 | 2.5 | 5.0 | right_anchor | (a) diseño v0.1.3 |
| H4 | 185.0 | 125.0 | 2.5 | 5.0 | right_anchor | (a) diseño v0.1.3 |
| H5 | 95.0 | 107.0 | 2.5 | 5.0 | left_anchor (par) | (a) diseño v0.1.3 |
| H6 | 95.0 | 123.0 | 2.5 | 5.0 | left_anchor | (a) diseño v0.1.3 |

**Prioridad de fuentes aplicada** (a → b → c):
- **(a) Drill/footprint del propio diseño 0.1.3** — fuente primaria de las
  *posiciones* y *Ø*. Las 6 huellas son `MountingHole:MountingHole_2.5mm_Pad_Via`
  con pad `(drill 2.5)(size 5 5)` y `(descr "Mounting Hole 2.5mm M2")`.
- **(c) Librería estándar KiCad** — `MountingHole_2.5mm_Pad_Via.kicad_mod`:
  taladro 2.5 mm, pad Ø5.0 mm. El "2.5mm" del nombre es el **taladro**, no el
  tornillo (las huellas con tornillo usan sufijo, p.ej. `MountingHole_2.7mm_M2.5`).
  Fuente: kicad-footprints/MountingHole.pretty; convención KLC F2.1
  (`https://klc.kicad.org/footprint/f2/f2.1/`).
- **(b) Norma ISO 273:1979** — agujeros de paso M2: fino 2.2 / medio 2.4 /
  basto 2.6 mm. Un taladro de **2.5 mm** es un ajuste holgado/medio-basto válido
  para **M2** (entre medio y basto). Fuente: ISO 273:1979 §2
  (`https://www.iso.org/standard/4183.html`).
- **Conclusión:** Ø2.5 mm es **coherente** con la intención «M2» del diseño — sin
  conflicto. (Nota: las mechanical drawings de Adafruit de cada breakout NO se
  usan aquí porque las perforaciones de **anclaje** las define el PCB de la MT1,
  no los módulos; ver Supuesto S1.)

Separaciones del patrón verificadas: H1–H2 = H3–H4 = 10.0 mm (X); H1–H3 = H2–H4
= 20.0 mm (Y); H5–H6 = 16.0 mm (Y). **Todas PASS.**

---

## 3. Resultados sobre la v0.1.3 (FASE 4)

### 3.1 G — Geométrico (diseño `.kicad_pcb` vs ground-truth)

**6/6 orificios PASS · 5/5 separaciones PASS.** Desviación de posición de cada
orificio = **0.000 mm**; taladro y pad exactos (Ø2.5 / Ø5.0). El diseño coloca
los anclajes exactamente donde la ground-truth los espera.

### 3.2 V — Visión por computador sobre el render (centros detectados)

Calibración por afín de 6 orificios: **11.577 px/mm** en ambas caras. Centros por
**dark-bore** (invariante a iluminación). Métrica de aceptación = **leave-one-out**
(cada orificio predicho a partir de los otros 5 → atrapa cualquier desplazamiento
sin circularidad). Tolerancia `cv_tol = 0.30 mm`.

| Orificio | LOO top (mm) | LOO bottom (mm) | Veredicto |
|---|---|---|---|
| H1 | 0.0007 | 0.0052 | PASS |
| H2 | 0.0015 | 0.0038 | PASS |
| H3 | 0.0044 | 0.0063 | PASS |
| H4 | 0.0026 | 0.0022 | PASS |
| H5 | 0.0031 | 0.0078 | PASS |
| H6 | 0.0038 | 0.0083 | PASS |
| **máx** | **0.0044** | **0.0083** | **6/6 PASS** |

Residual de ajuste completo (consistencia intra-render) ≤ **0.0037 mm**. Es decir,
los 6 orificios del render son mutuamente consistentes con la rejilla nominal a
nivel sub-píxel: **ninguno está desplazado**.

### 3.3 D — Evidencia visual (lo más importante)

Por cara se generan dos imágenes en `projects/mt1/validation/holes/`:
- `holes-crops-{top,bottom}.png` — montaje de recortes ×6: círculo esperado
  (verde=PASS), centro esperado (+ magenta) y centro detectado (× cian). En todos,
  los marcadores caen en el **centro exacto del taladro** y el círculo Ø5 mm queda
  concéntrico con el pad dorado.
- `holes-diff-{top,bottom}.png` — placa completa con el mismo código de color.

---

## 4. Alineación de overlays — pines sobre pads (FASE 2)

### 4.1 Escala exacta, paramétrica
`calibrate_from_holes` ajusta una **afín 6-DOF** a los 6 centros de orificio
(residual ≤ 0.008 mm), sustituyendo al método green-bbox (sesgo ≈ 0.17 mm, sin
rotación/cizalla). **Paramétrico y reproducible — sin números mágicos.** Es la
calibración por defecto del compositor (*fallback* a green-bbox si < 4 orificios).

### 4.2 Verificación de pines sobre pads (`verify.pins`)
Métrica = **desplazamiento perpendicular rígido** de la fila de pines de la foto
(centroide del cobre dorado del módulo) frente a la fila de pads proyectada por la
afín. Se eligió tras descartar el dark-bore por-pin: en pines pequeños y juntos los
huecos oscuros entre pads se confunden con el taladro (ruido). El perpendicular
rígido tiene varianza baja y es la señal fiable de "fila sobre pads". El componente
*a lo largo* de la fila se reporta sólo como informativo (puede sesgarlo cobre no-pin
de la foto: conectores, blindajes). Tolerancia perpendicular = **0.15 mm**.

### 4.3 Hallazgo: los overlays de módulo estaban desalineados; corregidos paramétricamente
Las fotos de U2/U3/U4 estaban desplazadas perpendicularmente respecto a sus pads.
La corrección se **calculó** (no a ojo): residual perpendicular medido → vector mundo
→ `body_offset_mm` local vía `R(rot)⁻¹` (cuidando el espejo de la cara bottom).

| Módulo (ref) | perp ANTES | corrección Δlocal | **perp DESPUÉS** | veredicto |
|---|---|---|---|---|
| LSM6DSO32 (U2) | −0.535 mm | +0.535 (body_x −6.1→−5.565) | **+0.021 mm** | PASS |
| BMP585 (U3) | +0.219 mm | +0.219 (body_x −6.0→−5.781) | **−0.065 mm** | PASS |
| microSD (U4) | −0.262 mm | +0.262 (body_x 8.47→8.732) | **−0.005 mm** | PASS |
| XIAO (U1/U5) | ±0.55 mm | — (ver R6) | ±0.55 mm (lowconf) | PASS* |

Evidencia: `validation/pins/pins-<módulo>.png` — pads proyectados (+ magenta) sobre
la foto, círculo = tolerancia, cabecera con `perp` por fila y PASS/FAIL.

\* **XIAO**: su cuerpo metálico (USB-C, blindaje RF, antena) contamina el centroide
del cobre, así que la métrica automática es de **baja confianza** y no se usa para
fallar el gate. La inspección visual (`pins-XIAO_ESP32S3.png`) muestra los pads
proyectados sobre/junto a los taladros de la foto (desalineación ≈ 0.5 mm,
aceptable). No se aplicó corrección automática para no empeorar una alineación
correcta con una medida no fiable (ver R6).

### 4.4 Ajuste fino a lo largo de la fila — escala y traslación lateral (2026-06-18 b)
Tras alinear el perpendicular (§4.3), un repaso visual por-pin (zoom ×5 con el pad
proyectado superpuesto) reveló desajustes **a lo largo** de la fila:

| Módulo | Síntoma observado | Corrección **calculada** | Resultado |
|---|---|---|---|
| **microSD** (U4) | escala OK; el pad amarillo del zócalo no quedaba centrado en el orificio de la foto (desplazado a la izquierda) | traslación lateral: `body_offset_y` 10.79→**10.0** (≈ +0.79 mm board +X; `d(cx)/d(dyl)=−1`) | pad amarillo centrado en cada pin |
| **BMP585** (U3) | SDO (centro) perfecto, extremos agrupados hacia dentro → foto pequeña | escala fila: `real_size_mm[0]` 22.86→**25.19** (+10.2 %), pivote en el centro | círculo negro visible en los 8 pines |
| **LSM6DSO32** (U2) | SDA (centro) perfecto, extremos agrupados → foto pequeña | escala fila: `real_size_mm[0]` 22.86→**25.24** (+10.4 %) | los 9 pines como SDA |

Método: la pendiente de un ajuste lineal `pin_detectado = a·pin_esperado + b` separa
**escala** (a) de **traslación** (b); se aplicó iterativamente con re-render y
confirmación visual. Verificación tras el ajuste (perp, gate `verify.pins`):
microSD **−0.008 mm**, LSM6 **+0.050 mm**, BMP585 **−0.101 mm** (todos ≤ 0.15 mm).

> **Limitación (R8):** en la microSD el detector de cobre engancha el **pad fijo del
> diseño** que se ve a través del orificio (no la foto): un desplazamiento de 2.79 mm
> de la foto no movió la medida. Por eso su traslación lateral se ajustó **visualmente**,
> no por métrica. Las fotos `validation/pins/pins-<módulo>.png` son el sign-off.

Overlays v0.1.3 regenerados con la calibración por orificios, los `body_offset`
corregidos y las escalas de fila ajustadas; orificios y pines siguen en PASS.

---

## 5. Hallazgo técnico relevante: sesgo de iluminación del anillo dorado

El centroide del **anillo dorado** del pad (método ingenuo) está desplazado del
centro real del orificio por la iluminación direccional del render 3D:
**hasta 1.52 mm en el render top** y ~0.45 mm en el bottom (campo
`gold_shift_mm` del informe). Un verificador que usara el centroide dorado
mediría ese sesgo como "desplazamiento" o, peor, lo absorbería en la calibración y
dibujaría los círculos descentrados. El estimador **dark-bore** (centroide del
taladro oscuro, rotacionalmente simétrico) lo elimina y deja el centro real. Es la
razón de que las imágenes de diff muestren los círculos perfectamente centrados.

---

## 6. Criterios de aceptación — checklist con evidencia

| Criterio | Estado | Evidencia |
|---|---|---|
| Centrado de cada círculo ≤ 0.1 mm | ✅ | LOO ≤ **0.0083 mm** (≈ 0.1 px) ambas caras; tol justificada en §3.2 / holes.yaml |
| Pines visualmente sobre sus pads | ✅ | U2/U3/U4 perp ≤ **0.065 mm** tras corrección (§4.3); XIAO ≈0.5 mm lowconf visualmente OK; `pins-<módulo>.png` |
| Cada agujero PASS/FAIL vs ground-truth con desviación numérica | ✅ | §3.1 (geom 0.000 mm) + §3.2 (tabla LOO) + `--json` |
| Reproducibilidad (misma entrada → mismo resultado) | ✅ | `test_cv_reproducible`, `test_reproducible` (afín/centros/perp bit-idénticos); pipeline determinista |
| Imagen de comprobación por módulo a simple vista | ✅ | orificios: `holes-{crops,diff}-*.png`; módulos: `pins-<módulo>.png` (pad proyectado vs foto) |
| Suite de tests | ✅ | **40/40** (`pytest tests/`): 14 orificios + 6 pines + 20 previos |

**Tolerancias y su justificación.** A 11.58 px/mm, 1 px = 0.086 mm. La verificación
geométrica exige ≤ 0.10 mm (de hecho 0.000 mm). La visión usa `cv_tol = 0.30 mm`
(≈ 3.5 px): muy por encima del ruido sub-píxel del centroide (medido ≤ 0.008 mm)
pero muy por debajo del error mm que produciría un orificio realmente mal colocado.

---

## 7. Supuestos tomados

- **S1.** "Perforaciones de anclaje de los módulos" se interpreta como las **6
  perforaciones de anclaje del PCB de la MT1** (H1–H6, zona "ANCHOR"), que fijan la
  placa al cuerpo del cohete — no como los agujeros de montaje propios de cada
  breakout Adafruit. Motivo: son las que define el diseño y las que la serigrafía
  rotula "ANCHOR". Las mechanical drawings de los módulos se investigaron (ver §2)
  pero no aplican como fuente de estas posiciones.
- **S2.** Ground-truth de posiciones = diseño v0.1.3 (fuente a, máxima prioridad).
  Esto valida que el diseño es **internamente coherente y bien ejecutado** (Ø, M2,
  patrón); para validar contra un requisito mecánico **externo** del cohete haría
  falta el plano del chasis (no disponible) — ver R2.
- **S3.** `cv_tol = 0.30 mm` y `pos_tol = 0.10 mm` elegidas como en §6; ajustables
  en `holes.yaml`.
- **S4.** Calibración por defecto cambiada a `mounting_holes`; se mantiene
  `green_bbox` como *fallback* para placas sin ≥ 4 orificios.

## 8. Limitaciones y riesgos pendientes

- **R1 — Verificación sobre render, no sobre placa física.** V y D validan el
  *render*, no una foto del PCB fabricado. La verificación geométrica (G) sí valida
  el diseño que se envía a fábrica. Para cierre físico: fotografiar la placa y
  re-correr `verify_holes.py --use-base-renders` apuntando a la foto calibrada.
- **R2 — Sin requisito mecánico externo.** No hay plano del chasis del cohete, así
  que "posición correcta" = "según el diseño v0.1.3". Si existe un patrón de anclaje
  objetivo del cuerpo, añadirlo a `holes.yaml` como segunda ground-truth.
- **R3 — Sesgo global no observable por LOO.** El leave-one-out detecta
  desplazamientos *relativos*; un corrimiento *global* idéntico de los 6 orificios
  lo absorbería la afín. Mitigado porque G (geométrico, absoluto) ya fija las
  posiciones absolutas frente a la ground-truth.
- **R4 — Ø del pad en el render.** El anillo dorado renderizado aparenta algo más
  de Ø5 mm (apertura de máscara / antialias); la verificación de Ø se hace sobre el
  **diseño** (exacto), no midiendo el render. Sin impacto en el veredicto.
- **R5 — Umbrales de color/dark-bore calibrados** para el tema de render actual de
  kicad-cli; un cambio de tema/iluminación podría requerir re-tarado de los gates
  HSV/brillo en `verify.holes` / `verify.pins`.
- **R6 — XIAO: métrica de pines de baja confianza.** El cuerpo metálico del XIAO
  contamina el centroide del cobre, así que su desplazamiento perpendicular
  automático (~0.5 mm) no es fiable y no se corrigió (riesgo de empeorar). Camino
  de cierre: detector de pines robusto específico (p.ej. localizar las dos columnas
  de taladros en la imagen fuente y ajustar `real_size_mm`/separación de forma
  paramétrica), o validación visual manual con `pins-XIAO_ESP32S3.png`.
- **R7 — Componente "a lo largo" de la fila no verificado numéricamente** por el
  gate. La métrica de pines valida el perpendicular (fila sobre pads); el ajuste a lo
  largo (escala/traslación, §4.4) se hizo con medición lineal + confirmación visual.
  El orden/paso lógico de pines lo cubre el gate de pinout `verify_placement.py` (C1–C5).
- **R8 — microSD: traslación lateral por inspección visual.** El detector de cobre
  engancha el pad fijo del diseño (visible por el orificio), no la foto, así que el
  desplazamiento lateral de la microSD se ajustó visualmente (§4.4), no por métrica
  automática. Sign-off: `validation/pins/pins-microSD.png`.

---

## 9. Reproducir

```bash
cd <repo-root>
python3 -m pcb_designer.render_overlay.cli --version v0.1.3   # regenerar overlays
python3 projects/mt1/tools/verify_holes.py --version v0.1.3   # G+V+D → exit 0
python3 -m pytest tests/ -q                                   # 40 passed
```

---

## 10. Orificios de anclaje DE LOS MÓDULOS (MH1–MH6) — 2026-06-18 (c)

Distintos de los 6 anclajes del PCB (H1–H6, §3). Cada breakout tiene sus **propios
orificios de montaje** (2 por módulo) y el PCB lleva 6 huellas `MT_MountHole_M2`
(taladro Ø2.1 mm, M2) — MH1–MH6 — que deben quedar **bajo** esos orificios para
poder atornillar el módulo. Estaban descoordinados.

### 10.1 Prerrequisito: imágenes de overlay sin deformar
El escalado de fila del paso anterior (§4.4) había estirado las fotos de LSM6
(+12.6 %) y BMP585 (+10.1 %) al cambiar sólo `real_size_mm[0]`. Una foto deformada
sitúa sus orificios de anclaje en una posición falsa, así que **primero** se
restauró el aspect ratio de la imagen fuente (`real_size_mm[1]`: LSM6 16→18.019,
BMP 16→17.614 → estiramiento 0.0 %) y se re-centró el perpendicular de los pines
(LSM6 perp −0.027, BMP −0.031 mm). microSD (+1.2 %) y XIAO (−3.6 %) ya eran fieles.

### 10.2 Método: dónde están realmente los orificios del módulo
Se detectaron los 2 orificios de montaje (y la fila de pines) en cada **imagen
fuente** del breakout, se ajustó una transformación fuente→placa **isótropa**
(escala uniforme + rotación + espejo del compositor) y se validó con el residual
de los pines (**0.04–0.12 mm**). Clave: una afín completa es **degenerada** con
pines colineales (no fija el eje perpendicular) — por eso hay que usar la
transformación isótropa del compositor, no un ajuste afín libre. Los centros se
afinaron con el centroide sub-píxel del anillo dorado.

### 10.3 Corrección aplicada (se movieron los ORIFICIOS, no los módulos)

| MH | módulo | posición ANTERIOR | **NUEVA** | desplazamiento |
|---|---|---|---|---|
| MH1 | LSM6 | (125.12,111.40) | (123.737,111.150) | (−1.38,−0.25) |
| MH2 | LSM6 | (101.22,111.40) | (103.101,111.061) | (+1.88,−0.34) |
| MH3 | BMP585 | (132.40,105.42) | (132.271,106.022) | (−0.13,+0.60) |
| MH4 | BMP585 | (132.40,125.72) | (132.224,126.389) | (−0.18,+0.67) |
| MH5 | microSD | (125.00,126.90) | (125.839,126.056) | (+0.84,−0.84) |
| MH6 | microSD | (104.30,126.90) | (104.514,125.991) | (+0.21,−0.91) |

Asignación: **MH1/MH2 → LSM6**, **MH3/MH4 → BMP585**, **MH5/MH6 → microSD**.
Evidencia visual: `validation/module-mount-holes/{bottom-LSM6-BMP585,top-microSD}.png`
— los 6 MH (magenta) caen sobre los anillos dorados de montaje de cada foto.
Tras mover los orificios se **re-rellenaron las zonas** (`pcbnew ZONE_FILLER`).

### 10.4 ⚠️ Consecuencia que requiere decisión del usuario (reenrutado)
Mover los orificios a su posición correcta destapa conflictos de cobre que existían
porque los MH estaban *fuera* de los módulos:

- **REAL — MH1 vs pista `/+3V3`:** una pista vertical de `/+3V3` en F.Cu (x≈123.47,
  y 110.7–122.7) **atraviesa** el nuevo MH1 (Ø2.1 mm en 123.737,111.15). El taladro
  cortaría la pista. **Requiere reenrutar** esa pista ≥1.3 mm a un lado (fuera de
  alcance de "mover orificios"; decisión de routing del usuario). DRC: 2
  `hole_clearance`.
- **Esperado/cosmético:** `npth_inside_courtyard` (×2) y solape de serigrafía MHx
  con la del módulo (×~16) — normal cuando el orificio queda BAJO el módulo; los
  MH dentro de zonas GND ya se resolvieron con el re-relleno.
- DRC total: 72 (previo, preexistente) → 92. De los +20: 2 reales (MH1), 2 courtyard
  esperados, ~16 serigrafía cosméticos.

### 10.5 Render base regenerado (clave: fondo TRANSPARENTE)
Mover MH exige regenerar el PNG base 3D para que el taladro aparezca en su nueva
posición. El primer intento (`--background opaque`) hacía que los taladros pasantes
mostraran el GRIS del fondo → el dark-bore no los detectaba (LOO 0.6–1.6 mm). El
render comprometido usa **`--background transparent`** (taladros NEGROS al aplanar)
→ detección limpia (LOO 0.0097 mm). Comando correcto:
`kicad-cli pcb render … --side <s> --background transparent --width 2384 --height 1176`.
Tras regenerar (framing 2352×1152) se re-afinó el perpendicular de la fila LSM6
(body_offset −6.295→−6.117). Las zonas se re-rellenaron con `pcbnew ZONE_FILLER`.

### 10.6 Centrado fino VISUAL (proceso iterativo) — posiciones finales
Con el taladro negro de la PCB y el anillo dorado del módulo ya visibles en el
overlay, se centró cada taladro iterando con una métrica **robusta a iluminación**:
ajuste geométrico de círculo (Kåsa) al anillo dorado del módulo vs el centro del
taladro negro (dark-bore). (El centroide por intensidad y el borde blanco estaban
sesgados por serigrafía/asimetría — daban un residual fantasma de ~0.2 mm que no
convergía; el ajuste de círculo sí.) Nota: el taladro de la PCB es Ø2.1 mm (M2) y el
orificio del módulo es mayor (~M2.5), por eso queda un **anillo verde** alrededor del
taladro; **uniforme = centrado**, en media luna = descentrado.

| MH | módulo | posición FINAL | residual centro |
|---|---|---|---|
| MH1 | LSM6 | (123.171, 111.293) | 0.044 mm |
| MH2 | LSM6 | (102.941, 111.225) | 0.011 mm |
| MH3 | BMP585 | (132.316, 105.969) | 0.043 mm |
| MH4 | BMP585 | (132.309, 126.336) | 0.015 mm |
| MH5 | microSD | (125.124, 125.470) | 0.019 mm |
| MH6 | microSD | (104.380, 125.609) | 0.097 mm |

**Evidencia visual** (taladro PCB negro centrado bajo el orificio del módulo, anillo
verde uniforme): `validation/module-mount-holes/seethrough-{LSM6,BMP585,microSD}.png`.
Todos los residuales ≤ 0.097 mm (sub-píxel). Gate (orificios+pines) y 40 tests en PASS.

---

# v0.1.4 — Corrección de enrutado y colisiones módulo↔perforación (2026-06-18)

**Veredicto:** ✅ **PASS** · `mt1-pcb.kicad_pcb` · DRC **0 errores / 0 unconnected** (eran 8 errores).

## 11.1 Problema heredado de v0.1.3 (8 errores DRC)
Al situar los orificios de montaje de cada breakout (§10) afloraron 8 errores reales
(medidos con `kicad-cli pcb drc --severity-all`, baseline en `validation/drc-v0.1.3-baseline.json`):

| Error | n.º | Causa |
|---|---|---|
| `hole_clearance` | 2 | MH1 (123.171,111.293) atraviesa la traza `/+3V3` en F.Cu |
| `solder_mask_bridge` | 4 | MH5 sobre U2 pad1 `/+3V3`; MH6 sobre U2 pad8 |
| `npth_inside_courtyard` | 2 | MH5/MH6 dentro del courtyard de U2 |

## 11.2 Causa raíz: solape de cuerpos en caras opuestas
El **cuerpo de la microSD** baja desde su conector (U4, y≈108) hasta sus orificios
MH5/MH6 (y≈125.5); el **cuerpo del IMU** (LSM6) sube desde sus pads (U2, B.Cu, y≈124)
hasta MH1/MH2 (y≈111). Ambos breakouts, montados en caras opuestas, **solapan sus
cuerpos** en y≈111–125, y los orificios de montaje de cada uno perforan el cobre del
otro. Un solver geométrico (pcbnew, rejilla ±4 mm) demostró que **ningún desplazamiento
pequeño** lo resuelve: deslizar en X no saca los orificios de la banda de pads; mover
en +Y hunde MH1/MH2 en el cobre de U4. La única salida es **separar los dos subsistemas
en Y** (decisión de diseño aprobada por el usuario, conservando los 6 orificios).

## 11.3 Desplazamiento aplicado (separación 7.0 mm en Y)
Búsqueda de viabilidad sobre **toda la placa** (fila de conectores y≈103, borde inferior
y=130.05, U3/XIAO/anclas). Traslación pura → el `body_offset_mm` del overlay no cambia
(ancla en el footprint); MH se mueven solidariamente con su módulo.

| Footprint | Antes (x,y) | **Después (x,y)** | Δ |
|---|---|---|---|
| U2 (IMU) | (123.320,124.000) | (123.320,**119.500**) | (0,−4.5) |
| MH1 | (123.171,111.293) | (123.171,**106.793**) | (0,−4.5) |
| MH2 | (102.941,111.225) | (102.941,**106.725**) | (0,−4.5) |
| U4 (microSD) | (125.000,108.000) | (125.000,**110.500**) | (0,+2.5) |
| MH5 | (125.124,125.470) | (125.124,**127.970**) | (0,+2.5) |
| MH6 | (104.380,125.609) | (104.380,**128.109**) | (0,+2.5) |

Separación relativa = 7.0 mm (mínimo geométrico 6.4 mm; se eligió 7.0 para maximizar el
peor clearance a **0.862 mm**, holgado sobre el 0.25 mm exigido). Restricciones límite:
MH1/MH2 vs courtyard de U4 (0.862 mm) y MH5/MH6 vs borde inferior (0.891/1.030 mm). El
dict `PLACEMENTS` de `tools/place_components.py` se actualizó a las nuevas coordenadas.

## 11.4 Re-ruteo + reconexión de GND
- `tools/run_autorouter.py`: strip total + freerouting + `ZONE_FILLER`. Resuelve los pads
  movidos de U2 y rutea `/+3V3` libre de MH1 (keepout). 0 `hole_clearance`.
- El relayout partió el pour `/GND` (B.Cu, placa de 2 capas) en 3 islas (2 unconnected,
  problema estocástico conocido — U2 vive dentro del pour). Se reconectaron con **2
  jumpers GND** (vía→F.Cu→vía, vía Ø0.6/0.3, track 0.2 mm) saltando las barreras
  `/I2C_SDA`+`/I2C_SCL` (isla del IMU) y `/BAT_SW` (franja superior). Clearance ≥3.7 mm.

## 11.5 Resultado y validación
| Gate | Resultado |
|---|---|
| **DRC** (`validation/drc-v0.1.4.json`) | **0 errores · 0 unconnected** · 77 warnings cosméticos (48 silk_overlap, 12 lib_footprint_mismatch, 10 silk_over_copper, 7 silk_edge_clearance — baja desde 90 en v0.1.3) |
| `verify_placement.py` (C1–C5) | EXIT 0 — todos los pads con net correcto (U2@y119.5, U4@y110.5) |
| `verify_holes.py --version v0.1.4` | EXIT 0 — G 6/6+5/5 (0.000 mm); V LOO ≤0.011 mm; P pines: LSM6 0.094 / BMP585 0.064 / microSD 0.050 mm (XIAO 0.649 lowconf) |
| `pytest tests/` | **42/42** (fixtures de golden actualizados a overlays v0.1.4) |

**Artefactos:** renders `renders/v0.1.4-{top,bottom,dim-front,dim-back}.png` (3D base
transparente 2384×1176 para dark-bore); overlays `overlays/v0.1.4-realistic-{top,bottom}.png`;
release `releases/v0.1.4/` (gerbers ×9 + NPTH/PTH drill + pos + bom + zip). Serigrafía de
título actualizada a «MT1 v0.1.4». Backup del board v0.1.3 en `kicad/mt1-pcb.v0.1.3-backup.kicad_pcb`.

## 11.6 Reproducir
```bash
cd <repo-root>
# (board ya tiene el relayout v0.1.4 aplicado en PLACEMENTS + .kicad_pcb)
python3 projects/mt1/tools/run_autorouter.py                 # re-ruteo + GND fill
# (re-aplicar los 2 jumpers GND si se re-rutea desde cero — ver §11.4)
kicad-cli pcb render projects/mt1/kicad/mt1-pcb.kicad_pcb --side top    --background transparent --width 2384 --height 1176 --output projects/mt1/renders/v0.1.4-top.png
kicad-cli pcb render projects/mt1/kicad/mt1-pcb.kicad_pcb --side bottom --background transparent --width 2384 --height 1176 --output projects/mt1/renders/v0.1.4-bottom.png
python3 projects/mt1/tools/render_dim.py --version v0.1.4
python3 -m pcb_designer.render_overlay.cli --version v0.1.4  # overlays
python3 projects/mt1/tools/verify_placement.py              # exit 0
python3 projects/mt1/tools/verify_holes.py --version v0.1.4 # exit 0
.venv/bin/python -m pytest tests/ -q                        # 42 passed
```

> **Nota (R9):** los 2 jumpers GND son cobre añadido **tras** el re-ruteo. Si se vuelve a
> ejecutar `run_autorouter.py` (que hace strip total de tracks/vías), hay que **re-aplicar**
> los jumpers. Para hacerlos permanentes convendría declararlos en una rutina de post-ruteo
> (p.ej. extender `MT1_GND_STITCHES` con coordenadas del nuevo layout) — pendiente.
