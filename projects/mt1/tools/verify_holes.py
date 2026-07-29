#!/usr/bin/env python3
"""MT1 mounting-hole (anchor-hole) verification gate.

Runs the three complementary methods of `pcb_designer.verify.holes`:
  G  geométrico  — diseño (.kicad_pcb) vs ground-truth (posición + Ø + patrón)
  V  visión      — centros detectados en el render (afín 6-DOF + leave-one-out)
  D  diff visual — imagen de comprobación por cara + montaje de recortes

Prints a human report (or --json) and exits non-zero if any critical check
fails — wire BEFORE `fab`, alongside verify_placement.py.

Usage:
    python3 projects/mt1/tools/verify_holes.py
    python3 projects/mt1/tools/verify_holes.py --json
    python3 projects/mt1/tools/verify_holes.py --version v0.1.3 --use-base-renders
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from pcb_designer.verify import holes as H  # noqa: E402
from pcb_designer.verify.pins import verify_pin_alignment  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
MT1 = REPO_ROOT / "projects" / "mt1"
DEFAULT_PCB = MT1 / "kicad" / "mt1-pcb.kicad_pcb"
DEFAULT_GT = MT1 / "ground-truth" / "holes.yaml"
DEFAULT_OUT = MT1 / "validation" / "holes"
DEFAULT_MODULES = MT1 / "overlays" / "modules.yaml"
DEFAULT_IMAGES = MT1 / "overlays" / "component-images"


def _render_paths(version: str, use_base: bool) -> dict[str, Path]:
    if use_base:
        return {"top": MT1 / "renders" / f"{version}-top.png",
                "bottom": MT1 / "renders" / f"{version}-bottom.png"}
    return {"top": MT1 / "overlays" / f"{version}-realistic-top.png",
            "bottom": MT1 / "overlays" / f"{version}-realistic-bottom.png"}


def _print_report(rep: dict) -> None:
    line = "=" * 76
    print(line)
    print("  VERIFICACIÓN DE PERFORACIONES DE ANCLAJE — pcb_designer.verify.holes")
    print(line)
    print(f"  Tornillo {rep['screw']} · taladro Ø{rep['drill_dia_mm']} mm · pad Ø{rep['pad_dia_mm']} mm")
    t = rep["tolerances"]
    print(f"  Tolerancias: posición ≤{t['pos_mm']} mm · Ø ≤{t['dia_mm']} mm · visión(LOO) ≤{t['cv_mm']} mm")

    print("\n  G · GEOMÉTRICO (diseño .kicad_pcb vs ground-truth)")
    print("  " + "-" * 72)
    for f in rep["geometric"]:
        tag = "PASS" if f["ok"] else "FAIL"
        print(f"   [{tag}] {f['ref']:<8} {f['message']}")
        if f["detail"]:
            print(f"          ↳ {f['detail']}")

    for side, sd in rep["sides"].items():
        print(f"\n  V · VISIÓN — render {side}")
        print("  " + "-" * 72)
        if "error" in sd:
            print(f"   [SKIP] {sd['error']}")
            continue
        print(f"   calibración {sd['ppm']} px/mm · max residual {sd['max_full_resid_mm']} mm · "
              f"max LOO {sd['max_loo_err_mm']} mm")
        for f in sd["cv_findings"]:
            tag = "PASS" if f["ok"] else "FAIL"
            print(f"   [{tag}] {f['ref']:<8} {f['message']}")
        print(f"   diff:  {sd['diff_image']}")
        print(f"   crops: {sd['crops_image']}")

    if "pins" in rep:
        pr = rep["pins"]
        print(f"\n  P · PINES SOBRE PADS (overlays) — tol perp {pr['tol_mm']} mm")
        print("  " + "-" * 72)
        for m in pr["modules"]:
            tag = "PASS" if m["ok"] else "FAIL"
            rows = " · ".join(
                f"{r['ref']} perp={r['perp_off_mm']:+.3f}{' (lowconf)' if not r['confident'] else ''}"
                for r in m["rows"])
            print(f"   [{tag}] {m['module']:<13} max|perp|={m['max_perp_mm']:.3f} mm   {rows}")
            print(f"          ↳ {m['diff_image']}")

    print("\n" + line)
    holes_ok = rep["pass"]
    pins_ok = rep.get("pins", {}).get("pass", True)
    if holes_ok and pins_ok:
        print("  ✅ PERFORACIONES DE ANCLAJE CORRECTAS (geom+visión) y PINES SOBRE PADS.")
    else:
        msg = []
        if not holes_ok:
            msg.append(f"{rep['geometric_failed']} geom + {rep['cv_failed']} visión (orificios)")
        if not pins_ok:
            msg.append(f"pines: {', '.join(rep['pins']['failed'])}")
        print(f"  ⛔ FALLOS: {' · '.join(msg)}.")
    print(line)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="MT1 mounting-hole verifier")
    ap.add_argument("--version", default="v0.1.3")
    ap.add_argument("--pcb", type=Path, default=DEFAULT_PCB)
    ap.add_argument("--ground-truth", type=Path, default=DEFAULT_GT)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--use-base-renders", action="store_true",
                    help="usar renders/<v>-{top,bottom}.png en vez de los overlays realistas")
    ap.add_argument("--no-pins", action="store_true",
                    help="omitir la verificación de pines sobre pads (overlays)")
    ap.add_argument("--pin-tol-mm", type=float, default=0.15)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if not args.pcb.exists():
        print(f"ERROR: PCB no encontrada: {args.pcb}", file=sys.stderr)
        return 2
    if not args.ground_truth.exists():
        print(f"ERROR: ground-truth no encontrada: {args.ground_truth}", file=sys.stderr)
        return 2

    renders = _render_paths(args.version, args.use_base_renders)
    rep = H.verify_holes(args.pcb, args.ground_truth, renders, args.out_dir)

    # Pin-on-pad verification runs on the realistic overlays (need the photos).
    if not args.no_pins:
        overlays = _render_paths(args.version, use_base=False)
        if DEFAULT_MODULES.exists():
            rep["pins"] = verify_pin_alignment(
                args.pcb, DEFAULT_MODULES, DEFAULT_IMAGES, overlays,
                MT1 / "validation" / "pins", tol_mm=args.pin_tol_mm)

    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        _print_report(rep)

    pins_ok = rep.get("pins", {}).get("pass", True)
    return 0 if (rep["pass"] and pins_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
