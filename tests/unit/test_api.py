"""Unit tests for the HTTP API (pcb_designer.api).

Covers the endpoints that are pure Python (health, root, openapi, validate,
place) on any host. The toolchain endpoints (drc/render/route/fab) are
asserted to answer correctly for the host: a real report where kicad-cli is
installed (the Docker image, CI's docker job), a structured 501 where it
isn't — never a crash.
"""
from __future__ import annotations

import io
import shutil
from pathlib import Path

import pytest

flask = pytest.importorskip("flask")

from pcb_designer.api import create_app  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
MT1_YAML = REPO / "examples" / "mt1.yaml"
FIXTURE_PCB = REPO / "tests" / "fixtures" / "mt1-pcb-v0.1.1-buggy.kicad_pcb"


@pytest.fixture(scope="module")
def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"] == "ok"
    assert body["service"] == "pcb-designer"
    assert "toolchain" in body


def test_root_json_and_html(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "endpoints" in r.get_json()
    r = client.get("/", headers={"Accept": "text/html"})
    assert r.status_code == 200
    assert b"pcb-designer" in r.data


def test_openapi(client):
    spec = client.get("/openapi.json").get_json()
    assert spec["openapi"].startswith("3.")
    for path in ("/validate", "/place", "/drc", "/render", "/route", "/fab"):
        assert path in spec["paths"]


def test_validate_raw_body(client):
    r = client.post("/validate", data=MT1_YAML.read_bytes())
    assert r.status_code == 200
    body = r.get_json()
    assert body["name"] == "mt1"
    assert body["placements"] == 19


def test_validate_multipart(client):
    r = client.post("/validate", data={
        "config": (io.BytesIO(MT1_YAML.read_bytes()), "mt1.yaml"),
    }, content_type="multipart/form-data")
    assert r.status_code == 200
    assert r.get_json()["name"] == "mt1"


def test_validate_garbage_is_400(client):
    r = client.post("/validate", data=b"geometry: {pcb: {x0: 0}}")
    assert r.status_code == 400
    assert r.get_json()["status"] == "invalid_config"


def test_validate_empty_is_400(client):
    assert client.post("/validate").status_code == 400


def test_place_applies_placements(client):
    r = client.post("/place?format=json", data={
        "pcb": (io.BytesIO(FIXTURE_PCB.read_bytes()), "board.kicad_pcb"),
        "config": (io.BytesIO(MT1_YAML.read_bytes()), "mt1.yaml"),
    }, content_type="multipart/form-data")
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"] == "ok"
    assert body["updated"] > 0
    import base64
    text = base64.b64decode(body["content_b64"]).decode()
    # U1 must sit at the mt1.yaml target (150, 124, 180)
    assert "(at 150 124 180)" in text


def test_place_missing_pcb_is_400(client):
    r = client.post("/place", data={
        "config": (io.BytesIO(MT1_YAML.read_bytes()), "mt1.yaml"),
    }, content_type="multipart/form-data")
    assert r.status_code == 400


def test_drc_answers_for_this_host(client):
    """Real report where kicad-cli exists; structured 501 where it doesn't."""
    r = client.post("/drc", data={
        "pcb": (io.BytesIO(FIXTURE_PCB.read_bytes()), "board.kicad_pcb"),
    }, content_type="multipart/form-data")
    if shutil.which("kicad-cli"):
        assert r.status_code == 200
        assert "violation_count" in r.get_json()
    else:
        assert r.status_code == 501
        assert r.get_json()["status"] == "tool_missing"


def test_render_bad_side_is_400(client):
    r = client.post("/render?side=diagonal", data={
        "pcb": (io.BytesIO(b"x"), "board.kicad_pcb"),
    }, content_type="multipart/form-data")
    assert r.status_code == 400


def test_render_bad_style_is_400(client):
    r = client.post("/render?style=sepia", data={
        "pcb": (io.BytesIO(b"x"), "board.kicad_pcb"),
    }, content_type="multipart/form-data")
    assert r.status_code == 400
    assert "style" in r.get_json()["error"]


def test_render_overlay_requires_modules(client):
    # style=overlay without a 'modules' yaml must 400 before any rendering
    r = client.post("/render?style=overlay", data={
        "pcb": (io.BytesIO(b"x"), "board.kicad_pcb"),
    }, content_type="multipart/form-data")
    assert r.status_code in (400, 501)   # 501 only if kicad-cli missing
    if r.status_code == 400:
        assert "modules" in r.get_json()["error"]


def test_render_overlay_bad_calibration_is_400(client):
    r = client.post("/render?style=overlay&calibration=nope", data={
        "pcb": (io.BytesIO(b"x"), "board.kicad_pcb"),
        "modules": (io.BytesIO(b"modules: {}"), "modules.yaml"),
    }, content_type="multipart/form-data")
    assert r.status_code in (400, 501)


def test_health_reports_render_styles(client):
    styles = client.get("/health").get_json()["render_styles"]
    assert set(styles) == {"bare", "realistic", "realistic-dim", "dim", "overlay"}


# ── /export3d ────────────────────────────────────────────────────────────────

def test_export3d_rejects_unknown_format(client):
    r = client.post("/export3d?format=obj",
                    data={"pcb": (io.BytesIO(b"(kicad_pcb)"), "b.kicad_pcb")},
                    content_type="multipart/form-data")
    # 400 on a bad format everywhere kicad-cli exists; 501 where it doesn't.
    assert r.status_code in (400, 501)
    if r.status_code == 400:
        assert "glb" in r.get_json()["error"]


def test_export3d_requires_a_pcb(client):
    r = client.post("/export3d", data={}, content_type="multipart/form-data")
    assert r.status_code in (400, 501)


def test_export3d_is_advertised(client):
    assert "POST /export3d" in client.get("/").get_json()["endpoints"]
    assert "/export3d" in client.get("/openapi.json").get_json()["paths"]


@pytest.mark.skipif(not shutil.which("kicad-cli"), reason="needs kicad-cli")
def test_export3d_glb_on_a_real_board(client):
    r = client.post("/export3d?format=glb",
                    data={"pcb": (io.BytesIO(FIXTURE_PCB.read_bytes()),
                                  "b.kicad_pcb")},
                    content_type="multipart/form-data")
    assert r.status_code == 200, r.data[:400]
    assert r.data[:4] == b"glTF"          # binary glTF magic

