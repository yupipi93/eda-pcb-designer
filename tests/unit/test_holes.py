"""Tests for pcb_designer.verify.holes (mounting-hole verification).

Three layers:
  - text-only parsing + geometric check (no numpy/PIL needed),
  - a synthetic misplaced-hole board that MUST fail (proves the check bites),
  - a CV golden regression on the real v0.1.3 overlay (skipped if numpy/PIL or
    the render is missing) asserting every hole PASSes with sub-tolerance LOO,
    and that re-running is bit-identical (reproducibility).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from pcb_designer.verify import holes as H

PCB_DIR = Path(__file__).resolve().parents[2]
LIVE_PCB = PCB_DIR / "projects" / "mt1" / "kicad" / "mt1-pcb.kicad_pcb"
GT_PATH = PCB_DIR / "projects" / "mt1" / "ground-truth" / "holes.yaml"
OVERLAY = {
    "top": PCB_DIR / "projects" / "mt1" / "overlays" / "v0.1.3-realistic-top.png",
    "bottom": PCB_DIR / "projects" / "mt1" / "overlays" / "v0.1.3-realistic-bottom.png",
}

EXPECTED = {
    "H1": (175.0, 105.0), "H2": (185.0, 105.0), "H3": (175.0, 125.0),
    "H4": (185.0, 125.0), "H5": (95.0, 107.0), "H6": (95.0, 123.0),
}


@pytest.fixture(scope="module")
def design():
    return H.parse_design_holes(LIVE_PCB.read_text())


@pytest.fixture(scope="module")
def gt():
    return H.load_holes_groundtruth(GT_PATH)


# ── parsing ──────────────────────────────────────────────────────────────────
def test_parse_finds_six_holes(design):
    assert set(design) == set(EXPECTED)


def test_parse_positions_drill_pad(design):
    for ref, (x, y) in EXPECTED.items():
        d = design[ref]
        assert (d.x, d.y) == pytest.approx((x, y))
        assert d.drill_dia == pytest.approx(2.5)
        # pad size 5x5 must be read from the PAD sub-block, NOT the font (0.8).
        assert d.pad_dia == pytest.approx(5.0)
        assert d.layer == "F.Cu"


def test_outline_parsed():
    out = H.get_pcb_outline(LIVE_PCB.read_text())
    assert out == pytest.approx((90.0, 100.0, 190.0, 130.0))


def test_groundtruth_loads(gt):
    assert gt.screw == "M2"
    assert gt.drill_dia == pytest.approx(2.5)
    assert gt.pad_dia == pytest.approx(5.0)
    assert set(gt.holes) == set(EXPECTED)
    assert gt.outline == pytest.approx((90.0, 100.0, 190.0, 130.0))


# ── G: geometric check ───────────────────────────────────────────────────────
def test_live_board_geometric_clean(design, gt):
    findings = H.check_holes_geometric(design, gt)
    critical = [f for f in findings if not f.ok and f.severity == "critical"]
    assert not critical, [f.message for f in critical]
    # all six per-hole + five spacings must be present and PASS
    assert sum(1 for f in findings if f.check == "geometric") == 6
    assert sum(1 for f in findings if f.check == "spacing" and f.ok) == 5


def test_misplaced_hole_fails(design, gt):
    """Move H3 by 1 mm → its geometric check MUST fail; the rest stay clean."""
    import copy
    bad = copy.deepcopy(design)
    bad["H3"] = H.DesignHole(ref="H3", x=176.0, y=125.0, drill_dia=2.5,
                             pad_dia=5.0, layer="F.Cu", library=bad["H3"].library)
    fs = {f.ref: f for f in H.check_holes_geometric(bad, gt) if f.check == "geometric"}
    assert fs["H3"].ok is False
    assert fs["H3"].deviation_mm == pytest.approx(1.0, abs=1e-6)
    assert fs["H1"].ok is True and fs["H5"].ok is True


def test_wrong_drill_fails(design, gt):
    import copy
    bad = copy.deepcopy(design)
    bad["H1"] = H.DesignHole(ref="H1", x=175.0, y=105.0, drill_dia=3.2,
                             pad_dia=5.0, layer="F.Cu", library=bad["H1"].library)
    fs = {f.ref: f for f in H.check_holes_geometric(bad, gt) if f.check == "geometric"}
    assert fs["H1"].ok is False
    assert "taladro" in fs["H1"].message


def test_missing_hole_fails(design, gt):
    import copy
    bad = copy.deepcopy(design)
    del bad["H6"]
    fs = {f.ref: f for f in H.check_holes_geometric(bad, gt) if f.check == "geometric"}
    assert fs["H6"].ok is False
    assert "AUSENTE" in fs["H6"].message


# ── affine math ──────────────────────────────────────────────────────────────
def test_fit_affine_recovers_known_transform():
    pytest.importorskip("numpy")
    # Known affine: px = 10*x + 5, 10*y + 7 (pure scale+translate).
    src = [(0, 0), (10, 0), (0, 10), (10, 10), (5, 5), (3, 8)]
    dst = [(10 * x + 5, 10 * y + 7) for x, y in src]
    M, res = H._fit_affine(src, dst)
    assert res.max() < 1e-9
    assert M[0, 0] == pytest.approx(10.0)
    assert M[0, 2] == pytest.approx(5.0)
    assert M[1, 2] == pytest.approx(7.0)


# ── V: CV golden regression on the real v0.1.3 overlay ───────────────────────
@pytest.mark.skipif(not OVERLAY["top"].exists(), reason="v0.1.3 overlay missing")
def test_cv_detects_all_holes_top(gt):
    pytest.importorskip("numpy")
    pytest.importorskip("PIL")
    det = H.detect_holes_in_render(OVERLAY["top"], EXPECTED, gt.outline,
                                   side="top", mirrored=False, drill_dia_mm=gt.drill_dia)
    assert not det.not_found
    assert set(det.detected_px) == set(EXPECTED)
    # dark-bore detection is sub-pixel: every leave-one-out error well under tol.
    assert max(det.loo_err_mm.values()) < gt.cv_tol
    assert max(det.loo_err_mm.values()) < 0.05      # in practice ~5 µm
    cv = H.check_holes_cv(det, gt)
    assert all(f.ok for f in cv)


@pytest.mark.skipif(not OVERLAY["bottom"].exists(), reason="v0.1.3 overlay missing")
def test_cv_detects_all_holes_bottom_mirrored(gt):
    pytest.importorskip("numpy")
    pytest.importorskip("PIL")
    det = H.detect_holes_in_render(OVERLAY["bottom"], EXPECTED, gt.outline,
                                   side="bottom", mirrored=True, drill_dia_mm=gt.drill_dia)
    assert not det.not_found
    assert max(det.loo_err_mm.values()) < gt.cv_tol


@pytest.mark.skipif(not OVERLAY["top"].exists(), reason="v0.1.3 overlay missing")
def test_cv_reproducible(gt):
    """Re-running detection on the same render is bit-identical (idempotent)."""
    pytest.importorskip("numpy")
    pytest.importorskip("PIL")
    a = H.detect_holes_in_render(OVERLAY["top"], EXPECTED, gt.outline,
                                 side="top", mirrored=False, drill_dia_mm=gt.drill_dia)
    b = H.detect_holes_in_render(OVERLAY["top"], EXPECTED, gt.outline,
                                 side="top", mirrored=False, drill_dia_mm=gt.drill_dia)
    assert a.detected_px == b.detected_px
    assert a.affine == b.affine


@pytest.mark.skipif(not OVERLAY["top"].exists(), reason="v0.1.3 overlay missing")
def test_calibrate_from_holes_affine(gt):
    """FASE 2: the hole-derived affine maps each hole's mm to its detected px
    to sub-pixel, and falls back gracefully when given <4 holes."""
    pytest.importorskip("numpy")
    pytest.importorskip("PIL")
    from pcb_designer.render_overlay.render_calibrator import calibrate_from_holes
    base = PCB_DIR / "projects" / "mt1" / "renders" / "v0.1.3-top.png"
    if not base.exists():
        pytest.skip("base render missing")
    cal = calibrate_from_holes(base, gt.outline, EXPECTED, mirrored_x=False,
                               drill_dia_mm=gt.drill_dia)
    assert cal.method == "mounting_holes"
    assert cal.affine is not None
    # round-trip: mm→px of each hole must be within ~1 px of the green-bbox seed
    assert 10.0 < cal.px_per_mm < 13.0
    # fallback: only 2 holes → green_bbox
    cal2 = calibrate_from_holes(base, gt.outline,
                                {"H1": EXPECTED["H1"], "H2": EXPECTED["H2"]},
                                mirrored_x=False, min_holes=4)
    assert cal2.method == "green_bbox"


@pytest.mark.skipif(not OVERLAY["top"].exists(), reason="v0.1.3 overlay missing")
def test_full_verify_passes_v013(gt, tmp_path):
    pytest.importorskip("numpy")
    pytest.importorskip("PIL")
    rep = H.verify_holes(LIVE_PCB, GT_PATH, OVERLAY, tmp_path)
    assert rep["pass"] is True
    assert rep["geometric_failed"] == 0
    assert rep["cv_failed"] == 0
    # diff artefacts written
    for side in ("top", "bottom"):
        assert Path(rep["sides"][side]["diff_image"]).exists()
        assert Path(rep["sides"][side]["crops_image"]).exists()
