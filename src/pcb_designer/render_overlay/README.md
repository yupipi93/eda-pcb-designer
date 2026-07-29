# render-overlay — Render fotorrealista con módulos físicos + dimensiones técnicas

Herramienta autocontenida que toma un render generado por `kicad-cli pcb
render` (PNG plano que solo muestra cobre + silkscreen) y lo enriquece
con:

1. **Fotos reales de los breakouts** (XIAO ESP32S3, LSM6, BMP585, microSD,
   etc.) escaladas, rotadas y posicionadas sobre las áreas correspondientes
   del PCB para visualizar "cómo queda con los chips puestos".
2. **Anotaciones técnicas de dimensión** (estilo dibujo técnico) con
   líneas de cota, flechas y etiquetas: tamaño de la PCB, anchura de cada
   zona de anclaje, separación entre mounting holes, separación entre pin
   rows del XIAO, y bbox/dimensión de cada módulo.

```
projects/mt1/renders/v0.1.X-top.png  ─┐
                                          ├─► cli.py ─► projects/mt1/overlays/v0.1.X-realistic-top.png
projects/mt1/overlays/modules.yaml ───┤            projects/mt1/overlays/v0.1.X-realistic-bottom.png
+ component-images/                       │
projects/mt1/kicad/mt1-pcb.kicad_pcb ─┘
```

---

## Tabla de contenidos

- [Quick start](#quick-start)
- [CLI completo](#cli-completo)
- [Cómo funciona la calibración mm ↔ px](#cómo-funciona-la-calibración-mm--px)
- [Anatomía de `modules.yaml`](#anatomía-de-modulesyaml)
  - [Schema completo](#schema-completo)
  - [Cómo se calcula `body_offset_mm` paso a paso](#cómo-se-calcula-body_offset_mm-paso-a-paso)
  - [Cómo se elige `image_rotation_deg`](#cómo-se-elige-image_rotation_deg)
- [Anotaciones técnicas](#anotaciones-técnicas)
  - [Categorías disponibles](#categorías-disponibles)
  - [Convenciones visuales](#convenciones-visuales)
  - [Cómo extender con nuevas categorías](#cómo-extender-con-nuevas-categorías)
- [Cómo añadir un módulo nuevo](#cómo-añadir-un-módulo-nuevo)
- [Cómo preparar una foto de breakout](#cómo-preparar-una-foto-de-breakout)
- [Capa visible y mirror del bottom](#capa-visible-y-mirror-del-bottom)
- [Workflow para futuras iteraciones de PCB](#workflow-para-futuras-iteraciones-de-pcb)
- [Arquitectura interna](#arquitectura-interna)
- [Troubleshooting](#troubleshooting)
- [Convenciones de orientación KiCad](#convenciones-de-orientación-kicad)
- [Limitaciones conocidas](#limitaciones-conocidas)

---

## Quick start

```bash
# Desde la raíz del repo, con el venv del paquete
# activo (`source .venv/bin/activate`):
python3 -m pcb_designer.render_overlay.cli --version v0.1.0-battery-power
```

Salida en `projects/mt1/overlays/v0.1.0-battery-power-realistic-{top,bottom}.png`.

**Pre-requisito**: que existan los renders base
`projects/mt1/renders/v0.1.0-battery-power-{top,bottom}.png`
(generados por `projects/mt1/tools/place_components.py` o manualmente con
`kicad-cli pcb render`).

---

## CLI completo

```
python3 -m pcb_designer.render_overlay.cli --version VERSION [opciones]
```

| Flag | Default | Descripción |
|---|---|---|
| `--version VERSION` | (requerido) | Tag de la versión. Debe existir `<renders-dir>/VERSION-top.png` y `<renders-dir>/VERSION-bottom.png`. |
| `--side top\|bottom\|both` | `both` | Generar solo una cara. |
| `--debug` | off | Dibuja bbox magenta + anchor amarillo sobre cada módulo (para depurar alineación). |
| `--no-annotations` | off | Desactiva todas las anotaciones técnicas. |
| `--annotations LIST` | `pcb,anchors,holes,modules,pins` | Categorías de anotación a dibujar (CSV). Ver [Anotaciones técnicas](#anotaciones-técnicas). |
| `--project-dir DIR` | `projects/mt1` | Board project dir; el resto de defaults derivan de él. |
| `--pcb PATH` | `<project-dir>/kicad/*.kicad_pcb` | Archivo `.kicad_pcb` fuente. |
| `--renders-dir DIR` | `<project-dir>/renders` | Carpeta donde están los renders base. |
| `--modules PATH` | `<project-dir>/overlays/modules.yaml` | Config de módulos (board-específica). |
| `--images-dir DIR` | `<project-dir>/overlays/component-images` | Carpeta con fotos/mockups de módulos. |
| `--output-dir DIR` | `<project-dir>/overlays` | Destino de los renders resultantes. |

**Ejemplos:**

```bash
# Render fotorrealista completo (default)
python3 -m pcb_designer.render_overlay.cli --version v0.1.0-battery-power

# Sólo top, sin anotaciones (más limpio para mostrar en presentaciones)
python3 -m pcb_designer.render_overlay.cli --version v0.1.0-battery-power --side top --no-annotations

# Sólo PCB outline + anchors (sin module bboxes para reducir clutter)
python3 -m pcb_designer.render_overlay.cli --version v0.1.0-battery-power --annotations pcb,anchors,holes,pins

# Modo depuración: bbox magenta + anchor amarillo sobre cada módulo
python3 -m pcb_designer.render_overlay.cli --version v0.1.0-battery-power --debug

# Apuntar a otra versión de PCB / otra carpeta de renders
python3 -m pcb_designer.render_overlay.cli --version experimental \
        --pcb /tmp/experimental.kicad_pcb \
        --renders-dir /tmp/renders \
        --output-dir /tmp/realistic
```

Salida típica:

```
[top] rendered 7 modules → v0.1.0-battery-power-realistic-top.png
         px_per_mm = 8.67, pcb_outline_mm = (90.0, 100.0, 190.0, 130.0)
[bottom] rendered 2 modules → v0.1.0-battery-power-realistic-bottom.png
         px_per_mm = 8.67, pcb_outline_mm = (90.0, 100.0, 190.0, 130.0)
```

Si un módulo declarado en `modules.yaml` no tiene su `anchor_ref` en el
`.kicad_pcb`, aparece en `skipped: …` (warning, no error).

---

## Cómo funciona la calibración mm ↔ px

`render_calibrator.py` (en este mismo directorio; el viejo subdir `lib/`
se aplanó en T-011) detecta automáticamente la zona verde de FR4 en el
PNG base mediante una máscara HSV:

- H ∈ [80, 125] (verde KiCad, calibrado empíricamente — un sample del
  centro de la PCB rinde HSV ≈ (105, 106, 74) en PIL 0..255).
- S ≥ 40 (saturación mínima para descartar grises del fondo gradiente).
- V ≥ 25 (luminosidad mínima).

Estrategia:

1. Saca un bounding box del verde (`Image.getbbox()`).
2. **Sanity check**: si el aspect ratio del bbox diverge >5% del aspect
   ratio del Edge.Cuts del `.kicad_pcb`, salta a paso 3.
3. **Fallback robusto**: cuenta píxeles verdes por columna y por fila;
   toma el rango contiguo de columnas/filas con conteo ≥ 30% del peak.
   Esto descarta protrusiones finas (cuerpo 3D de un socket que sobresale
   del borde) que contaminarían el bbox.
4. El bbox final se mapea uno-a-uno con el rectángulo `Edge.Cuts` del
   `.kicad_pcb` → `px_per_mm` + offset.

**Por qué importa**: la herramienta funciona automáticamente con
cualquier geometría futura del PCB (v0.0.12, v0.1.0, …) sin tocar
constantes hardcodeadas. Si el PCB cambia de 100×30 a 120×40, el
script detecta el nuevo outline y re-escala todas las imágenes.

Para el render BOTTOM, `Calibration.mirrored_x = True` invierte el eje
X (`rel_x = pcb_x1 - x_mm` en lugar de `x_mm - pcb_x0`), reproduciendo
la convención KiCad de espejo lateral.

---

## Anatomía de `modules.yaml`

### Schema completo

```yaml
modules:
  MyModule:
    refs: [U6, U7]              # Footprints que forman el módulo
    anchor_ref: U6              # Cuál define posición + rotación
    positioning: anchor_offset  # bbox_center | anchor_offset
    image: my-module.png        # Path relativo a images/
    real_size_mm: [25.4, 17.78] # [width, height] EN LA ORIENTACIÓN NATIVA
    image_rotation_deg: 90      # Rotación CCW para alinear pin row a +Y
    body_offset_mm: [7.62, 11.43] # Offset desde pin 1 al centro de imagen
                                # (en MÓDULO-LOCAL, asumiendo rot=0)
    visible_layer: B.Cu         # F.Cu (top only) | B.Cu (bottom only)
    category: sensor            # sensor | module | switch | connector | default
                                # (solo afecta color del mockup procedural)
```

**Modos de `positioning`:**

- **`bbox_center`** — el centro de la imagen se coloca en el bbox center
  de TODAS las `refs`. Ideal para módulos que se montan sobre múltiples
  footprints (XIAO sobre U1+U5+J2). `body_offset_mm` se ignora.

- **`anchor_offset`** — el centro de la imagen se coloca en
  `anchor_ref.position + body_offset_mm` (con el offset rotado por la
  rotación del `anchor_ref`). Ideal para sockets 1×N donde el pin 1
  está en una esquina del breakout y el cuerpo se extiende hacia un lado.

### Cómo se calcula `body_offset_mm` paso a paso

Esto es lo más sutil del schema. Sigue estos pasos:

**1)** Identifica las coordenadas en píxeles del **pin 1** en la imagen
nativa (sin rotar). Las breakouts Adafruit típicamente tienen el pin
header en un borde con un margen estándar de **1.27mm** entre el primer
pin y la esquina del PCB del breakout.

  - Para una imagen landscape con pin row en el borde inferior, pin 1 en
    `(1.27, image_height_mm - 1.27)` desde top-left.
  - Para una imagen portrait con pin row en el borde derecho, pin 1 en
    `(image_width_mm - 1.27, 1.27)`.
  - **Trabaja en mm**, no en píxeles: usa las dimensiones físicas que
    declaraste en `real_size_mm`.

**2)** El centro de la imagen está en `(image_width_mm / 2, image_height_mm / 2)`.

**3)** Calcula el **offset NATIVO** de pin 1 al centro:
```
offset_native = (center_x - pin1_x, center_y - pin1_y)
              = (W/2 - 1.27, H/2 - (H - 1.27))
              = (W/2 - 1.27, 1.27 - H/2)
```

**4)** Aplica la rotación inversa de `image_rotation_deg`. Como el
schema dice que la imagen se rota CCW por `image_rotation_deg` para
llegar a la convención PCB rot=0, el offset (definido en módulo-local
= post-rotación) se obtiene aplicando la MISMA rotación CCW al offset
nativo:

```
Para image_rotation_deg = 90° (CCW):
  (dx_native, dy_native) → (-dy_native, dx_native)
```

**Ejemplo real LSM6** (image 25.4 × 17.78 mm, `image_rotation_deg = 90`):
```
pin 1 nativo:    (1.27, 16.51)
centro nativo:   (12.7, 8.89)
offset nativo:   (12.7 - 1.27, 8.89 - 16.51) = (11.43, -7.62)
tras CCW 90°:    (7.62, 11.43)
→ body_offset_mm: [7.62, 11.43]
```

**Verificación**: con este offset, cuando el footprint U2 está en
`(152, 104.84)` con `rot=0`, el script coloca el centro de imagen en
`(152 + 7.62, 104.84 + 11.43) = (159.62, 116.27)`. Después de rotar la
imagen CCW 90°, su pin 1 acaba exactamente en `(152, 104.84)` — pixel
perfect sobre el footprint.

### Cómo se elige `image_rotation_deg`

La convención del schema: tras aplicar `image_rotation_deg` (CCW), la
imagen debe quedar como si su `anchor_ref` estuviera en `rot=0`, es
decir, **pin row vertical en el borde izquierdo con pin 1 arriba, body
extendiéndose hacia la derecha**.

Casos comunes:

| Imagen nativa (pin row en…) | `image_rotation_deg` |
|---|---|
| Borde izquierdo, pin 1 arriba (ya en convención KiCad) | 0 |
| Borde inferior, pin 1 a la izquierda (Adafruit landscape) | 90 |
| Borde derecho, pin 1 abajo | 180 |
| Borde superior, pin 1 a la derecha | 270 |
| Ambos bordes verticales (XIAO con headers a izquierda y derecha) | 0 con `positioning: bbox_center` |

El script combina `image_rotation_deg` con la rotación PCB del
`anchor_ref` automáticamente:

```python
pil_rot = -pcb_rotation_deg + image_rotation_deg
if mirrored_x:  # bottom render
    pil_rot = -pil_rot
```

---

## Anotaciones técnicas

Activadas por defecto. Se dibujan al final del compositing, encima de
las imágenes de módulos. Estilo: líneas de 1px con flechas pequeñas
(5px) y etiquetas con caja blanca semi-transparente para legibilidad
sobre el verde del FR4.

### Categorías disponibles

| Categoría | Color | Contenido |
|---|---|---|
| `pcb` | azul-gris (40,40,60) | Dimensión total Edge.Cuts: `PCB 100 mm` arriba, `30 mm` derecha |
| `anchors` | magenta (200,80,180) | Anchura izquierda `L:10`, derecha `R:20`, zona electrónica `electronic zone 70` |
| `holes` | naranja (220,160,40) | Separación entre mounting holes (vertical H5↔H6, horizontal H1↔H2, vertical H1↔H3) |
| `pins` | azul (60,130,220) | Separación entre pin rows críticas (U1↔U5 del XIAO) |
| `modules` | verde (40,160,90) | Bbox + tamaño en mm de cada módulo visible (`XIAO 17.8×21.0`) |

(`annotations.py` vive en `src/pcb_designer/render_overlay/annotations.py`
desde T-011; antes estaba en `lib/annotations.py`.)

**Selección por CLI** (CSV):
```bash
--annotations pcb,anchors,holes          # solo PCB + anchors + holes
--annotations modules                    # solo bbox de módulos
--no-annotations                         # ninguna
```

**Origen de los datos** (todo automático, sin constantes hardcodeadas
salvo los límites de zona anchor):

| Categoría | Fuente |
|---|---|
| `pcb` | `get_pcb_outline(.kicad_pcb)` — Edge.Cuts rectangle |
| `anchors` | `LEFT_ANCHOR_INNER_X = 100`, `RIGHT_ANCHOR_INNER_X = 170` en `annotations.py` (constantes de proyecto, ajustar si cambian) |
| `holes` | Footprints con ref que empieza por `H` |
| `pins` | Footprints `U1` y `U5` (extensible a más pares) |
| `modules` | `real_size_mm` × `image_rotation_deg` de cada entrada en `modules.yaml` |

### Convenciones visuales

- **Trazos finos** (1px) para no tapar el contenido principal.
- **Etiquetas con fondo blanco semi-transparente** (alpha 215/255) para
  legibilidad sobre cualquier capa (verde PCB, gradiente del fondo).
- **Flechas pequeñas** (5px triangulares rellenas) en cada extremo de
  cada cota.
- **Ticks de extensión** (5px) perpendiculares al inicio/fin de cada cota.
- **Colores por categoría** para identificación visual rápida (ver tabla).
- **Anotaciones FUERA del PCB**: width/height arriba/derecha del board;
  anchors abajo. Esto deja el área electrónica del PCB libre para que
  los módulos sean claramente visibles.

### Cómo extender con nuevas categorías

Añade una nueva función `_annotate_<nombre>(...)` en `annotations.py`
(en este mismo directorio) siguiendo el patrón de las existentes
(recibe `draw`, `calib`, y los datos necesarios; usa los primitivos
`_dim_h`, `_dim_v`, `_bbox_outline`, `_draw_label`). Luego inclúyela
en `draw_annotations()`:

```python
def draw_annotations(..., categories=(...,)):
    ...
    if "mi_categoria" in categories:
        _annotate_mi_categoria(draw, calib, ...)
```

El default en `compositor.compose_side()` la incluirá si la añades a
`annotation_categories`. También puedes pasarla por CLI:
`--annotations pcb,anchors,mi_categoria`.

---

## Cómo añadir un módulo nuevo

1. **Coloca la foto** en `images/<nombre>.png` (preferiblemente PNG con
   alpha — esquinas transparentes — o JPG con fondo de estudio
   uniforme).

2. **Mide la imagen**: anota `image_width_px × image_height_px`. Verifica
   que coincida con el aspect ratio físico real del breakout. Si no
   coincide, recorta o ajusta la foto.

3. **Identifica el pin 1** en la imagen. Para footprints 1×N este es el
   primer pin del header (`Vin`, `+3V3`, `CLK`, etc. según el módulo).

4. **Añade entrada en `modules.yaml`**:

```yaml
mi_modulo:
  refs: [U6]
  anchor_ref: U6
  positioning: anchor_offset
  image: mi-modulo.png
  real_size_mm: [25.4, 17.78]   # ajustar a las dims físicas reales
  image_rotation_deg: 90         # ver tabla de elección
  body_offset_mm: [7.62, 11.43]  # ver derivación paso a paso
  visible_layer: B.Cu            # o F.Cu
  category: sensor
```

5. **Verifica con `--debug`**:

```bash
python3 -m pcb_designer.render_overlay.cli --version v0.1.0-battery-power --debug
```

Esto dibuja un bbox magenta + anchor amarillo sobre cada módulo, así
puedes confirmar visualmente que el pin 1 de la imagen cae sobre el
pin 1 del footprint.

6. **Ajusta `body_offset_mm` o `image_rotation_deg`** si el módulo no
   queda perfectamente alineado, y re-ejecuta hasta que sea
   pixel-perfect.

Si la imagen no existe, el script genera un mockup procedural coloreado
con el nombre del módulo y sus dimensiones, así el script nunca se
rompe por falta de assets.

---

## Cómo preparar una foto de breakout

Para máxima compatibilidad con el auto-mask:

1. **Vista cenital** (top-down), perpendicular a la breakout. Evita
   ángulos isométricos: rompen la correspondencia mm ↔ píxeles.

2. **Fondo uniforme** (blanco, gris, o transparente). Si es opaco, el
   script lo recorta automáticamente:
   - Si el PNG tiene canal alpha con esquinas transparentes
     (`alpha < 16`), se respeta tal cual.
   - Si es JPG o PNG opaco, se sample-an las 4 esquinas y se enmascaran
     los píxeles dentro de Chebyshev distance 35 de la mediana
     (suficiente para fondos blancos / grises de estudio).

3. **Orientación consistente**: coloca el pin row en uno de los 4 bordes
   (no diagonales) para simplificar `image_rotation_deg`.

4. **Centra el módulo en la imagen**: el bbox de la breakout debe llenar
   ≥ 90% del área. Recorta márgenes innecesarios.

5. **Resolución**: 300-800 px en el lado largo es suficiente. Más alto
   no mejora visiblemente la salida (1800×900 final).

---

## Capa visible y mirror del bottom

- **Render TOP**: solo módulos con `visible_layer: F.Cu`.
- **Render BOTTOM**: solo módulos con `visible_layer: B.Cu`. KiCad
  espeja X horizontalmente, así que la herramienta:
  - Invierte X en `mm_to_px` (`rel_x = pcb_x1 - x_mm`).
  - Invierte el signo de la rotación PIL (`pil_rot = -pil_rot`).
  - Aplica `Image.transpose(FLIP_LEFT_RIGHT)` a la imagen del módulo,
    de modo que los logos y texto se leen como vista trasera (espejados
    horizontalmente, no rotados 180°).

Las anotaciones técnicas se renderizan idéntico en ambos lados — el
mirror se hereda de la `Calibration` y todas las cotas terminan en el
sitio físico correcto.

---

## Workflow para futuras iteraciones de PCB

El sistema está diseñado para sobrevivir cambios estructurales sin
intervención manual.

**Si cambia el outline del PCB** (ej. v0.0.12 con dimensiones 110×35):
- `render_calibrator` detecta el nuevo bbox verde automáticamente.
- `pcb_parser` lee el nuevo `Edge.Cuts` rectangle.
- Las anotaciones reflejan los nuevos números.
- No hay que tocar nada.

**Si se mueven mounting holes**:
- `_annotate_mounting_holes` agrupa por anchor inner X y deduce las
  separaciones automáticamente.
- Los nuevos números aparecen en las cotas.

**Si se añaden / mueven footprints existentes**:
- `pcb_parser.parse_footprints()` extrae las nuevas posiciones.
- `_compute_image_center_mm` recalcula con las nuevas coords.
- Las imágenes se reposicionan donde correspondan.

**Si se añade un módulo nuevo**:
- Sigue [Cómo añadir un módulo nuevo](#cómo-añadir-un-módulo-nuevo).
- Solo se toca `modules.yaml` + nueva imagen en `images/`.

**Las dos únicas constantes específicas del proyecto** (que sí hay que
revisar si cambia la convención):

```python
# src/pcb_designer/render_overlay/annotations.py
LEFT_ANCHOR_INNER_X  = 100.0   # x ≤ esto = zona anchor izquierdo
RIGHT_ANCHOR_INNER_X = 170.0   # x ≥ esto = zona anchor derecho
```

Si en v1.0.0 el equipo decide otra distribución de anchors, edita estas
dos líneas (o muévelas a `modules.yaml` / `examples/mt1.yaml` con tu
propio adaptador).

---

## Arquitectura interna

Post-T-011, todos los módulos viven planos bajo `src/pcb_designer/render_overlay/`
(antes estaban en un subdir `lib/`). El config y los assets MT1-específicos
se movieron al board:

```
src/pcb_designer/render_overlay/         ← subpaquete (board-agnostic)
├── __init__.py
├── cli.py                       CLI entry point (antes overlay_render.py)
├── pcb_parser.py                regex S-expression sobre .kicad_pcb
├── render_calibrator.py         detección HSV + projection fallback
├── module_overlay.py            scale + rotate + alpha + auto-mask
├── compositor.py                orquestación + positioning resolver
├── annotations.py               dim lines + flechas + labels
├── mock_image.py                generador procedural para imágenes faltantes
├── requirements.txt             Pillow + PyYAML (sin numpy ni opencv)
└── README.md                    ← este archivo

projects/mt1/overlays/       ← assets MT1-específicos
├── modules.yaml                 Config editable de módulos
├── component-images/            Fotos / mockups
└── v0.1.X-*-realistic-*.png     Generados (gitignored salvo releases)
```

**Flujo principal** (`compositor.compose_side()`):

1. Parsea `modules.yaml` → lista de `ModuleConfig`.
2. Parsea `.kicad_pcb` → `{ref: (x, y, rot, layer)}`.
3. Lee el render base (PNG).
4. `calibrate()` detecta el verde FR4 → `Calibration(px_per_mm, …)`.
5. Para cada módulo cuya `visible_layer` coincide con el lado:
   - `_compute_image_center_mm()` resuelve el centro destino.
   - `render_module()` carga, escala, rota la imagen.
   - `alpha_composite()` la fusiona sobre el render base.
6. `draw_annotations()` añade las cotas técnicas.
7. Guarda PNG en `outputs/`.

**Dependencias externas**: solo Pillow ≥ 10 y PyYAML ≥ 6. Sin numpy ni
opencv — todas las operaciones de píxeles van por PIL pura. A
1800×900 px la performance es suficiente (< 5 s end-to-end por lado).

---

## Troubleshooting

### El módulo aparece pero descolocado del footprint

Lo más probable es que `body_offset_mm` o `image_rotation_deg` no
cuadren con la orientación nativa de la foto. Pasos:

1. Ejecuta con `--debug` y mira dónde cae el anchor amarillo vs dónde
   está el footprint real.
2. Revisa la sección [Cómo se calcula `body_offset_mm` paso a paso](#cómo-se-calcula-body_offset_mm-paso-a-paso).
3. Verifica que `real_size_mm` esté en la orientación NATIVA (no
   rotada) — i.e., `[width, height]` de la imagen tal cual se guardó.

### El bbox verde detectado es demasiado pequeño

Posibles causas:

- Render base con un PCB de color no estándar (rojo, azul). Edita los
  thresholds HSV en `render_calibrator.py` (`_H_MIN`, `_H_MAX`,
  `_S_MIN`, `_V_MIN`).
- Resolución del render muy baja (< 800 px). Regenera con
  `--width 1800 --height 900` en `kicad-cli pcb render`.

El sanity check aborta con un mensaje claro si la calibración falla.

### El módulo no aparece

- Verifica que `visible_layer` coincida con el lado del render
  (`F.Cu` para top, `B.Cu` para bottom).
- Verifica que `anchor_ref` exista en el `.kicad_pcb` (si no, aparece
  en `skipped: …`).
- Verifica que `image:` apunte a un fichero existente (si no, se usa
  mockup procedural — debería ser visible pero como un rectángulo
  coloreado con el nombre, no como foto real).

### Las anotaciones se solapan con los módulos

- Usa `--annotations pcb,anchors,holes,pins` para quitar las module
  bboxes (suelen ser la fuente principal de clutter).
- O sube el margen de las cotas editando `_annotate_*` en
  `annotations.py` (los offsets en mm: `y0 - 6.0`, `y1 + 4.0`, etc).

### Quiero generar solo el realista, sin cotas

```bash
python3 -m pcb_designer.render_overlay.cli --version v0.1.0-battery-power --no-annotations
```

### El render bottom se ve raro (texto invertido)

Es correcto: en la vista trasera, los logos y serigrafía aparecen como
si miraras la PCB por detrás (espejados). Si quisieras texto legible
hay que usar la vista TOP.

---

## Convenciones de orientación KiCad

Para que la herramienta funcione, asume estas convenciones del proyecto:

- **Eje +X** hacia la derecha del board.
- **Eje +Y** hacia abajo del board.
- **Rotación PCB en el `.kicad_pcb`**: CW positivo cuando se mira el
  board desde arriba (verificado empíricamente con U4 a rot=90).
- **Footprints de pin headers 1×N**: pin 1 en el origen, pads van a lo
  largo de +Y por defecto (rot=0).
- **PIL rotation**: CCW positivo, igual que matemática estándar. El
  script invierte el signo internamente.

Si tu proyecto usa otras convenciones, edita las funciones de rotación
en `compositor.py` (`_compute_image_center_mm`) y `module_overlay.py`
(`render_module`) — ambos en este mismo directorio.

---

## Limitaciones conocidas

1. **Fotos isométricas vs cenitales**: el sistema asume top-down. Si
   subes una foto en perspectiva el módulo aparecerá distorsionado.

2. **Auto-mask de fondo asume estudio limpio**: si la foto tiene
   sombras complejas o fondos no uniformes, conviene preprocesar
   manualmente añadiendo canal alpha.

3. **`LEFT_ANCHOR_INNER_X` / `RIGHT_ANCHOR_INNER_X` son constantes en
   `annotations.py`** (mismo directorio): si el proyecto cambia de
   convención de anchors, hay que editar esos dos números (o
   promoverlos a `examples/<board>.yaml` en una iteración futura).

4. **Sin NumPy → performance limitada en imágenes muy grandes**: el
   auto-mask itera píxel a píxel en Python puro. Para imágenes de
   > 2000×2000 se nota; reescribir con NumPy daría 10-100×.

5. **Render bottom siempre espeja**: no hay opción de "render bottom
   sin mirror" (correspondería a una vista interior poco común).

6. **Solo un módulo por footprint**: no soporta "stackup" de varios
   breakouts apilados sobre el mismo socket (uso real: poner un radio
   sobre un breadboard). Hay que crear footprints separados o tratar
   manualmente.

7. **Las anotaciones de mounting holes asumen patrones 1×N o 2×2** en
   cada anchor: si hay otra distribución (e.g., 3 holes en triángulo)
   las cotas pueden quedar raras. Editar `_annotate_mounting_holes` si
   se da el caso.
