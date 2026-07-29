"""Unit + golden-regression tests for pcb_designer.verify (anti-mirror gate).

The golden regression runs the verifier against the REAL mt1-pcb.kicad_pcb
(which still carries the v0.1.x bugs) and asserts that each check catches
exactly its intended failure — and PASSES the parts that are correct. This
is the proof that the verifier actually works.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from pcb_designer.verify import pinmap
from pcb_designer.verify.checks import (
    check_chirality,
    check_flip_integrity,
    check_net_intent,
    check_pad_net_function,
    load_ground_truth,
    run_all,
)

PCB_DIR = Path(__file__).resolve().parents[2]
# Golden regression runs against a FROZEN copy of the buggy v0.1.1 board so it
# keeps validating "the verifier detects the 3 known bugs" even after the live
# board is fixed in v0.1.2.
BOARD_PATH = PCB_DIR / "tests" / "fixtures" / "mt1-pcb-v0.1.1-buggy.kicad_pcb"
LIVE_BOARD_PATH = PCB_DIR / "projects" / "mt1" / "kicad" / "mt1-pcb.kicad_pcb"
GT_PATH = PCB_DIR / "projects" / "mt1" / "ground-truth" / "components.yaml"


@pytest.fixture(scope="module")
def board():
    return pinmap.parse_board(BOARD_PATH.read_text())


@pytest.fixture(scope="module")
def gt():
    return load_ground_truth(GT_PATH)


# ── geometry ──────────────────────────────────────────────────────────────
def test_parse_finds_all_module_refs(board):
    for ref in ("U1", "U2", "U3", "U4", "U5"):
        assert ref in board, f"{ref} not parsed"


def test_global_pad_position_rot180(board):
    # U1 at (150,124,180); pad1 local (0,0) → (150,124); pad7 local (0,15.24)
    # rotated 180 → (0,-15.24) → (150, 108.76).
    assert board["U1"].global_pad("1") == pytest.approx((150.0, 124.0))
    gx, gy = board["U1"].global_pad("7")
    assert (gx, gy) == pytest.approx((150.0, 108.76))


def test_global_pad_position_rot270(board):
    # U4 at (125,108,270); pad row goes -X. pad2 local (0,2.54) → (-2.54,0)+anchor.
    assert board["U4"].global_pad("1") == pytest.approx((125.0, 108.0))
    assert board["U4"].global_pad("2") == pytest.approx((122.46, 108.0))


# ── C1 chirality ──────────────────────────────────────────────────────────
def test_chirality_flags_xiao_mirror(board, gt):
    fs = {f.component: f for f in check_chirality(board, gt)}
    assert "XIAO_ESP32S3" in fs
    assert fs["XIAO_ESP32S3"].ok is False  # mirrored → must FAIL


# ── C2 flip integrity ─────────────────────────────────────────────────────
def test_flip_integrity_flags_back_sensors(board, gt):
    fs = {f.component: f for f in check_flip_integrity(board, gt)}
    assert fs["LSM6DSO32"].ok is False   # fake flip → FAIL
    assert fs["BMP585"].ok is False      # fake flip → FAIL


# ── C3 pad → net → function ───────────────────────────────────────────────
def test_pad_net_function(board, gt):
    fs = {f.component: f for f in check_pad_net_function(board, gt)}
    # BMP585 has the SDA/SDO swap → FAIL
    assert fs["BMP585"].ok is False
    assert "SDO" in fs["BMP585"].detail and "SDA" in fs["BMP585"].detail
    # Correct parts must PASS (proves no false positives)
    assert fs["XIAO_ESP32S3"].ok is True
    assert fs["LSM6DSO32"].ok is True
    assert fs["microSD"].ok is True


# ── C4 net intent ─────────────────────────────────────────────────────────
def test_net_intent_flags_i2c_sda(board, gt):
    fs = {f.component: f for f in check_net_intent(board, gt)}
    assert fs["/I2C_SDA"].ok is False     # SDA lands on wrong pad
    assert fs["/I2C_SCL"].ok is True
    assert fs["/SDIO_CLK"].ok is True


# ── overall gate ──────────────────────────────────────────────────────────
def test_run_all_reports_known_failures(board, gt):
    findings = run_all(board, gt)
    failed = [f for f in findings if not f.ok]
    # XIAO chirality + U2 flip + U3 flip + BMP585 pad-net + /I2C_SDA intent
    # + U2/U3 pin1_orientation (bottom-mount reversal, added 2026-06-16) = 7
    assert len(failed) == 7, [f.component + ":" + f.check for f in failed]


def test_pin1_orientation_catches_reversed_sensors(board, gt):
    """C5 must flag the buggy fixture's reversed B.Cu sensor footprints."""
    from pcb_designer.verify.checks import check_pin1_orientation
    fs = {f.component: f for f in check_pin1_orientation(board, gt)}
    assert fs["LSM6DSO32"].ok is False   # pad1/Vin at wrong end
    assert fs["BMP585"].ok is False
    assert fs["microSD"].ok is True      # top-mount, pad1 at its natural end


# ── corrected board (v0.1.2) must be CLEAN ────────────────────────────────
@pytest.mark.skipif(not LIVE_BOARD_PATH.exists(), reason="live board missing")
def test_corrected_live_board_passes(gt):
    """After the v0.1.2 fix, the live board must pass every check."""
    live = pinmap.parse_board(LIVE_BOARD_PATH.read_text())
    failed = [f for f in run_all(live, gt) if not f.ok]
    assert not failed, "el board en vivo aún tiene fallos: " + str(
        [f"{f.component}:{f.check}" for f in failed])
