"""The four physical-placement checks (C1–C4).

Each maps 1-to-1 to a known MT1 failure (POST-MORTEM-001):
  C1 chirality        → XIAO column-swap mirror   (multi-column parts)
  C2 flip_integrity   → fake flip_to_back on B.Cu (any back-side footprint)
  C3 pad_net_function → BMP585 SDA/SDO swap       (net on wrong physical pin)
  C4 net_intent       → bus touches the wrong set of pads (safety net)

All checks are read-only and return `Finding` records (ok=True/False).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from .pinmap import Footprint

__all__ = ["Finding", "GroundTruth", "load_ground_truth", "run_all",
           "check_pad_net_function", "check_chirality",
           "check_flip_integrity", "check_pin1_orientation", "check_net_intent"]


@dataclass
class Finding:
    check: str          # "chirality" | "flip_integrity" | "pad_net_function" | "net_intent"
    component: str
    ok: bool
    message: str
    severity: str = "critical"   # critical | warning | info
    detail: str = ""


@dataclass
class GroundTruth:
    components: dict
    key_nets: list

    def pin(self, ref: str, pad: str) -> dict | None:
        for comp in self.components.values():
            p = comp.get("pins", {}).get(f"{ref}.{pad}")
            if p is not None:
                return p
        return None


def load_ground_truth(path: str | Path) -> GroundTruth:
    data = yaml.safe_load(Path(path).read_text())
    return GroundTruth(
        components=data.get("components", {}),
        key_nets=data.get("key_nets", []),
    )


def _signed_area(a, b, c) -> float:
    """z-component of the cross product (b-a)x(c-a) — signed triangle area*2."""
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _sign(v: float) -> int:
    return 1 if v > 1e-9 else (-1 if v < -1e-9 else 0)


def _norm(net):
    """Normalize a ground-truth net value (None / 'null' / '' → None)."""
    if net in (None, "null", ""):
        return None
    return net


# ── C3: pad → net → physical function ────────────────────────────────────
def check_pad_net_function(board: dict[str, Footprint], gt: GroundTruth) -> list[Finding]:
    findings: list[Finding] = []
    for cname, comp in gt.components.items():
        mism = []
        for key, spec in comp.get("pins", {}).items():
            ref, pad = key.split(".")
            fp = board.get(ref)
            if fp is None:
                mism.append(f"{key}: footprint ausente en el board")
                continue
            p = fp.pads.get(pad)
            actual = p.net_name if p else "<pad ausente>"
            expected = _norm(spec.get("net"))
            if (actual or None) != (expected or None):
                mism.append(
                    f"{key} (pin físico {spec.get('func')}): "
                    f"net esperado {expected!r} pero el pad lleva {actual!r}"
                )
        ok = not mism
        findings.append(Finding(
            check="pad_net_function", component=cname, ok=ok,
            message="cada pad lleva el net de su pin físico"
            if ok else f"{len(mism)} pad(s) con net en el pin equivocado",
            detail="\n".join(mism),
        ))
    return findings


# ── C1: chirality (mirror) ───────────────────────────────────────────────
def check_chirality(board: dict[str, Footprint], gt: GroundTruth) -> list[Finding]:
    findings: list[Finding] = []
    for cname, comp in gt.components.items():
        triad = comp.get("chirality_triad")
        if not triad or len(triad) < 3:
            continue  # single-column / collinear parts: chirality undefined
        # canonical signed area (part-local frame, +Y up)
        cano = [t["xy"] for t in triad[:3]]
        cano_sign = _sign(_signed_area(cano[0], cano[1], cano[2]))

        # board signed area from real global pad positions
        pts = []
        missing = []
        for t in triad[:3]:
            ref, pad = t["at"].split(".")
            fp = board.get(ref)
            g = fp.global_pad(pad) if fp else None
            if g is None:
                missing.append(t["at"])
            else:
                pts.append(g)
        if missing:
            findings.append(Finding(
                check="chirality", component=cname, ok=False,
                message=f"no se pudo localizar {missing} para medir quiralidad",
            ))
            continue
        board_sign = _sign(_signed_area(*pts))

        # Expected board sign: KiCad is +Y-down vs canonical +Y-up → one flip
        # for a top-mounted part; a bottom-mounted part adds an X flip.
        side = comp.get("mount_side", "top")
        expected_sign = -cano_sign if side == "top" else cano_sign

        ok = (board_sign == expected_sign)
        funcs = " , ".join(f"{t['func']}" for t in triad[:3])
        findings.append(Finding(
            check="chirality", component=cname, ok=ok,
            message="quiralidad correcta (no espejada)"
            if ok else "ESPEJADO: la disposición de pines es la imagen especular del componente físico",
            detail=(f"tríada [{funcs}] · mount={side} · "
                    f"signo board={board_sign:+d} esperado={expected_sign:+d}"
                    + ("" if ok else " → las columnas/lados están intercambiados")),
        ))
    return findings


# ── C2: flip integrity (real flip vs fake layer-swap) ────────────────────
def check_flip_integrity(board: dict[str, Footprint], gt: GroundTruth) -> list[Finding]:
    findings: list[Finding] = []
    for cname, comp in gt.components.items():
        if comp.get("mount_side") != "bottom":
            continue
        for ref in comp.get("refs", []):
            fp = board.get(ref)
            if fp is None:
                continue
            if not fp.is_back:
                findings.append(Finding(
                    check="flip_integrity", component=cname, ok=False, severity="warning",
                    message=f"{ref} debería ir en B.Cu (mount_side=bottom) pero está en {fp.layer}",
                ))
                continue
            mirror_ok = fp.has_mirror_text()
            findings.append(Finding(
                check="flip_integrity", component=cname, ok=mirror_ok,
                message=(f"{ref}: footprint volteado correctamente a B.Cu"
                         if mirror_ok else
                         f"{ref}: FLIP FALSO — está en B.Cu pero la serigrafía/geometría no fue "
                         f"reflejada (sin '(justify mirror)'). El módulo físico entrará en ESPEJO."),
                detail=("" if mirror_ok else
                        "Causa: flip_to_back() solo renombra capas F.*→B.*; un volteo real "
                        "niega la X local y marca los textos con (justify mirror)."),
            ))
    return findings


# ── C4: net intent (each key bus touches exactly the expected pads) ──────
def check_net_intent(board: dict[str, Footprint], gt: GroundTruth) -> list[Finding]:
    findings: list[Finding] = []
    # Expected: from ground-truth, the set of (ref.pad) that each net SHOULD touch.
    expected: dict[str, set] = {}
    for comp in gt.components.values():
        for key, spec in comp.get("pins", {}).items():
            net = _norm(spec.get("net"))
            if net:
                expected.setdefault(net, set()).add(key)
    # Actual: scan all module pads in the board.
    actual: dict[str, set] = {}
    tracked_refs = {r for comp in gt.components.values() for r in comp.get("refs", [])}
    for ref in tracked_refs:
        fp = board.get(ref)
        if not fp:
            continue
        for num, pad in fp.pads.items():
            if pad.net_name:
                actual.setdefault(pad.net_name, set()).add(f"{ref}.{num}")

    for net in gt.key_nets:
        exp = expected.get(net, set())
        act = actual.get(net, set())
        missing = exp - act
        extra = act - exp
        ok = not missing and not extra
        det = []
        if missing:
            det.append(f"faltan en el net: {sorted(missing)}")
        if extra:
            det.append(f"sobran en el net (pads inesperados): {sorted(extra)}")
        findings.append(Finding(
            check="net_intent", component=net, ok=ok, severity="warning",
            message=(f"{net} conecta exactamente los pads previstos"
                     if ok else f"{net} no conecta el conjunto de pads previsto"),
            detail=" · ".join(det),
        ))
    return findings


# ── C5: pin-1 orientation (catches the bottom-mount pin-order reversal) ───
def check_pin1_orientation(board: dict[str, Footprint], gt: GroundTruth) -> list[Finding]:
    """Verify pad 1 (Vin) sits at the physical END the module needs.

    DRC/ERC and the pad→net check (C3) all pass even when a single-row B.Cu
    module's footprint has pad1 at the WRONG end: the netlist is self-
    consistent (pad1=Vin), but a bottom-mounted breakout inserts with its pin
    order REVERSED, so its Vin lands on the opposite pad → powered-but-no-ACK
    (ERRATA-001 §9; missed by the gate until 2026-06-16). This check pins the
    orientation: ground-truth `pin1_at` (x_min|x_max|y_min|y_max) says which
    extreme pad 1 must occupy; a reversed/rotated footprint fails it.
    """
    findings: list[Finding] = []
    for cname, comp in gt.components.items():
        want = comp.get("pin1_at")
        if not want:
            continue
        for ref in comp.get("refs", []):
            fp = board.get(ref)
            if not fp:
                continue
            pts = {n: fp.global_pad(n) for n in fp.pads}
            p1 = pts.get("1")
            if p1 is None:
                continue
            xs = [p[0] for p in pts.values()]
            ys = [p[1] for p in pts.values()]
            extreme = {"x_min": min(xs), "x_max": max(xs),
                       "y_min": min(ys), "y_max": max(ys)}[want]
            axis = 0 if want.startswith("x") else 1
            ok = abs(p1[axis] - extreme) < 0.5
            findings.append(Finding(
                check="pin1_orientation", component=cname, ok=ok,
                message=(f"{ref}: pad1/Vin en el extremo {want} (orientación OK)"
                         if ok else
                         f"{ref}: pad1/Vin NO está en {want} — footprint en orientación "
                         f"ESPEJADA/invertida para montaje por su cara → el módulo entra reversed"),
                detail=(f"pad1 @ ({p1[0]:.2f},{p1[1]:.2f}); esperado {want}={extreme:.2f}"),
            ))
    return findings


def run_all(board: dict[str, Footprint], gt: GroundTruth) -> list[Finding]:
    findings: list[Finding] = []
    findings += check_chirality(board, gt)
    findings += check_flip_integrity(board, gt)
    findings += check_pad_net_function(board, gt)
    findings += check_pin1_orientation(board, gt)
    findings += check_net_intent(board, gt)
    return findings
