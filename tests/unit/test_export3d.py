"""Unit tests for the 3D export stage (pcb_designer.export3d).

All pure Python: the model-path parser, the missing-body detector, the
colour-variant substitution rule and the fetcher (with an injected opener so
nothing touches the network). The `kicad-cli` invocation itself is covered by
the API tests, which already assert "real output where the toolchain exists,
structured 501 where it doesn't".
"""
from __future__ import annotations

from pathlib import Path

import pytest

from pcb_designer.export3d import (
    Export3DResult,
    _substitute_candidates,
    export_3d,
    fetch_models,
    missing_models,
    referenced_models,
)

PCB_TEXT = """(kicad_pcb
  (footprint "LED_THT:LED_D3.0mm"
    (property "Reference" "D3")
    (model "${KICAD9_3DMODEL_DIR}/LED_THT.3dshapes/LED_D3.0mm_Green.step"
      (offset (xyz 0 0 0))
    )
  )
  (footprint "LED_THT:LED_D3.0mm"
    (property "Reference" "D9")
    (model "${KICAD9_3DMODEL_DIR}/LED_THT.3dshapes/LED_D3.0mm_Orange.step")
  )
  (footprint "Resistor_SMD:R_0805"
    (property "Reference" "R1")
    (model "${KICAD9_3DMODEL_DIR}/Resistor_SMD.3dshapes/R_0805_2012Metric.step")
  )
  (footprint "MountingHole:MountingHole_2.5mm"
    (property "Reference" "H1")
  )
)
"""


@pytest.fixture
def pcb(tmp_path: Path) -> Path:
    p = tmp_path / "board.kicad_pcb"
    p.write_text(PCB_TEXT, encoding="utf-8")
    return p


def test_referenced_models_dedupes_and_sorts(pcb):
    assert referenced_models(pcb) == [
        "LED_THT.3dshapes/LED_D3.0mm_Green.step",
        "LED_THT.3dshapes/LED_D3.0mm_Orange.step",
        "Resistor_SMD.3dshapes/R_0805_2012Metric.step",
    ]


def test_referenced_models_ignores_footprints_without_a_model(pcb):
    # H1 has no (model ...) block — it must not appear as a phantom path.
    assert not any("MountingHole" in m for m in referenced_models(pcb))


def test_missing_models_reports_only_absent_files(pcb, tmp_path):
    models = tmp_path / "models"
    present = models / "Resistor_SMD.3dshapes/R_0805_2012Metric.step"
    present.parent.mkdir(parents=True)
    present.write_bytes(b"solid")
    assert missing_models(pcb, models) == [
        "LED_THT.3dshapes/LED_D3.0mm_Green.step",
        "LED_THT.3dshapes/LED_D3.0mm_Orange.step",
    ]


def test_substitute_candidates_drops_exactly_one_suffix():
    assert _substitute_candidates("LED_THT.3dshapes/LED_D3.0mm_Orange.step") == [
        "LED_THT.3dshapes/LED_D3.0mm.step",
    ]


def test_substitute_candidates_never_strips_down_to_a_different_part():
    """`LED.step` is a different-sized body than `LED_D3.0mm_Orange.step`.

    Only one suffix comes off, so we never silently offer a wrong-sized
    part — an absent body is visible in the render, a wrong one is not.
    """
    cands = _substitute_candidates("d/X_A_B.step")
    assert cands == ["d/X_A.step"]
    assert "d/X.step" not in cands


def test_substitute_candidates_handles_bare_filename():
    assert _substitute_candidates("X_A.step") == ["X.step"]


def test_substitute_candidates_empty_when_there_is_no_suffix():
    assert _substitute_candidates("LED_THT.3dshapes/LED.step") == []


def _opener_for(available: dict[str, bytes]):
    """Fake HTTP opener: serves `available`, 404s everything else."""
    calls = []

    def opener(url: str, timeout: float) -> bytes:
        calls.append(url)
        rel = url.split("/-/raw/master/", 1)[-1]
        if rel in available:
            return available[rel]
        raise OSError(f"404 {rel}")

    opener.calls = calls
    return opener


def test_fetch_models_downloads_only_what_is_missing(pcb, tmp_path):
    models = tmp_path / "m"
    cached = models / "Resistor_SMD.3dshapes/R_0805_2012Metric.step"
    cached.parent.mkdir(parents=True)
    cached.write_bytes(b"cached")
    opener = _opener_for({
        "LED_THT.3dshapes/LED_D3.0mm_Green.step": b"green",
        "LED_THT.3dshapes/LED_D3.0mm_Orange.step": b"orange",
    })
    res = fetch_models(pcb, models, opener=opener)
    assert res.fetched_models == [
        "LED_THT.3dshapes/LED_D3.0mm_Green.step",
        "LED_THT.3dshapes/LED_D3.0mm_Orange.step",
    ]
    assert not res.missing_models
    # the cached file was never re-fetched
    assert all("R_0805" not in u for u in opener.calls)
    assert cached.read_bytes() == b"cached"


def test_fetch_models_substitutes_a_missing_colour_variant(pcb, tmp_path):
    """Upstream has no orange LED body — fall back to the base one, loudly."""
    models = tmp_path / "m"
    opener = _opener_for({
        "LED_THT.3dshapes/LED_D3.0mm_Green.step": b"green",
        "LED_THT.3dshapes/LED_D3.0mm.step": b"red-base",
        "Resistor_SMD.3dshapes/R_0805_2012Metric.step": b"res",
    })
    res = fetch_models(pcb, models, opener=opener)
    orange = "LED_THT.3dshapes/LED_D3.0mm_Orange.step"
    assert res.substituted_models == {orange: "LED_THT.3dshapes/LED_D3.0mm.step"}
    assert not res.missing_models
    assert (models / orange).read_bytes() == b"red-base"
    assert res.complete


def test_fetch_models_reports_unresolvable_bodies(pcb, tmp_path):
    """No upstream file and no fallback -> reported missing, not silently ok."""
    models = tmp_path / "m"
    opener = _opener_for({"Resistor_SMD.3dshapes/R_0805_2012Metric.step": b"res"})
    res = fetch_models(pcb, models, opener=opener)
    assert set(res.missing_models) == {
        "LED_THT.3dshapes/LED_D3.0mm_Green.step",
        "LED_THT.3dshapes/LED_D3.0mm_Orange.step",
    }
    assert not res.complete


def test_fetch_models_substitute_off_keeps_it_missing(pcb, tmp_path):
    models = tmp_path / "m"
    opener = _opener_for({"LED_THT.3dshapes/LED_D3.0mm.step": b"red-base"})
    res = fetch_models(pcb, models, substitute=False, opener=opener)
    assert "LED_THT.3dshapes/LED_D3.0mm_Orange.step" in res.missing_models
    assert not res.substituted_models


def test_export_3d_rejects_an_unknown_format(pcb, tmp_path):
    with pytest.raises(ValueError, match="unknown 3D format"):
        export_3d(pcb, tmp_path / "out", "v1.0.0", formats=("obj",))


def test_result_complete_reflects_missing_list():
    assert Export3DResult().complete
    assert not Export3DResult(missing_models=["a.step"]).complete
