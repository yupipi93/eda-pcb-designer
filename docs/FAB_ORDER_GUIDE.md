# FAB_ORDER_GUIDE.md — Pedido v0.1.0 a JLCPCB + LCSC (envío combinado a España)

> **Nota (repo standalone)**: esta guía documenta un pedido REAL del board
> MT1 v0.1.0 en JLCPCB (con combined shipping LCSC). La mecánica —
> exportación de gerbers/drill, settings de quote, aduanas IOSS — se
> generaliza a cualquier board de 2 capas; los part numbers y cantidades
> son del ejemplo MT1.

> **Objetivo**: tener las 5 PCBs MT1 v0.1.0 + todos los componentes
> (los del BOM v0.1.0 + un stock de pasivos para futuros proyectos)
> entregadas en tu casa por **~€30-45 totales** sin sorpresas de
> aduana.

**Estrategia**: pedir PCBs en **JLCPCB** primero (sin pagar envío
todavía), luego pedir componentes en **LCSC** marcando *"Combine with
JLCPCB order"*. Las dos empresas son hermanas (mismo grupo SZLCSC) —
consolidan ambos pedidos en una sola caja y te ahorras un envío
internacional entero.

**Plazo total estimado**: 10-15 días a Madrid.

---

## Pre-flight: lo que necesitas tener listo antes de empezar

- [ ] **Cuentas creadas** en ambas plataformas (con el mismo email):
      - JLCPCB: https://passport.jlcpcb.com/register
      - LCSC: https://lcsc.com/register
- [ ] **Tarjeta o PayPal** configurada en ambas.
- [ ] **Dirección de envío Spain** confirmada en ambas cuentas.
- [ ] **Gerbers + drill** generados (ver §1).
- [ ] **30-45 min** de tiempo para hacer el pedido sin prisas.

---

## §1 — Generar los gerbers del PCB

Los gerbers se almacenan dentro del proyecto en
`projects/mt1/releases/v0.1.0/`, siguiendo la convención
documentada en `DESIGN_STATE.md §6`. El directorio `fab/` está en
`.gitignore` por defecto (no se versionan binarios fab regenerables),
salvo que decidas commitear el `README.md` de la release.

```bash
# Desde la raíz del repo:
cd projects/mt1/kicad

# 1) Crear el directorio para esta versión
mkdir -p fab/v0.1.0/gerbers

# 2) Exportar SOLO las capas que JLCPCB necesita (sin Fab/Courtyard/
#    User_* que añaden ruido al review). --subtract-soldermask hace
#    que el silk no se imprima sobre los pads expuestos.
kicad-cli pcb export gerbers mt1-pcb/mt1-pcb.kicad_pcb \
    --output fab/v0.1.0/gerbers/ \
    --layers F.Cu,B.Cu,F.Mask,B.Mask,F.Silkscreen,B.Silkscreen,F.Paste,B.Paste,Edge.Cuts \
    --no-protel-ext \
    --subtract-soldermask

# 3) Exportar los drills (PTH metalizados + NPTH no metalizados como
#    ficheros separados, que es lo que JLCPCB recomienda):
kicad-cli pcb export drill mt1-pcb/mt1-pcb.kicad_pcb \
    --output fab/v0.1.0/gerbers/ \
    --excellon-separate-th

# 4) Comprimir en un único ZIP (lo que JLCPCB pide al subir):
cd fab/v0.1.0
(cd gerbers && zip ../mt1-v0.1.0.zip *)
ls -la mt1-v0.1.0.zip
# → ~70 KB típico

# El ZIP queda en projects/mt1/releases/v0.1.0/mt1-v0.1.0.zip
```

El ZIP debe contener exactamente estos **12 ficheros** (nada más,
nada menos — si ves capas tipo `*_Courtyard.gbr` o `*_Fab.gbr`,
algo se ha colado):

| Archivo | Capa | Tamaño típico |
|---|---|---|
| `mt1-pcb-F_Cu.gbr` | Front Copper | ~9 KB |
| `mt1-pcb-B_Cu.gbr` | Back Copper (incluye plano GND) | ~88 KB |
| `mt1-pcb-F_Mask.gbr` | Front solder mask | ~4 KB |
| `mt1-pcb-B_Mask.gbr` | Back solder mask | ~3 KB |
| `mt1-pcb-F_Silkscreen.gbr` | Front silkscreen blanco | ~44 KB |
| `mt1-pcb-B_Silkscreen.gbr` | Back silkscreen ("Made on Earth") | ~16 KB |
| `mt1-pcb-F_Paste.gbr` | Front solder paste (para stencil opcional) | ~1.5 KB |
| `mt1-pcb-B_Paste.gbr` | Back solder paste | ~0.5 KB |
| `mt1-pcb-Edge_Cuts.gbr` | **Outline del PCB** (crítico) | ~0.6 KB |
| `mt1-pcb-PTH.drl` | Drills metalizados (Excellon) | ~1.7 KB |
| `mt1-pcb-NPTH.drl` | Drills NO metalizados (mounting holes M2) | ~0.3 KB |
| `mt1-pcb-job.gbrjob` | Metadata (opcional pero JLCPCB lo respeta) | ~3 KB |

> **No subas el `.kicad_pcb` directamente a JLCPCB** — aunque lo
> acepta, los gerbers exportados por ti son la fuente canónica y
> dejan trazabilidad clara de qué se pidió.

### Verificación rápida antes de subir (opcional pero recomendado)

Si quieres revisar visualmente los gerbers antes de subir, puedes
usar el viewer online de gerber sin instalar nada:
**https://tracespace.io/view/** — arrastra el `mt1-v0.1.0.zip` y
deberías ver el board renderizado por capas. Confirma que:

- El outline rectangular 100×30 mm aparece completo.
- Los 6 mounting holes están como NPTH (sin cobre alrededor).
- El plano GND en B.Cu se ve continuo.
- El silk "MT1 v0.1.0 - MultitecUA" se lee correctamente.

---

## §2 — Pedir el PCB en JLCPCB

> ⚠️ **AVISO CRÍTICO para combinar shipping con LCSC** (aprendido por
> las malas en el pedido v0.1.0):
>
> El combine LCSC+JLCPCB **NO** funciona enviando ambos pedidos a tu
> dirección real. Funciona enviando JLCPCB al **warehouse de LCSC en
> Hong Kong**, donde LCSC consolida + reexpide a tu casa.
>
> Si configuras JLCPCB con tu dirección real (España) y pagas, **el
> combine YA NO es posible** — y JLCPCB normalmente no permite cambiar
> dirección post-pago (*"there will be no option to modify it after
> checkout"*). Acabas pagando los dos envíos por separado (~€7-12 de
> sobrecoste).
>
> **Antes de pagar JLCPCB, lee este FAQ COMPLETO**:
> https://www.lcsc.com/faqs/notice/combine-lcsc-jlcpcb-orders
>
> **Dirección que JLCPCB debe usar para combine** (sustituye TU
> dirección por esta):
>
> ```
> Recipient: <tu nombre>
> Phone: (+852) 36112905
> Country/Region: Hong Kong, China
> State: NT
> City: KWAI CHUNG
> Street: NOS.35/41 TAI LIN PAI ROAD
> Building: FTB1 2/F Gold Base IND. BLDG.
> Postal: 999077
> ```
>
> El destino real (tu casa en España) lo configuras SOLO en LCSC. LCSC
> al hacer checkout detecta automáticamente tu pedido JLCPCB con esa
> dirección de warehouse y ofrece el combine.

### 2.1 Abre el cotizador

https://jlcpcb.com/quote → **"Add gerber file"** → sube
`/tmp/mt1-v0.1.0-gerbers/mt1-v0.1.0.zip`.

JLCPCB autodetecta dimensiones y muestra una vista previa del board.
**Verifica que se ve el contorno completo de 100×30 mm con los 6
mounting holes**. Si la preview se ve cortada o sin agujeros, revisa
el ZIP (probablemente le falta `Edge_Cuts.gbr` o el drill).

### 2.2 Opciones recomendadas

| Campo | Valor recomendado | Notas |
|---|---|---|
| **Base material** | FR-4 | Por defecto |
| **Layers** | **2** | — |
| **Dimensions** | 100 × 30 mm | Autodetectado |
| **PCB Qty** | **5** | Mínimo del fab, no se ahorra pidiendo menos |
| **Product type** | Industrial/Consumer electronics | — |
| **Different Design** | 1 | — |
| **Delivery format** | Single PCB | (no panelizado) |
| **PCB Thickness** | **1.6 mm** | Standard |
| **PCB Color** | **Green** | El más rápido (otros colores añaden 1-2 días) |
| **Silkscreen** | White | (automático con verde) |
| **Surface Finish** | **HASL (with lead) o HASL Lead-free** | HASL lead-free es ligeramente más caro pero RoHS — recomendado |
| **Outer Copper Weight** | **1 oz** | Standard |
| **Via Covering** | Tented | Por defecto |
| **Board Outline Tolerance** | ±0.2 mm | Por defecto |
| **Confirm Production File** | No | (Sí solo si quieres revisión humana — añade 1 día) |
| **Remove order number** | **No** ($0) o "Specify a location" ($1.5) | "No" es gratis y solo añaden un pequeño número en silk discreto |
| **Flying Probe Test** | Fully test | Por defecto |
| **Gold fingers** | No | — |
| **Castellated Holes** | No | — |
| **Mark on PCB** | None | — |
| **Edge Plating** | No | — |
| **Halfcut/Tail-cut/Slot** | No | — |
| **Material Detail** | Standard FR-4 TG155 | Por defecto, suficiente |
| **PCB Assembly (PCBA)** | **OFF (No)** | Vamos a soldar nosotros |

### 2.3 Importante para España

Antes de añadir al carrito, abajo a la derecha hay un cuadro con
"Calculate shipping". Selecciona:

- **Country/Region**: **Spain**
- **Shipping Method**: "Global Standard Direct Line" o similar.

Click **"Save to Cart"**. Verás tu PCB en el shopping cart con un
identificador tipo `Y2-XXXXXXXXX` debajo (e.g. `Y2-12652754A`).

> ⚠️ **Ese `Y2-…` NO es el order number** — es el "PCB prototype
> code" que identifica el diseño del PCB en el catálogo de JLCPCB.
> El order number (formato `JLCYYYYMMDDXXX`) se crea **DESPUÉS de
> pagar**, no antes. JLCPCB no tiene un estado intermedio
> "submitted-but-unpaid" como otras tiendas.

### 2.4 Estrategia para el envío combinado con LCSC

Como JLCPCB asigna el order number sólo al cobrar, tienes dos
caminos. Recomendado **Estrategia A**:

#### Estrategia A — Pagas JLCPCB primero, LCSC inmediatamente después

1. En el carrito de JLCPCB, **marca el checkbox del item** (si está
   sin marcar verás Subtotal €0.00 — bug clásico de la UI).
2. Click **Secure Checkout** → confirma shipping address Spain
   (IOSS auto-activado) → elige Global Standard Direct Line.
3. En **"Order Notes"** o **"Remark"** (último paso antes de pagar)
   escribe literalmente:

   > `Please hold for combined shipping with my upcoming LCSC
   > order — same delivery address`

4. **Paga** con tarjeta o PayPal.
5. JLCPCB responde con **"Order placed successfully!"** y te
   muestra el **Order Number `JLCYYYYMMDDXXX`** (también te llega
   por email — guárdalo).
6. **Inmediatamente** (idealmente < 2 h después) ve a LCSC (§3) y
   haz tu pedido marcando *"Combine with JLCPCB order"* + pegas ese
   número.

JLCPCB suele tardar 24-48 h en empezar producción tras el pago;
durante esa ventana el sistema detecta tu pedido LCSC y retiene el
envío para consolidar.

#### Estrategia B — Fallback si LCSC no detecta combine

Si en LCSC checkout NO aparece el checkbox "Combine with JLCPCB":

1. Paga LCSC normalmente (con envío individual).
2. Abre el chat de LCSC (esquina inferior derecha en lcsc.com) y
   escribe:

   > `Hi, please combine my LCSC order #LCSCXXXXX with my JLCPCB
   > order #JLCYYYYMMDDXXX, same shipping address. Refund the LCSC
   > shipping cost difference please.`

3. Soporte responde en minutos, combinan manualmente y te devuelven
   el shipping de LCSC.

### 2.5 Coste esperado JLCPCB

| Concepto | Precio típico |
|---|---|
| 5× PCB 100×30 mm 2-layer | **$2.00** (promo primer pedido) o ~$7 estándar |
| Envío "Global Standard Direct Line" a ES | $5-8 |
| IVA español 21% (IOSS) | $0.50-1.50 |
| **Subtotal JLCPCB** | **~$8-15 USD** (≈ €7-14) |

### 2.4 Coste esperado JLCPCB

| Concepto | Precio típico |
|---|---|
| 5× PCB 100×30 mm 2-layer | **$2.00** (promo primer pedido) o ~$7 estándar |
| Envío "Global Standard Direct Line" a ES | $5-8 |
| IVA español 21% (IOSS) | $0.50-1.50 |
| **Subtotal JLCPCB** | **~$8-15 USD** (≈ €7-14) |

---

## §3 — Pedir componentes en LCSC con envío combinado

### 3.1 Configurar la cuenta

Antes de empezar a llenar el carrito, asegúrate de que LCSC sabe que
tienes una orden en JLCPCB:

1. Login en https://lcsc.com.
2. Tu nombre arriba a la derecha → **My Account** → **My Address** →
   confirma que la dirección de envío es la misma que pusiste en
   JLCPCB.

### 3.2 Añade los componentes del BOM MT1 v0.1.0

La lista exacta para fabricar tu PCB v0.1.0 (extraída de
`BUYING.md §1.1`). Busca cada **LCSC P/N** en la barra de búsqueda y
añade al carrito con la cantidad indicada:

| Ref MT1 | LCSC P/N  | Descripción                                       | Footprint  | Cant. | € unit | € total |
|---------|-----------|---------------------------------------------------|------------|-------|--------|---------|
| `J1`    | **C146049** | JST-PH S2B-PH-K, 2-pin horizontal 2.0 mm        | THT        | 2     | 0.10   | 0.20    |
| `SW1`   | **C133260** | Slide SPDT CK OS102011MS2Q 2.54 mm pitch         | THT        | 2     | 0.30   | 0.60    |
| `J2`,`J5` | **C124378** | Pin header 1×2 2.54 mm vertical (macho)        | THT        | 5     | 0.05   | 0.25    |
| `R3`,`R4` | **C17407**  | Resistor 100 kΩ 0805 1%                         | 0805       | 50    | 0.005  | 0.25    |
| `C8`    | **C49678**  | Capacitor 100 nF 50V X7R 0805                     | 0805       | 50    | 0.01   | 0.50    |
| sockets | **C124388** | Pin-header **hembra** 1×40 strip 2.54 mm (para U1, U5, U2, U3, U4) | THT        | 3 strips | 0.40 | 1.20    |
| **BOM total** |       |                                                   |            |       |        | **~3 €**|

> Las cantidades incluyen **margen de prototipado ×5** (se te caerá
> alguno con las pinzas, especialmente al soldar 0805). El BOM real
> mínimo es 1×J1 + 1×SW1 + 2×J2/J5 + 2×R3/R4 + 1×C8 + 48 pines
> sockets — pero no merece la pena pedir cantidades exactas porque
> los pasivos vienen en reel completo.

### 3.3 Aprovecha el envío: pasivos + miscelánea para tu stock

Como ya pagas el envío con JLCPCB, **es buen momento para hacer
stock** de pasivos comunes que vas a usar en cualquier proyecto
futuro (Arduino, ESP32, drones, etc.). Estos son los que más se usan
en electrónica embebida y siguen tu propia regla **0805 mínimo**
(`CONVENTIONS.md §4.1`):

#### Resistencias 0805 1% (reels de 100, ~$0.30-0.50 por reel)

Valores que necesitarás SIEMPRE — la "biblia E12 reducida":

| Valor   | Para qué se usa típicamente                                | LCSC P/N indicativo | Cant. | € total approx |
|---------|------------------------------------------------------------|---------------------|-------|----------------|
| **0 Ω**  | Jumpers / puentes / opciones de configuración              | C17477              | 100   | 0.30           |
| **100 Ω**| Limitadores LED (a 5V, ~20-30 mA)                          | C17414              | 100   | 0.30           |
| **220 Ω**| Limitadores LED (a 5V, ~13 mA)                             | C17561              | 100   | 0.30           |
| **330 Ω**| Limitadores LED (a 3V3, ~5 mA) — ya en BUYING para R1/R2   | C17630              | 100   | 0.30           |
| **470 Ω**| LED amarillo/azul/blanco a 3V3                             | C17675              | 100   | 0.30           |
| **1 kΩ** | Pull-up base, divisor genérico, base BJT                   | C17513              | 100   | 0.30           |
| **2.2 kΩ**| I²C pull-up a 3V3 (en buses internos sin pull-up)         | C17520              | 100   | 0.30           |
| **4.7 kΩ**| **I²C pull-up estándar** (en breakouts sin pull-up)       | C17673              | 100   | 0.30           |
| **10 kΩ**| **Pull-up genérico** — el más usado en general             | C17414 _(VERIFICAR)_| 100   | 0.30           |
| **22 kΩ**| Divisor genérico                                           | C18272              | 100   | 0.30           |
| **47 kΩ**| Divisor genérico, pull-down sleep mode                     | C18298              | 100   | 0.30           |
| **100 kΩ**| **YA EN BOM** (R3, R4) — pedir 50 extra de stock          | C17407              | (50 ya)| —             |
| **1 MΩ** | Reset RC, pull-up de muy baja corriente                    | C18043              | 50    | 0.20           |
| **Subtotal resistencias** | | | | **~€4-5** |

> Los P/N C-xxxx son indicativos. Antes de añadir al carrito,
> **verifica en LCSC** que el package es `0805`, la tolerancia es `1%`
> (F, no J) y que está en stock (no "Pre-Order"). El buscador acepta
> filtros como `Resistor 0805 1% 10k F` para acotar rápido.

#### Condensadores 0805 cerámicos X7R/X5R (reels de 50, ~$0.30-1 por reel)

| Valor   | Tipo     | Para qué                                          | LCSC P/N | Cant. | € total |
|---------|----------|---------------------------------------------------|----------|-------|---------|
| **100 pF**| C0G     | Filtros HF, crystals load (junto con la frecuencia adecuada) | C36905   | 50    | 0.40    |
| **1 nF** | X7R      | Filtros LP, debounce alto                          | C28233   | 50    | 0.40    |
| **10 nF**| X7R      | Filtros LP, anti-aliasing antes de ADC             | C57112   | 50    | 0.40    |
| **100 nF**| X7R     | **DECOUPLING UNIVERSAL** — el cap más útil. Ya en BOM (C8) — pedir 100 extra | C49678 | (50 ya, +100)| 0.50  |
| **1 µF** | X7R      | Bulk decoupling local, filtros RC                  | C28323   | 50    | 0.50    |
| **10 µF**| X5R      | **Bulk power supply** — el segundo más útil       | C15850   | 50    | 1.00    |
| **22 µF**| X5R      | Bulk batería, LDO output                           | C45783   | 25    | 0.80    |
| **Subtotal condensadores** | | | | | **~€4** |

#### LEDs 0805 (5-10 por color, ~$0.50/color)

Reservas básicas para indicadores de estado:

| Color   | Para qué                                                  | LCSC P/N | Cant. | € total |
|---------|-----------------------------------------------------------|----------|-------|---------|
| Rojo    | Estado "error", "logging activo"                          | C84257   | 10    | 0.50    |
| Verde   | Estado "OK", "heartbeat"                                  | C84256   | 10    | 0.50    |
| Amarillo| Estado "warning", "esperando"                             | C84268   | 10    | 0.30    |
| Azul    | Indicador WiFi/BLE activo                                 | C84260   | 10    | 0.50    |
| Blanco  | Iluminación / debug                                        | C84268 _(VERIFICAR)_ | 5 | 0.30 |
| **Subtotal LEDs** | | | | **~€2** |

#### Pulsadores

| Tipo                          | Para qué                                | LCSC P/N | Cant. | € total |
|-------------------------------|-----------------------------------------|----------|-------|---------|
| **Tactile SMD 6×6×5 mm 4-pin**| Botones de PCB (BTN1/BTN2 futuros)      | C318884  | 10    | 1.20    |
| Tactile SMD 4×4×1.5 mm 2-pin  | Botones pequeños (reset interno)        | C720478  | 5     | 0.40    |
| Tactile THT 6×6 mm 4-pin      | Prototipo en breadboard                 | C127509  | 10    | 1.00    |
| **Subtotal pulsadores** | | | | **~€2.60** |

#### Pin headers + sockets (THT)

| Item                                          | Para qué                                       | LCSC P/N | Cant.    | € total |
|-----------------------------------------------|------------------------------------------------|----------|----------|---------|
| Pin header **macho** 1×40 strip 2.54 mm     | Cortar a medida para cualquier conector futuro | C124378  | 5 strips | 0.50    |
| Pin header **hembra** 1×40 strip 2.54 mm    | Sockets para módulos enchufables (ya en BOM)   | C124388  | (3 ya)   | —       |
| Pin header **macho** 2×40 strip 2.54 mm     | Conectores dual-row, IDC                        | C124379  | 3 strips | 0.60    |
| Pin header **macho ángulo recto** 1×40 2.54 mm | Conectores que salen lateralmente al PCB     | C50982   | 3 strips | 0.50    |
| **Subtotal pin headers** | | | | **~€1.60** |

#### Conectores especializados (los más útiles)

| Item                                          | Para qué                                   | LCSC P/N | Cant. | € total |
|-----------------------------------------------|--------------------------------------------|----------|-------|---------|
| JST-PH 2.0 mm 2-pin **vertical** (S2B-PH-K-V)| LiPo 1S en PCB (ya en BOM J1 es horizontal — la vertical es para otros casos) | C144394 | 5 | 0.40 |
| JST-PH 2.0 mm 3-pin horizontal               | Encoders, sensores con alimentación        | C146052 | 5 | 0.40 |
| JST-PH 2.0 mm 4-pin horizontal               | I²C breakout cables (3V3+GND+SDA+SCL)      | C146054 | 5 | 0.50 |
| JST-XH 2.5 mm 2-pin (para LiPos más grandes) | Baterías 2S/3S de aeromodelismo            | C2828   | 5 | 0.50 |
| Screw terminal 5.08 mm 2-pin                 | Conexión de cables gruesos sin connector   | C8270   | 3 | 0.60 |
| Bornier KF301-2P horizontal                  | Conexión robusta (motores, alimentación)   | C8270 _(verificar)_ | 3 | 0.60 |
| **Subtotal conectores especializados** | | | | **~€3** |

#### Cables y consumibles (a menudo se olvidan)

| Item                                          | Para qué                                   | LCSC P/N | Cant.   | € total |
|-----------------------------------------------|--------------------------------------------|----------|---------|---------|
| Cable jumper Dupont **hembra-hembra** 20 cm (40 hilos color) | Prototipado / hand-wiring J5 a XIAO | C50983 _(verificar)_ | 1 kit | 2-3 |
| **Subtotal cables LCSC** | | | | **~€3** |

> **Cable JST-PH 2-pin 20 cm con conector hembra ya soldado** (que
> estaba originalmente listado aquí): el catálogo de LCSC tiene MUY
> POCAS cable assemblies pre-armadas y suelen ser caras. La LiPo
> 602535 que ya tienes incluye su propio cable JST-PH 2-pin hembra
> de fábrica — **no necesitas el cable extra para el bringup
> normal**. Si quieres spares (cable de repuesto, pigtails para
> bench supply), **pídelos en Amazon España** — packs de 10 cables
> por ~€5-8, entrega en 2-3 días, mucho mejor experiencia que LCSC
> para este artículo concreto.

#### Semiconductores básicos (opcionales pero muy útiles)

| Item                                          | Para qué                                   | LCSC P/N | Cant. | € total |
|-----------------------------------------------|--------------------------------------------|----------|-------|---------|
| Schottky diode SS14 SMA (1A/40V)             | Protección polaridad inversa, free-wheel   | C8678    | 10    | 0.50    |
| Signal diode 1N4148WS SOD-323                 | Lógica, clamp                              | C81598   | 20    | 0.30    |
| MOSFET N AO3400 SOT-23 (30V/5A)              | High-side/low-side switch, level shifter   | C20917   | 10    | 1.00    |
| MOSFET P AO3401 SOT-23 (30V/4A)              | Reverse-polarity protection alta-corriente | C15127   | 10    | 1.20    |
| LDO 3.3V AMS1117-3.3 SOT-223                 | Regulación para circuitos sin XIAO         | C6186    | 5     | 0.40    |
| **Subtotal semiconductores** | | | | **~€3.40** |

#### Total estimado del stock-up

| Bloque | € approx |
|---|---|
| BOM v0.1.0 (obligatorio) | 3.00 |
| Resistencias 0805 | 4-5 |
| Condensadores 0805 | 4 |
| LEDs 0805 | 2 |
| Pulsadores | 2.60 |
| Pin headers | 1.60 |
| Conectores | 3 |
| Cables | 4 |
| Semiconductores | 3.40 |
| **TOTAL LCSC componentes (antes de envío/IVA)** | **~€28** |

> Sube fácilmente a €30-50 si añades algún módulo grande o muchos
> reels extra. Para tu primer pedido, **mantente en lo esencial** y
> compra ampliaciones en pedidos futuros.

### 3.4 Combinar el envío con JLCPCB

Cuando llegues al carrito en LCSC → **Checkout** → en la sección
**"Shipping Method"** debería aparecer una opción tipo:

```
☐ Combine with my JLCPCB order  [JLCYYYYMMDDXXXX]
```

Marca el checkbox y pega el **Order Number** de JLCPCB del paso 2.3.

LCSC confirmará "Your order will be combined with JLCPCB #JLCXXX,
shipping cost: $0.00".

Si por algún motivo el checkbox **no aparece** automáticamente:
- Verifica que tu pedido JLCPCB está en estado "Submitted" o "In
  Production" (no "Shipped").
- Abre el chat de LCSC (abajo derecha) y pide manualmente: *"Please
  combine my LCSC cart with JLCPCB order #JLCXXX, same shipping
  address"*. Responden en minutos en horario asiático.

### 3.5 Confirmar IOSS para España

En el checkout de LCSC, en **"Tax & Customs"**:
- Verifica que aparece **"IOSS"** o **"VAT included for EU"** con el
  IVA español 21% ya añadido.
- Si NO aparece: cambia el shipping country a Spain explícitamente
  (no "España" en español ni acentos raros).

### 3.6 Pago

Tarjeta o PayPal. LCSC tira directo sin redirecciones.

---

## §4 — Verificar el envío combinado

Si seguiste la Estrategia A (§2.4), JLCPCB ya está pagado y LCSC ha
detectado el combine en su checkout. Ve a:

- **JLCPCB → My Orders → tu pedido**: verifica que en "Order Notes"
  aparece tu mensaje de hold-for-combined-shipping. Estado debería ser
  "Pending Review" o "In Production".
- **LCSC → My Orders → tu pedido**: verifica que dice "Combined with
  JLCPCB #JLCXXX" y shipping cost = $0.00.

Si algo no cuadra (LCSC ya muestra "shipped" antes que JLCPCB, o
JLCPCB despachó sin esperar), usa la Estrategia B (§2.4) abriendo el
chat de LCSC para reclamar el reembolso del envío individual.

---

## §5 — Seguimiento del pedido

**Te llegan DOS tracking numbers** (uno por web), pero al final es
**una sola caja**:

1. JLCPCB tracking: aparece en `My Orders` → tu pedido → "Tracking
   Info" cuando se manda.
2. LCSC tracking: aparece en `My Orders` → tu pedido → "Logistics".

Suelen apuntar al mismo trackin de DHL/SF Express/Cainiao.

**Plazo realista a Madrid**:
- Producción JLCPCB: 1-3 días (fast turn) o 5-7 días (standard).
- Consolidación con LCSC en almacén Shenzhen: 1-2 días.
- Envío internacional Shenzhen→ES: 7-12 días (Direct Line) o 3-5
  días (DHL).
- **Total típico**: **10-15 días**.

---

## §6 — Cuando llegue la caja: checklist de recepción

- [ ] Cuenta los PCBs: deben ser **5 unidades** intactas.
- [ ] Inspecciona visualmente las pistas con buena luz — no debe
      haber arañazos profundos ni cortes en las trazas.
- [ ] Confirma silk legible: el título "MT1 v0.1.0 - MultitecUA"
      debe leerse claramente.
- [ ] Comprueba que todos los agujeros M2 están abiertos (no
      taponados con máscara).
- [ ] Multímetro en continuidad: prueba `J1.1 ↔ SW1.1 ↔ J2.1` (todos
      deben pitar). Lo mismo `J5.2 ↔ J1.2 ↔ cualquier pad GND`.
- [ ] Cuenta los componentes contra el packing slip de LCSC —
      especialmente los reels pequeños (LEDs, MOSFETs).
- [ ] Empieza el bringup: soldar primero los sockets (U1, U5, U2,
      U3, U4), después J1+SW1+J2+J5, finalmente R3+R4+C8.

---

## §7 — Resumen de costes esperados

| Concepto | $ USD | € EUR approx |
|---|---|---|
| 5× PCB JLCPCB (con promo $2 primer pedido) | $2 | €1.85 |
| BOM v0.1.0 LCSC | $3 | €2.80 |
| Stock-up SMD adicional (~€28) | $30 | €28 |
| Envío combinado JLCPCB+LCSC a ES | $8 | €7.50 |
| IVA español 21% (IOSS) | $9 | €8.40 |
| **TOTAL aproximado** | **~$52** | **~€48** |

> Sin el stock-up adicional (solo BOM v0.1.0 mínimo): **~€18-22**.

---

## §8 — Tips finales

1. **Hazlo en un solo bloque de tiempo** (no dejes el carrito de
   JLCPCB pendiente 3 días — caduca la posibilidad de combine).
2. **Captura pantalla** del checkout final de cada plataforma antes
   de pagar — útil si hay disputa con aduanas o tienes que reclamar.
3. **Guarda los emails de confirmación** (JLCPCB + LCSC) en una
   carpeta llamada `MT1 v0.1.0 fab` para auditoría futura.
4. **Anota en `BUYING.md §9`** las fechas reales del pedido, los
   tracking numbers y el coste real cuando llegue — para tener
   referencia en futuros pedidos.
5. **No combines más de una orden de JLCPCB con LCSC** (e.g.
   v0.1.0 + v0.2 en el mismo combo) — el sistema solo soporta 1:1.
   Si quieres dos versiones, espera a recibir la primera o paga
   envíos separados.
6. **JLCPCB tiene cupones promocionales** que aparecen en banner
   superior — léelos antes de pagar, a veces hay un código "$5 OFF"
   válido para tu pedido.

---

## §9 — Plantilla para apuntar el pedido real

Rellena esta tabla cuando confirmes el pedido y márcalo en
`BUYING.md §9` también:

| Campo | Valor |
|---|---|
| Fecha pedido JLCPCB | YYYY-MM-DD |
| JLCPCB Order # | JLCYYYYMMDDXXXX |
| Fecha pedido LCSC | YYYY-MM-DD |
| LCSC Order # | LCSCXXXXXXX |
| Total pagado JLCPCB (USD) | $X.XX |
| Total pagado LCSC (USD) | $X.XX |
| Tracking number | XXXXXXXX |
| Fecha de recepción esperada | YYYY-MM-DD |
| Fecha de recepción real | YYYY-MM-DD |
| Estado al recibir | ✅ todo OK / ⚠ algún defecto / ❌ extraviado |
| Notas para próximo pedido | ... |

---

## Anexo A — Si necesitas PCBA en una iteración futura

Cuando estés listo para PCBA (assembly automática de los SMDs por
JLCPCB), prepara estos dos ficheros adicionales:

```bash
cd projects/mt1/kicad/

# BOM con columnas: Designator, Comment, Footprint, LCSC Part #
kicad-cli sch export bom mt1-pcb.kicad_sch \
    --output /tmp/mt1-v0.1.0-bom.csv \
    --fields 'Reference,Value,Footprint,${LCSC_PN}' \
    --format-preset 'JLCPCB' 2>/dev/null \
    || kicad-cli sch export bom mt1-pcb.kicad_sch \
        --output /tmp/mt1-v0.1.0-bom.csv \
        --fields 'Reference,Value,Footprint'

# CPL (centroid) — posiciones X/Y/rotación para pick-and-place
kicad-cli pcb export pos mt1-pcb.kicad_pcb \
    --output /tmp/mt1-v0.1.0-cpl.csv \
    --format csv --units mm
```

> Pero para tu primer pedido v0.1.0 con solo 3 SMDs (R3, R4, C8)
> **no merece la pena** — soldar a mano 3 piezas 0805 con flux es
> trivial y te ahorras los ~$30 extra de setup PCBA.
