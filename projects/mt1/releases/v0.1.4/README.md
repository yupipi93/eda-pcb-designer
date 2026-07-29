# MT1 PCB — Release v0.1.4

**Fecha:** 2026-06-18 · **DRC:** 0 errores · 0 unconnected · **Tests:** 42/42

## Qué cambió respecto a v0.1.3
Se resolvieron los **8 errores DRC** que dejó v0.1.3 al colocar los orificios de montaje
de los módulos:
- `/+3V3` cortada por MH1 (2× `hole_clearance`) → reenrutada (MH1 como keepout).
- Cuerpo de la microSD (orificios MH5/MH6) solapando los pads del IMU U2 (4×
  `solder_mask_bridge` + 2× `npth_inside_courtyard`) → **separación de 7.0 mm en Y** de
  los subsistemas IMU y microSD, conservando los 6 orificios de montaje.
- Pour `/GND` (B.Cu) reconectado con 2 jumpers vía→F.Cu→vía tras el re-ruteo.

Detalle completo en `../../REPORT.md` §11.

## Contenido
| Archivo | Descripción |
|---|---|
| `gerbers/*.g??` | Gerbers RS-274X: F/B Cu, F/B Mask, F/B Silkscreen, F/B Paste, Edge.Cuts |
| `gerbers/mt1-pcb-NPTH.drl` · `-PTH.drl` | Taladros Excellon (mm), NPTH y PTH separados |
| `gerbers/mt1-pcb-job.gbrjob` | Job file de fabricación |
| `mt1-pcb-pos.csv` | Pick & place (ambas caras, mm) |
| `mt1-pcb-bom.csv` | BOM agrupado por valor/footprint |
| `mt1-pcb-v0.1.4.zip` | Paquete completo para el fabricante |

## Verificación
```bash
cd ../../..    # raíz del repo
kicad-cli pcb drc projects/mt1/kicad/mt1-pcb.kicad_pcb --severity-all   # 0 errores
python3 projects/mt1/tools/verify_placement.py                          # exit 0
python3 projects/mt1/tools/verify_holes.py --version v0.1.4             # exit 0
.venv/bin/python -m pytest tests/ -q                                    # 42 passed
```
