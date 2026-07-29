"""Golden regression for pcb_designer.verify.pins (pin-on-pad alignment).

Runs against the real v0.1.4 overlays. After the 2026-06-18 parametric
auto-correction (and the v0.1.4 module-vs-mount-hole relayout), the three
single-row module photos (U2/U3/U4) must land on their pads with
perpendicular offset ≤ 0.15 mm. The XIAO is flagged
low-confidence (metallic body biases the gold-band metric) and must not hard
fail. Skipped if numpy/PIL or the overlays are missing.
"""
from __future__ import annotations

from pathlib import Path

import pytest

PCB_DIR = Path(__file__).resolve().parents[2]
MT1 = PCB_DIR / "projects" / "mt1"
PCB = MT1 / "kicad" / "mt1-pcb.kicad_pcb"
MODULES = MT1 / "overlays" / "modules.yaml"
IMAGES = MT1 / "overlays" / "component-images"
OV = {"top": MT1 / "overlays" / "v0.1.4-realistic-top.png",
      "bottom": MT1 / "overlays" / "v0.1.4-realistic-bottom.png"}

pytestmark = pytest.mark.skipif(not OV["top"].exists(), reason="v0.1.4 overlay missing")


@pytest.fixture(scope="module")
def report(tmp_path_factory):
    pytest.importorskip("numpy")
    pytest.importorskip("PIL")
    from pcb_designer.verify.pins import verify_pin_alignment
    out = tmp_path_factory.mktemp("pins")
    return verify_pin_alignment(PCB, MODULES, IMAGES, OV, out, tol_mm=0.15)


def test_overall_pass(report):
    assert report["pass"] is True
    assert report["failed"] == []


def test_single_row_modules_on_pads(report):
    by = {m["module"]: m for m in report["modules"]}
    for mod in ("LSM6DSO32", "BMP585", "microSD"):
        assert mod in by, f"{mod} not checked"
        assert by[mod]["max_perp_mm"] <= 0.15, f"{mod} perp too large: {by[mod]}"
        assert by[mod]["ok"] is True


def test_lsm6_landed_after_correction(report):
    """The module in the brief's photo: perpendicular alignment well under tol."""
    u2 = next(m for m in report["modules"] if m["module"] == "LSM6DSO32")
    assert abs(u2["rows"][0]["perp_off_mm"]) < 0.1


def test_xiao_present_and_lowconf(report):
    xiao = next(m for m in report["modules"] if m["module"] == "XIAO_ESP32S3")
    assert len(xiao["rows"]) == 2          # U1 + U5 measured independently
    assert all(not r["confident"] for r in xiao["rows"])
    assert xiao["ok"] is True              # low-confidence metric never hard-fails


def test_diff_images_written(report):
    for m in report["modules"]:
        assert m["diff_image"] and Path(m["diff_image"]).exists()


def test_aspect_guard_rejects_deformation():
    """FASE 0 hard rule: real_size_mm must match the source image aspect, or
    the composite stretches the photo (LESSONS_LEARNED §21)."""
    pytest.importorskip("PIL")
    from pcb_designer.render_overlay.compositor import _assert_image_aspect
    img = IMAGES / "lsm6dsox-imu.png"        # 597x426 → AR 1.401
    if not img.exists():
        pytest.skip("source image missing")
    # undistorted (height derived to match aspect) → OK
    _assert_image_aspect("ok", img, [25.244, 18.019], 0.05)
    # the 2026-06-18 deformed value (height 16 → AR 1.578, +12.6%) → MUST raise
    with pytest.raises(ValueError, match="DEFORMA"):
        _assert_image_aspect("bad", img, [25.244, 16.0], 0.05)


def test_all_overlay_images_undistorted():
    """Every module in the live modules.yaml must keep its source aspect ratio."""
    pytest.importorskip("PIL")
    from pcb_designer.render_overlay.compositor import load_module_config
    # load_module_config runs the aspect guard on every module; a deformed
    # config would raise here. (XIAO carries its documented ~3.6% deviation.)
    mods = load_module_config(MODULES, IMAGES)
    assert any(m.name == "LSM6DSO32" for m in mods)


def test_reproducible(tmp_path):
    pytest.importorskip("numpy")
    pytest.importorskip("PIL")
    from pcb_designer.verify.pins import verify_pin_alignment
    a = verify_pin_alignment(PCB, MODULES, IMAGES, OV, tmp_path / "a", tol_mm=0.15)
    b = verify_pin_alignment(PCB, MODULES, IMAGES, OV, tmp_path / "b", tol_mm=0.15)
    fa = {m["module"]: m["max_perp_mm"] for m in a["modules"]}
    fb = {m["module"]: m["max_perp_mm"] for m in b["modules"]}
    assert fa == fb
