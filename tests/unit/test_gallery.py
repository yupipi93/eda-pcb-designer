"""Gallery grouping: one section per (version, style descriptor)."""
import argparse

from pcb_designer.cli import cmd_gallery


def test_gallery_multi_style_suite(tmp_path):
    for name in ("v0.2.1-normal-top.png", "v0.2.1-normal-bottom.png",
                 "v0.2.1-overlay-top.png", "v0.1.0-top.png"):
        (tmp_path / name).write_bytes(b"png")
    rc = cmd_gallery(argparse.Namespace(renders_dir=tmp_path))
    assert rc == 0
    idx = (tmp_path / "INDEX.md").read_text()
    assert "## v0.2.1 — normal" in idx
    assert "## v0.2.1 — overlay" in idx
    assert "## v0.1.0" in idx
    assert "v0.2.1-normal-bottom.png" in idx
