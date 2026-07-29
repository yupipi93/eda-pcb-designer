"""Unit tests for pcb_designer.config."""
from __future__ import annotations

from pathlib import Path

import pytest

from pcb_designer.config import (
    AnchorGeometry,
    BodyExtent,
    PcbGeometry,
    Placement,
    load_config,
)

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def test_pcb_geometry_defaults_match_mt1():
    g = PcbGeometry()
    assert (g.x0, g.y0, g.x1, g.y1) == (90.0, 100.0, 190.0, 130.0)
    assert g.width == 100.0
    assert g.height == 30.0


def test_anchor_geometry_defaults():
    a = AnchorGeometry()
    assert (a.left_x, a.right_x) == (100.0, 170.0)


def test_placement_as_tuple():
    p = Placement(x=150.0, y=124.0, rot=180.0, layer="F.Cu")
    assert p.as_tuple() == (150.0, 124.0, 180.0, "F.Cu")


def test_body_extent_basic():
    b = BodyExtent(half=(8.89, 12.7), offset=(7.62, 11.43))
    assert b.half == (8.89, 12.7)
    assert b.offset == (7.62, 11.43)


def test_load_config_mt1_smoke():
    cfg = load_config(EXAMPLES / "mt1.yaml")
    assert cfg.project.name == "mt1"
    assert cfg.project.version == "v0.1.4"
    assert cfg.project.vendor == "MultitecUA"
    # 6 mounting holes + 5 modules + 1 J4 + 7 battery subsystem = 19
    assert len(cfg.placements) == 19
    # KEEP_REFS == set of placement refs
    assert cfg.keep_refs == set(cfg.placements.keys())
    # Through-hole footprints exclude SMD 0805 (R3, R4, C8)
    assert "U1" in cfg.th_footprints
    assert "R3" not in cfg.th_footprints
    # Geometry: 100 × 30 mm
    assert cfg.geometry_pcb.width == 100.0
    assert cfg.geometry_pcb.height == 30.0
    # Routing
    assert cfg.routing.trace_width_signal == 0.25
    assert cfg.routing.trace_width_power == 0.4


def test_load_config_placements_round_trip():
    cfg = load_config(EXAMPLES / "mt1.yaml")
    # XIAO U1 — left socket, USB-C +Y
    assert cfg.placements["U1"].as_tuple() == (150, 124, 180, "F.Cu")
    # LSM6DSO32 on B.Cu, rot=90
    assert cfg.placements["U2"].as_tuple() == (103, 127, 90, "B.Cu")
    # BMP585 moved to B.Cu in v0.1.0
    assert cfg.placements["U3"].as_tuple() == (145, 125, 180, "B.Cu")


def test_load_config_body_extent_typed():
    cfg = load_config(EXAMPLES / "mt1.yaml")
    assert cfg.body_extent["U2"].half == (8.89, 12.7)
    assert cfg.body_extent["U3"].offset == (7.62, 11.43)


def test_load_config_net_numbers():
    cfg = load_config(EXAMPLES / "mt1.yaml")
    assert cfg.net_numbers["GND"] == 2
    assert cfg.net_numbers["+3V3"] == 3
    assert cfg.net_numbers["DBG_RX"] == 25


def test_load_config_missing_path_raises():
    with pytest.raises(FileNotFoundError):
        load_config(EXAMPLES / "does-not-exist.yaml")


def test_load_config_missing_project_section(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("geometry:\n  pcb: { x0: 0, y0: 0, x1: 10, y1: 10 }\n")
    with pytest.raises(ValueError):
        load_config(bad)
