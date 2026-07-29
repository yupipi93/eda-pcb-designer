#!/usr/bin/env bash
# Lemon Piano V5.5 — one full iteration through the pcb-designer CLOUD API.
#
#   ./projects/lemon-piano/tools/cloud_pipeline.sh v0.0.3 [--skip-route]
#
# Stages (cloud for everything that has an endpoint — AGENTS.md/mission):
#   build   (local Docker; generative, no endpoint)   -> base .kicad_pcb
#   /place  (cloud)  YAML placements applied           -> placed board
#   /route  (cloud)  freerouting + zone fill           -> routed board
#   post    (local Docker; widths + zone refill, no endpoint)
#   /drc    (cloud)  JSON report  -> validation/drc-<ver>.json
#   /render (cloud)  raytraced    -> renders/<ver>-top.png / -bottom.png
#
# The routed board is left in projects/lemon-piano/kicad/lemon-piano.kicad_pcb
# (in-place, MT1 style) and every artefact is archived under the version tag.
set -euo pipefail

VER="${1:?usage: cloud_pipeline.sh vX.Y.Z [--skip-route]}"
SKIP_ROUTE="${2:-}"
API="https://pcb-designer.scv.multitecua.com"
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
PROJ="$ROOT/projects/lemon-piano"
PCB="$PROJ/kicad/lemon-piano.kicad_pcb"
CFG="$PROJ/lemon-piano.yaml"
IMG=eda-pcb-designer:latest

dk() { docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
        -v "$ROOT":/work -w /work --entrypoint python3 "$IMG" "$@"; }

cd "$ROOT"
mkdir -p "$PROJ/validation" "$PROJ/renders"

echo "== [$VER] build (local docker, generative) =="
dk projects/lemon-piano/tools/build_board.py

echo "== [$VER] cloud /place =="
curl -sf -F "pcb=@$PCB" -F "config=@$CFG" "$API/place" -o "$PCB.placed"
mv "$PCB.placed" "$PCB"

if [ "$SKIP_ROUTE" != "--skip-route" ]; then
  echo "== [$VER] cloud /route =="
  curl -sf -F "pcb=@$PCB" "$API/route?passes=30&optim=5" -o "$PCB.routed" \
    || { echo "ROUTE FAILED"; curl -s -F "pcb=@$PCB" "$API/route?format=json" | head -c 2000; exit 1; }
  mv "$PCB.routed" "$PCB"

  echo "== [$VER] post-route (local docker: widths + zone refill) =="
  dk projects/lemon-piano/tools/post_route.py "projects/lemon-piano/kicad/lemon-piano.kicad_pcb"
fi

echo "== [$VER] cloud /drc =="
curl -sf -F "pcb=@$PCB" "$API/drc" -o "$PROJ/validation/drc-$VER.json"
DRC_OK=1
python3 - "$PROJ/validation/drc-$VER.json" <<'EOF' || DRC_OK=0
import json, sys
d = json.load(open(sys.argv[1]))
rep = d.get("report", d)
v = rep.get("violations", [])
u = rep.get("unconnected_items", [])
sev = {}
for item in v:
    sev[item.get("severity", "?")] = sev.get(item.get("severity", "?"), 0) + 1
print(f"DRC: {len(v)} violations {sev}, {len(u)} unconnected")
for item in v[:12]:
    print(f"  [{item.get('severity')}] {item.get('type')}: {item.get('description', '')[:110]}")
if len(v) > 12:
    print(f"  ... {len(v) - 12} more")
sys.exit(0 if sev.get("error", 0) == 0 and len(u) == 0 else 1)
EOF

echo "== [$VER] cloud /render both =="
curl -sf -F "pcb=@$PCB" "$API/render?side=both" -o "/tmp/renders-$VER.zip"
python3 - "/tmp/renders-$VER.zip" "$PROJ/renders" "$VER" <<'EOF'
import sys, zipfile, shutil, os
zf, outdir, ver = sys.argv[1], sys.argv[2], sys.argv[3]
with zipfile.ZipFile(zf) as z:
    for n in z.namelist():
        side = "top" if "top" in n else "bottom"
        with z.open(n) as src, open(os.path.join(outdir, f"{ver}-{side}.png"), "wb") as dst:
            shutil.copyfileobj(src, dst)
        print("  saved", os.path.join(outdir, f"{ver}-{side}.png"))
EOF

if [ "$DRC_OK" != "1" ]; then
  echo "== [$VER] DRC GATE FAILED (errors or unconnected > 0) — artefacts archived, stopping before fab =="
  exit 1
fi

echo "== [$VER] schematic (local docker, generative) + ERC =="
dk projects/lemon-piano/tools/build_schematic.py
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$ROOT":/work -w /work \
  --entrypoint bash "$IMG" -c '
mkdir -p /tmp/.config/kicad/9.0
{ echo "(sym_lib_table (version 7)"
  for f in /usr/share/kicad/symbols/*.kicad_sym; do
    n=$(basename "$f" .kicad_sym)
    echo " (lib (name \"$n\")(type \"KiCad\")(uri \"$f\")(options \"\")(descr \"\"))"
  done
  echo ")"; } > /tmp/.config/kicad/9.0/sym-lib-table
kicad-cli sch erc --output projects/lemon-piano/validation/erc-'"$VER"'.txt \
  --exit-code-violations projects/lemon-piano/kicad/lemon-piano.kicad_sch' \
  && echo "  ERC clean" || { echo "ERC VIOLATIONS"; exit 1; }

echo "== [$VER] gates: verify_placement + verify_holes + geometry =="
python3 "$PROJ/tools/verify_placement.py" > "$PROJ/validation/verify-placement-$VER.txt" \
  && echo "  verify_placement PASS" || { tail -30 "$PROJ/validation/verify-placement-$VER.txt"; exit 1; }
python3 "$PROJ/tools/verify_holes.py" > "$PROJ/validation/verify-holes-$VER.txt" \
  && echo "  verify_holes PASS" || { cat "$PROJ/validation/verify-holes-$VER.txt"; exit 1; }
python3 "$PROJ/tools/geometry_gate.py" > "$PROJ/validation/geometry-$VER.txt" \
  && echo "  geometry_gate PASS" || { cat "$PROJ/validation/geometry-$VER.txt"; exit 1; }

if [ "${3:-}" = "--fab" ] || [ "$SKIP_ROUTE" = "--fab" ]; then
  echo "== [$VER] cloud /fab =="
  mkdir -p "$PROJ/releases/$VER"
  curl -sf -F "pcb=@$PCB" -F "sch=@$PROJ/kicad/lemon-piano.kicad_sch" \
    "$API/fab?version=$VER" -o "$PROJ/releases/$VER/lemon-piano-$VER-fab.zip"
  unzip -l "$PROJ/releases/$VER/lemon-piano-$VER-fab.zip" | tail -20
fi

echo "== [$VER] done =="
