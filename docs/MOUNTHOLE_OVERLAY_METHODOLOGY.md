# Methodology — Overlay alignment, mounting-hole placement & verification

> Síntesis de TODAS las metodologías usadas (2026-06-17/18) para alinear los
> overlays y dejar los taladros de anclaje bien colocados y centrados. Es
> **parte del pipeline**: se referencia desde METHODOLOGY.md (overlay step 4c y
> routing step 5) y se enforce en código + tests. Reglas duras en **negrita**.

---

## 0. REGLA DURA — NUNCA deformar las imágenes (factor de forma)

**El aspect ratio de `real_size_mm` ([w,h] en mm) DEBE coincidir con el aspect
ratio en píxeles de la imagen fuente.** Si no, el compositor estira la foto y sus
pines/orificios de anclaje caen en posiciones falsas (incidente 2026-06-18: LSM6
+12.6 %, BMP585 +10.1 % al escalar sólo el ancho).

- **Enforce en código:** `compositor._assert_image_aspect` falla si la desviación
  > 5 % (override documentado por módulo: `allow_aspect_deviation`). Tests:
  `test_pins.py::test_aspect_guard_rejects_deformation`,
  `::test_all_overlay_images_undistorted`.
- **Para redimensionar un módulo:** cambia w **y** h juntos (mantén el ratio).
- **Para ajustar el PASO de pines:** escala UNIFORME (un factor sobre ambos ejes)
  y luego re-centra con `body_offset_mm`. **Jamás** estires un solo eje.
- Comprobación rápida: `width ≈ height · (img_px_w/img_px_h)`.

---

## 1. Calibración mm↔px desde fiduciales (no a ojo)

- `render_overlay.render_calibrator.calibrate_from_holes`: ajusta una **afín 6-DOF**
  a los 6 centros de orificio de anclaje (H1–H6). Residual ≤ 0.01 mm. Es la
  calibración por defecto del compositor; *fallback* a la caja verde (`green_bbox`)
  si hay < 4 orificios.
- **El render base DEBE generarse con `--background transparent`.** Con `opaque` el
  fondo gris se ve a través de los taladros pasantes y la detección falla (LOO
  0.6–1.6 mm vs 0.0097 mm). El render comprometido es RGBA con taladros negros.
  Comando: `kicad-cli pcb render … --side <s> --background transparent --width 2384 --height 1176`.
- Regenerar el render cambia el framing (~2352 vs 2384 px) y desplaza ~0.2 mm la
  alineación de pines → **re-afinar el perpendicular tras regenerar** (verify.pins).

---

## 2. Detección de centros de orificio — DARK-BORE (invariante a iluminación)

- El centro real de un orificio es el **centroide del taladro oscuro** (dark-bore),
  no el del anillo dorado: el anillo sufre un sesgo de iluminación direccional de
  **hasta ~1.5 mm** en el render top. Ver `verify.holes._dark_bore_centroid`.
- Verificación de consistencia sin circularidad: **leave-one-out** (predecir cada
  orificio con los otros 5). Un orificio mal colocado salta como atípico.

---

## 3. Mapeo imagen-fuente → placa: transformación ISÓTROPA (no afín libre)

Para saber dónde caen en la placa los orificios/pines de un módulo a partir de su
imagen fuente:

- Detecta orificios + fila de pines en la **imagen fuente** (ahí son inequívocos).
- Aplica la **transformación isótropa del compositor** (escala uniforme + rotación
  + espejo de cara), **validada** con el residual de los pines (0.04–0.12 mm).
- **NO uses una afín libre ajustada sólo a los pines:** con pines colineales es
  DEGENERADA (no fija el eje perpendicular) → los orificios mapean mal (error de
  ~12 mm observado). La isótropa lo resuelve.

---

## 4. Centrar el taladro de la PCB en el orificio del módulo

- Métrica robusta: **ajuste geométrico de círculo (Kåsa)** al anillo dorado del
  módulo vs el **dark-bore** del taladro de la PCB. El centroide por intensidad y
  el borde blanco están sesgados por serigrafía/asimetría (residual fantasma
  ~0.2 mm que no converge); el ajuste de círculo sí converge (≤ 0.1 mm).
- **El taladro de la PCB (Ø2.1 mm, M2) es menor que el orificio del módulo
  (~M2.5)** → siempre queda un **anillo verde** alrededor del taladro:
  **uniforme = centrado**, en media luna = descentrado. Éste es el criterio visual.
- Evidencia: `validation/module-mount-holes/seethrough-*.png` (taladro negro
  concéntrico, anillo verde uniforme).

---

## 5. INTEGRACIÓN EN EL PIPELINE DE ENRUTADO (keepouts)

Los orificios de anclaje de módulo (MH1–MH6, huellas `MT_MountHole_M2`) interactúan
con el ruteo. Reglas para que **nunca** vuelva a ocurrir un taladro sobre una pista
(incidente MH1 vs `/+3V3`):

1. **Coloca los MH ANTES de rutear** (en la etapa `place`), en la posición real del
   orificio del módulo (§3–§4).
2. **Trata los MH como keepout de cobre** para el autorouter: el taladro NPTH debe
   tener su `hole_clearance` (0.25 mm) respetada; freerouting rutea alrededor si el
   orificio está presente en el DSN antes del export.
3. **Si mueves un MH, RE-RUTEA** (`run_autorouter.py`): una pista trazada antes del
   movimiento puede quedar atravesada por el nuevo taladro. Mover el orificio NO
   reenruta la pista.
4. **Verifica tras rutear:** DRC (`kicad-cli pcb drc`) — cualquier `hole_clearance`
   de una pista contra un pad NPTH de MH = FALLO a corregir reenrutando esa pista
   ≥ (radio_taladro + clearance) del centro del MH.
5. Re-rellena zonas tras cualquier movimiento de orificio (`pcbnew ZONE_FILLER`,
   LESSONS_LEARNED §11).

---

## 6. Gate de verificación (antes de `fab`)

`projects/mt1/tools/verify_holes.py` ejecuta, e idealmente bloquea `fab` si falla:

- **Anclajes H1–H6:** geométrico (diseño vs ground-truth) + visión (LOO) + diff
  visual (`validation/holes/`).
- **Pines sobre pads:** desplazamiento perpendicular rígido por módulo
  (`validation/pins/`).
- **Orificios de anclaje de módulo:** taladro PCB centrado en el anillo del módulo
  (§4, `validation/module-mount-holes/`).
- **DRC:** sin `hole_clearance` de pista contra MH (§5).

---

## Orden de operaciones (resumen)

```
schematic → place (incl. MH en su posición real) → ROUTE (MH como keepout)
  → render (--background transparent) → overlay (aspecto verificado, §0)
  → verify (H1-H6 + pines + mount-holes + DRC) → fab
```

Funciones clave: `render_calibrator.calibrate_from_holes`, `verify.holes`,
`verify.pins`, `compositor._assert_image_aspect`. Ver `../projects/mt1/REPORT.md` §4, §10 y
LESSONS_LEARNED §21–§24.
