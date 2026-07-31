"""HTTP API — stateless KiCad pipeline operations over uploaded board files.

Designed for agents and curl alike. Unlike the CLI (which orchestrates a
whole board project on disk), every endpoint here is a pure function of the
uploaded files: send a `.kicad_pcb` (+ optionally a `.kicad_sch` / YAML
config), get back the transformed file or report. No uploaded code is ever
executed — only KiCad file surgery via the pcb_designer engine.

  GET  /                     service info + endpoint list (HTML for browsers)
  GET  /health               liveness + toolchain versions
  GET  /openapi.json         OpenAPI 3 spec (so an agent can self-configure)
  POST /validate             YAML config → parsed summary (no files needed)
  POST /place                pcb + config → .kicad_pcb with placements applied
  POST /drc                  pcb → KiCad DRC report (JSON)
  POST /render               pcb → PNG render (style = bare | realistic |
                             realistic-dim | dim | overlay; see _RENDER_STYLES)
  POST /route                pcb → freerouting-autorouted .kicad_pcb
  POST /fab                  pcb + sch → gerbers/drill/BOM/pos release zip

File endpoints take multipart/form-data (fields: `pcb`, `sch`, `config`).
Binary responses are the transformed artefact; pass `?format=json` to get
base64 + metadata instead. Errors are always structured JSON with the right
HTTP status. Endpoints that need tools missing from the host (kicad-cli,
pcbnew, Java 21 + freerouting) answer 501 with install instructions — the
Docker image in `deploy/` ships everything.

Run locally:   gunicorn pcb_designer.api:app -b 0.0.0.0:8080
               (or: python -m pcb_designer.api  →  dev server)
"""
from __future__ import annotations

import base64
import io
import json
import os
import shutil
import subprocess
import tempfile
import threading
import zipfile
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_file

from pcb_designer import __version__
from pcb_designer.config import load_config

# pcbnew (route endpoint) is process-global and not proven thread-safe:
# serialise all pcbnew work behind one lock.
_PCBNEW_LOCK = threading.Lock()

JAR_PATH = Path(os.environ.get("PCB_DESIGNER_JAR", "/app/vendor/freerouting.jar"))
MAX_ROUTE_PASSES = 50

# /render styles:
#   bare          raytrace, (model ...) blocks stripped — copper/mask/silk only
#   realistic     raytrace with the installed 3D component models
#   realistic-dim realistic + floor/shadows + low lights (moody dark shot)
#   dim           MT1-style 2D DIM plot per side (PDF + theme → PNG → crop)
#   overlay       transparent-bg raytrace + client-supplied module photos
#                 composited by pcb_designer.render_overlay
_RENDER_STYLES = {"bare", "realistic", "realistic-dim", "dim", "overlay"}

# DIM plot per-side configs (theme, paint-order layer list, mirror) — the
# generic MT1 recipe: active side's layers LAST; back is a TRUE bottom view.
_DIM_SIDES = {
    "top": ("api-dim-front",
            ["Edge.Cuts", "B.Cu", "B.SilkS", "B.Mask",
             "F.Mask", "F.Cu", "F.SilkS", "F.Fab"], False),
    "bottom": ("api-dim-back",
               ["Edge.Cuts", "F.Cu", "F.SilkS", "F.Mask",
                "B.Mask", "B.Cu", "B.SilkS", "B.Fab"], True),
}


# ── helpers ──────────────────────────────────────────────────────────────────

def _err(status: str, message: str, code: int, **extra):
    return jsonify({"status": status, "error": message, **extra}), code


def _need_kicad_cli():
    if shutil.which("kicad-cli"):
        return None
    return _err("tool_missing",
                "kicad-cli not found on this host. Install KiCad 9 or use the "
                "Docker image (deploy/Dockerfile), which ships the full toolchain.",
                501)


def _save_upload(field: str, tmp: Path, filename: str, *, required: bool = True):
    """Persist a multipart upload under a fixed safe name inside tmp.

    Returns (path, error_response). Fixed names mean uploaded filenames can
    never traverse paths or collide.
    """
    f = request.files.get(field)
    if f is None or f.filename == "":
        if required:
            return None, _err("bad_request",
                              f"missing multipart file field '{field}'", 400)
        return None, None
    dest = tmp / filename
    f.save(dest)
    return dest, None


def _config_summary(cfg) -> dict:
    return {
        "name": cfg.project.name,
        "full_name": cfg.project.full_name,
        "version": cfg.project.version,
        "placements": len(cfg.placements),
        "through_hole": len(cfg.th_footprints),
        "board_mm": [cfg.geometry_pcb.width, cfg.geometry_pcb.height],
        "nets": len(cfg.net_numbers),
    }


def _load_yaml_config(tmp: Path):
    """Config from multipart 'config' field or raw request body (YAML text)."""
    cfg_path = tmp / "config.yaml"
    if request.mimetype == "multipart/form-data":
        f = request.files.get("config")
        if f is None or f.filename == "":
            return None, _err("bad_request",
                              "multipart request must include a 'config' file field", 400)
        f.save(cfg_path)
    else:
        # Raw body, whatever the Content-Type (curl --data-binary sends
        # x-www-form-urlencoded by default — don't let Werkzeug eat it as a form).
        raw = request.get_data(cache=True, parse_form_data=False)
        if not raw:
            return None, _err("bad_request",
                              "provide the YAML config as multipart field 'config' "
                              "or as the raw request body", 400)
        cfg_path.write_bytes(raw)
    try:
        return load_config(cfg_path), None
    except Exception as e:
        return None, _err("invalid_config", f"{type(e).__name__}: {e}", 400)


def _file_or_json(path: Path, *, mimetype: str, meta: dict):
    """Binary artefact by default; base64 + metadata with ?format=json."""
    wants_json = (request.args.get("format") == "json"
                  or "application/json" in request.headers.get("Accept", ""))
    if wants_json:
        return jsonify({"status": "ok",
                        "filename": path.name,
                        "content_b64": base64.b64encode(path.read_bytes()).decode(),
                        **meta})
    resp = send_file(io.BytesIO(path.read_bytes()), mimetype=mimetype,
                     as_attachment=True, download_name=path.name)
    for k, v in meta.items():
        if isinstance(v, (str, int, float)):
            resp.headers[f"X-Pcb-{k.replace('_', '-')}"] = str(v)
    return resp


# ── app ──────────────────────────────────────────────────────────────────────

def create_app() -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024   # 32 MB upload cap

    @app.get("/health")
    def health():
        def _v(cmd):
            try:
                out = subprocess.run(cmd, capture_output=True, text=True,
                                     timeout=20, check=False)
                return (out.stdout or out.stderr).strip().splitlines()[0]
            except Exception:
                return None
        models_dir = Path("/usr/share/kicad/3dmodels")
        return {"status": "ok", "service": "pcb-designer", "version": __version__,
                "toolchain": {"kicad_cli": _v(["kicad-cli", "version"]),
                              "java": _v(["java", "-version"]),
                              "freerouting_jar": JAR_PATH.exists(),
                              "kicad_3dmodels": models_dir.is_dir()
                              and any(models_dir.iterdir())},
                "render_styles": sorted(_RENDER_STYLES)}

    @app.get("/")
    def root():
        info = {
            "service": "pcb-designer",
            "version": __version__,
            "description": ("Stateless KiCad-9 pipeline operations: upload board "
                            "files, get back routed boards, DRC reports, renders "
                            "and fabrication outputs."),
            "endpoints": {
                "GET /health": "liveness + toolchain versions",
                "GET /openapi.json": "OpenAPI 3 spec",
                "POST /validate": "YAML config → parsed summary",
                "POST /place": "pcb + config → .kicad_pcb with placements applied",
                "POST /drc": "pcb → KiCad DRC report (JSON)",
                "POST /render": ("pcb → PNG (?side=top|bottom|both&style=bare|"
                                "realistic|realistic-dim|dim|overlay; overlay "
                                "adds multipart 'modules' yaml + 'images' files)"),
                "POST /route": "pcb → freerouting-autorouted .kicad_pcb",
                "POST /fab": "pcb + sch → gerbers/BOM/pos release zip (?version=vX.Y.Z)",
                "POST /export3d": ("pcb → interactive 3D model "
                                   "(?format=glb|step|both) — GLB opens in "
                                   "3dviewer.net or f3d, STEP in CAD"),
            },
            "example": ("curl -F pcb=@board.kicad_pcb $URL/route -o routed.kicad_pcb"),
            "docs": "https://github.com/yupipi93/eda-pcb-designer",
        }
        if "text/html" in request.headers.get("Accept", ""):
            return Response(_LANDING.replace("__VERSION__", __version__),
                            mimetype="text/html")
        return info

    @app.get("/openapi.json")
    def openapi():
        return jsonify(_OPENAPI)

    @app.post("/validate")
    def validate():
        with tempfile.TemporaryDirectory() as td:
            cfg, err = _load_yaml_config(Path(td))
            if err:
                return err
            return jsonify({"status": "ok", **_config_summary(cfg)})

    @app.post("/place")
    def place():
        from pcb_designer.placement import place_and_flip
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            pcb, err = _save_upload("pcb", tmp, "board.kicad_pcb")
            if err:
                return err
            cfg, err = _load_yaml_config(tmp)
            if err:
                return err
            text = pcb.read_text(encoding="utf-8")
            placements = {ref: p.as_tuple() for ref, p in cfg.placements.items()}
            text, updated, not_found = place_and_flip(text, placements)
            out = tmp / f"{cfg.project.name}-placed.kicad_pcb"
            out.write_text(text, encoding="utf-8")
            return _file_or_json(out, mimetype="application/octet-stream",
                                 meta={"updated": updated,
                                       "not_found": ",".join(not_found) if not_found else ""})

    @app.post("/drc")
    def drc():
        missing = _need_kicad_cli()
        if missing:
            return missing
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            pcb, err = _save_upload("pcb", tmp, "board.kicad_pcb")
            if err:
                return err
            report = tmp / "drc.json"
            r = subprocess.run(["kicad-cli", "pcb", "drc", str(pcb),
                                "--format", "json", "--output", str(report)],
                               capture_output=True, text=True, check=False)
            if not report.exists():
                return _err("drc_failed",
                            f"kicad-cli pcb drc exited {r.returncode}: "
                            f"{(r.stderr or r.stdout).strip()[-500:]}", 500)
            data = json.loads(report.read_text(encoding="utf-8"))
            violations = data.get("violations", [])
            sev = {}
            for v in violations:
                sev[v.get("severity", "?")] = sev.get(v.get("severity", "?"), 0) + 1
            return jsonify({"status": "ok",
                            "violation_count": len(violations),
                            "by_severity": sev,
                            "unconnected_count": len(data.get("unconnected_items", [])),
                            "report": data})

    @app.post("/render")
    def render():
        side = request.args.get("side", "top")
        if side not in ("top", "bottom", "both"):
            return _err("bad_request", "side must be top | bottom | both", 400)
        style = request.args.get("style", "bare")
        if style not in _RENDER_STYLES:
            return _err("bad_request",
                        f"style must be one of {sorted(_RENDER_STYLES)}", 400)
        background = request.args.get("background", "opaque")
        if background not in ("opaque", "transparent", "default"):
            return _err("bad_request",
                        "background must be opaque | transparent | default", 400)
        missing = _need_kicad_cli()
        if missing:
            return missing
        sides = ("top", "bottom") if side == "both" else (side,)
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            pcb, err = _save_upload("pcb", tmp, "board.kicad_pcb")
            if err:
                return err

            if style == "overlay":
                return _render_overlay(tmp, pcb, sides)

            if style == "bare":
                # strip every (model ...) block so the raytrace shows copper/
                # mask/silk only, even with kicad-packages3d installed
                from pcb_designer.kicad_pcb_io import strip_3d_model_blocks
                pcb.write_text(strip_3d_model_blocks(
                    pcb.read_text(encoding="utf-8")), encoding="utf-8")

            pngs = []
            for s in sides:
                png = tmp / f"render-{s}.png"
                if style == "dim":
                    err = _render_dim_side(pcb, s, png, tmp)
                else:
                    bg = "opaque" if style == "realistic-dim" else background
                    cmd = ["kicad-cli", "pcb", "render", str(pcb),
                           "--side", s, "--background", bg,
                           "--output", str(png)]
                    if style in ("realistic", "realistic-dim"):
                        cmd += ["--quality", "high"]
                    if style == "realistic-dim":
                        cmd += ["--floor",
                                "--light-top", "0.25", "--light-bottom", "0.12",
                                "--light-side", "0.2", "--light-camera", "0.12"]
                    r = subprocess.run(cmd, capture_output=True, text=True,
                                       check=False)
                    err = (None if r.returncode == 0 and png.exists() else
                           (r.stderr or r.stdout).strip()[-500:])
                if err:
                    return _err("render_failed",
                                f"render ({style}/{s}) failed: {err}", 500)
                pngs.append(png)
            if len(pngs) == 1:
                return _file_or_json(pngs[0], mimetype="image/png",
                                     meta={"side": side, "style": style})
            bundle = tmp / "renders.zip"
            with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as z:
                for p in pngs:
                    z.write(p, p.name)
            return _file_or_json(bundle, mimetype="application/zip",
                                 meta={"side": side, "style": style})

    def _render_dim_side(pcb: Path, s: str, png: Path, tmp: Path):
        """MT1-style 2D DIM plot: kicad-cli PDF with the dim theme →
        pdftocairo → crop (pcb_designer.render_dim)."""
        from pcb_designer.render_dim import install_themes, render_side
        themes_src = Path(os.environ.get("PCB_DESIGNER_THEMES", "/app/themes"))
        if not themes_src.is_dir():
            return f"themes dir not found: {themes_src}"
        install_themes(themes_src, prefix="api-")
        theme, layers, mirror = _DIM_SIDES[s]
        work = tmp / "dim-work"          # render_side's intermediate PDF/PNG
        work.mkdir(exist_ok=True)        # share the output's stem — keep them
        try:                             # in their own dir to avoid collision
            render_side(pcb, layers, theme, png, work, mirror=mirror)
        except Exception as e:                      # pragma: no cover
            return f"{type(e).__name__}: {e}"
        return None if png.exists() else "dim plot produced no PNG"

    def _render_overlay(tmp: Path, pcb: Path, sides):
        """Photo-overlay compositing: client uploads `modules` (yaml) plus
        one `images` file per module photo; the base render is a transparent-
        background raytrace (LESSONS_LEARNED §22), module photos are pasted
        by pcb_designer.render_overlay."""
        from pcb_designer.render_overlay.compositor import (
            compose_side,
            load_module_config,
        )
        modules_yaml, err = _save_upload("modules", tmp, "modules.yaml")
        if err:
            return err
        images_dir = tmp / "component-images"
        images_dir.mkdir()
        for f in request.files.getlist("images"):
            name = Path(f.filename or "").name
            if not name:
                return _err("bad_request", "an images part has no filename", 400)
            f.save(images_dir / name)
        calibration = request.args.get("calibration", "mounting_holes")
        if calibration not in ("mounting_holes", "green_bbox"):
            return _err("bad_request",
                        "calibration must be mounting_holes | green_bbox", 400)
        ann = request.args.get("annotations",
                               "pcb,anchors,holes,modules,pins").strip()
        annotate = ann.lower() not in ("none", "")
        cats = tuple(c.strip() for c in ann.split(",") if c.strip())
        try:
            modules = load_module_config(modules_yaml, images_dir)
        except Exception as e:
            return _err("bad_request", f"invalid modules.yaml: {e}", 400)

        pngs = []
        for s in sides:
            base = tmp / f"base-{s}.png"
            r = subprocess.run(["kicad-cli", "pcb", "render", str(pcb),
                                "--side", s, "--background", "transparent",
                                "--quality", "high", "--output", str(base)],
                               capture_output=True, text=True, check=False)
            if r.returncode != 0 or not base.exists():
                return _err("render_failed",
                            f"base render ({s}) exited {r.returncode}: "
                            f"{(r.stderr or r.stdout).strip()[-500:]}", 500)
            out = tmp / f"render-overlay-{s}.png"
            try:
                result = compose_side(side=s, base_render_path=base,
                                      pcb_path=pcb, modules=modules,
                                      output_path=out, annotate=annotate,
                                      annotation_categories=cats,
                                      calibration=calibration)
            except Exception as e:
                return _err("overlay_failed", f"{type(e).__name__}: {e}", 500)
            app.logger.info("overlay %s: %s modules, skipped=%s",
                            s, result["rendered"], result["skipped"])
            pngs.append(out)
        if len(pngs) == 1:
            return _file_or_json(pngs[0], mimetype="image/png",
                                 meta={"style": "overlay"})
        bundle = tmp / "renders.zip"
        with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as z:
            for p in pngs:
                z.write(p, p.name)
        return _file_or_json(bundle, mimetype="application/zip",
                             meta={"style": "overlay"})

    @app.post("/route")
    def route():
        from pcb_designer import autorouter
        if autorouter.pcbnew is None:
            return _err("tool_missing",
                        "pcbnew Python module not importable on this host. "
                        "Install KiCad 9 or use the Docker image.", 501)
        if not JAR_PATH.exists():
            return _err("tool_missing",
                        f"freerouting JAR not found at {JAR_PATH}. Run "
                        "vendor/fetch-freerouting.sh or set PCB_DESIGNER_JAR.", 501)
        try:
            java_bin = autorouter.find_java21()
        except RuntimeError as e:
            return _err("tool_missing", str(e), 501)
        try:
            passes = min(int(request.args.get("passes", 30)), MAX_ROUTE_PASSES)
            optim = min(int(request.args.get("optim", 5)), 20)
        except ValueError:
            return _err("bad_request", "passes/optim must be integers", 400)

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            pcb, err = _save_upload("pcb", tmp, "board.kicad_pcb")
            if err:
                return err
            dsn, ses, log = tmp / "board.dsn", tmp / "board.ses", tmp / "freerouting.log"
            try:
                with _PCBNEW_LOCK:
                    autorouter.export_specctra_dsn(pcb, dsn)
                autorouter.run_freerouting(java_bin, JAR_PATH, dsn, ses, log,
                                           max_passes=passes, optim_rounds=optim)
                with _PCBNEW_LOCK:
                    autorouter.import_ses_and_fill(pcb, ses)
            except (SystemExit, Exception) as e:   # autorouter helpers sys.exit on failure
                tail = log.read_text(encoding="utf-8").splitlines()[-15:] if log.exists() else []
                return _err("route_failed",
                            f"autorouting failed ({type(e).__name__}: {e})", 500,
                            log_tail=tail)
            out = tmp / "board-routed.kicad_pcb"
            out.write_bytes(pcb.read_bytes())
            return _file_or_json(out, mimetype="application/octet-stream",
                                 meta={"passes": passes})

    @app.post("/fab")
    def fab():
        missing = _need_kicad_cli()
        if missing:
            return missing
        from pcb_designer.fab import full_fab
        version = request.args.get("version", "v0.0.0-api")
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            pcb, err = _save_upload("pcb", tmp, "board.kicad_pcb")
            if err:
                return err
            sch, err = _save_upload("sch", tmp, "board.kicad_sch")
            if err:
                return err
            try:
                zip_path = full_fab(pcb, sch, tmp / "releases", version)
            except (SystemExit, Exception) as e:
                return _err("fab_failed", f"{type(e).__name__}: {e}", 500)
            return _file_or_json(Path(zip_path), mimetype="application/zip",
                                 meta={"version": version})

    @app.post("/export3d")
    def export3d():
        """pcb -> rotatable 3D model (GLB for viewers, STEP for CAD).

        `?format=glb|step|both` (default glb). `both` returns a zip. This
        host ships kicad-packages3d, so component bodies resolve here even
        though a slim local KiCad install would drop them.
        """
        missing = _need_kicad_cli()
        if missing:
            return missing
        from pcb_designer.export3d import export_3d
        fmt = (request.args.get("format") or "glb").lower()
        if fmt not in {"glb", "step", "both"}:
            return _err("bad_request",
                        f"format must be glb, step or both (got {fmt!r})", 400)
        version = request.args.get("version", "v0.0.0-api")
        formats = ("glb", "step") if fmt == "both" else (fmt,)
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            pcb, err = _save_upload("pcb", tmp, "board.kicad_pcb")
            if err:
                return err
            try:
                res = export_3d(pcb, tmp / "3d", version, formats=formats,
                                stem="board")
            except (SystemExit, Exception) as e:
                return _err("export3d_failed", f"{type(e).__name__}: {e}", 500)
            meta = {"version": version,
                    "missing_models": len(res.missing_models),
                    "complete": res.complete}
            if len(res.files) == 1:
                only = next(iter(res.files.values()))
                mt = ("model/gltf-binary" if only.suffix == ".glb"
                      else "application/step")
                return _file_or_json(only, mimetype=mt, meta=meta)
            bundle = tmp / f"board-{version}-3d.zip"
            with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as z:
                for path in res.files.values():
                    z.write(path, arcname=path.name)
            return _file_or_json(bundle, mimetype="application/zip", meta=meta)

    return app


# ── landing page + OpenAPI ───────────────────────────────────────────────────

_LANDING = """<!doctype html>
<html><head><meta charset="utf-8"><title>pcb-designer API</title>
<style>
 body{font-family:system-ui,sans-serif;max-width:52rem;margin:3rem auto;
      padding:0 1rem;line-height:1.5;color:#222}
 code,pre{background:#f4f4f4;border-radius:4px;padding:.1rem .3rem}
 pre{padding:.8rem;overflow-x:auto}
 table{border-collapse:collapse}td,th{border:1px solid #ddd;padding:.4rem .6rem;text-align:left}
 h1{margin-bottom:0}.v{color:#777}
</style></head><body>
<h1>pcb-designer <span class="v">__VERSION__</span></h1>
<p><strong>Stateless KiCad-9 pipeline operations over HTTP.</strong> Upload board
files, get back routed boards, DRC reports, renders and fabrication outputs.
The engine is deterministic — no LLM inside — and built to be driven by humans
and AI agents. <a href="https://github.com/yupipi93/eda-pcb-designer">Docs on GitHub</a>.</p>
<table>
<tr><th>Endpoint</th><th>What it does</th></tr>
<tr><td><code>GET /health</code></td><td>liveness + toolchain versions</td></tr>
<tr><td><code>GET /openapi.json</code></td><td>OpenAPI 3 spec (agents self-configure)</td></tr>
<tr><td><code>POST /validate</code></td><td>YAML board config → parsed summary</td></tr>
<tr><td><code>POST /place</code></td><td>pcb + config → placements applied</td></tr>
<tr><td><code>POST /drc</code></td><td>pcb → KiCad DRC report (JSON)</td></tr>
<tr><td><code>POST /render</code></td><td>pcb → PNG
  (<code>?side=top|bottom|both&amp;style=bare|realistic|realistic-dim|dim|overlay</code>;
  overlay takes multipart <code>modules</code> yaml + <code>images</code> files)</td></tr>
<tr><td><code>POST /route</code></td><td>pcb → freerouting-autorouted pcb</td></tr>
<tr><td><code>POST /fab</code></td><td>pcb + sch → gerbers/BOM/pos zip</td></tr>
<tr><td><code>POST /export3d</code></td><td>pcb → rotatable 3D model
  (<code>?format=glb|step|both</code>). Drop the <code>.glb</code> on
  <a href="https://3dviewer.net">3dviewer.net</a>, or <code>f3d file.glb</code></td></tr>
</table>
<h2>Try it</h2>
<pre>URL=https://this-service

# Autoroute a board (the flagship: freerouting-as-a-service)
curl -F pcb=@board.kicad_pcb "$URL/route" -o routed.kicad_pcb

# DRC report
curl -F pcb=@board.kicad_pcb "$URL/drc" | jq .by_severity

# Rotatable 3D model — then drag board.glb onto https://3dviewer.net
curl -F pcb=@board.kicad_pcb "$URL/export3d?format=glb" -o board.glb

# Raytraced render of both sides
curl -F pcb=@board.kicad_pcb "$URL/render?side=both" -o renders.zip

# JLCPCB-ready fabrication zip
curl -F pcb=@board.kicad_pcb -F sch=@board.kicad_sch "$URL/fab?version=v1.0.0" -o release.zip</pre>
<p>Binary responses become base64 JSON with <code>?format=json</code>. Errors are
structured JSON with meaningful HTTP statuses, so an agent can fix and retry.</p>
</body></html>
"""

_FILE_RESP = {"200": {"description": "The artefact (binary), or base64 JSON with ?format=json"},
              "400": {"description": "Bad request (structured JSON)"},
              "500": {"description": "Operation failed (structured JSON, may include log_tail)"},
              "501": {"description": "Required tool missing on this host"}}

_OPENAPI = {
    "openapi": "3.0.3",
    "info": {"title": "pcb-designer API", "version": __version__,
             "description": "Stateless KiCad-9 pipeline operations: place, "
                            "route (freerouting), DRC, render, fab."},
    "paths": {
        "/health": {"get": {"summary": "Liveness + toolchain versions",
                            "responses": {"200": {"description": "OK"}}}},
        "/validate": {"post": {
            "summary": "Parse + summarise a YAML board config",
            "requestBody": {"content": {
                "application/x-yaml": {"schema": {"type": "string"}},
                "multipart/form-data": {"schema": {"type": "object", "properties": {
                    "config": {"type": "string", "format": "binary"}}}}}},
            "responses": {"200": {"description": "Summary JSON"},
                          "400": {"description": "Invalid config"}}}},
        "/place": {"post": {
            "summary": "Apply YAML placements to a .kicad_pcb (genuine layer flips)",
            "requestBody": {"content": {"multipart/form-data": {"schema": {
                "type": "object", "required": ["pcb", "config"], "properties": {
                    "pcb": {"type": "string", "format": "binary"},
                    "config": {"type": "string", "format": "binary"}}}}}},
            "responses": _FILE_RESP}},
        "/drc": {"post": {
            "summary": "KiCad DRC report for a .kicad_pcb",
            "requestBody": {"content": {"multipart/form-data": {"schema": {
                "type": "object", "required": ["pcb"], "properties": {
                    "pcb": {"type": "string", "format": "binary"}}}}}},
            "responses": {"200": {"description": "JSON report + severity counts"},
                          "500": {"description": "DRC failed"},
                          "501": {"description": "kicad-cli missing"}}}},
        "/render": {"post": {
            "summary": "PNG render of a .kicad_pcb (raytrace, DIM plot or "
                       "photo overlay)",
            "parameters": [
                {"name": "side", "in": "query",
                 "schema": {"enum": ["top", "bottom", "both"], "default": "top"}},
                {"name": "style", "in": "query",
                 "description": "bare = raytrace without 3D models; realistic = "
                                "raytrace with kicad-packages3d bodies; "
                                "realistic-dim = realistic + floor/shadows + low "
                                "lights; dim = 2D DIM-theme plot (MT1 style); "
                                "overlay = transparent raytrace + client module "
                                "photos composited on top",
                 "schema": {"enum": ["bare", "realistic", "realistic-dim",
                                     "dim", "overlay"], "default": "bare"}},
                {"name": "background", "in": "query",
                 "schema": {"enum": ["opaque", "transparent", "default"],
                            "default": "opaque"}},
                {"name": "calibration", "in": "query",
                 "description": "overlay only: mm→px mapping source "
                                "(green_bbox for boards with <4 holes)",
                 "schema": {"enum": ["mounting_holes", "green_bbox"],
                            "default": "mounting_holes"}},
                {"name": "annotations", "in": "query",
                 "description": "overlay only: csv of pcb,anchors,holes,"
                                "modules,pins — or 'none'",
                 "schema": {"type": "string",
                            "default": "pcb,anchors,holes,modules,pins"}}],
            "requestBody": {"content": {"multipart/form-data": {"schema": {
                "type": "object", "required": ["pcb"], "properties": {
                    "pcb": {"type": "string", "format": "binary"},
                    "modules": {"type": "string", "format": "binary",
                                "description": "overlay only: modules.yaml"},
                    "images": {"type": "array", "description":
                               "overlay only: one part per module photo",
                               "items": {"type": "string",
                                         "format": "binary"}}}}}}},
            "responses": _FILE_RESP}},
        "/route": {"post": {
            "summary": "Autoroute a .kicad_pcb with freerouting (strip tracks → "
                       "DSN → freerouting → SES → zone fill)",
            "parameters": [
                {"name": "passes", "in": "query",
                 "schema": {"type": "integer", "default": 30, "maximum": 50}},
                {"name": "optim", "in": "query",
                 "schema": {"type": "integer", "default": 5, "maximum": 20}}],
            "requestBody": {"content": {"multipart/form-data": {"schema": {
                "type": "object", "required": ["pcb"], "properties": {
                    "pcb": {"type": "string", "format": "binary"}}}}}},
            "responses": _FILE_RESP}},
        "/export3d": {"post": {
            "summary": "Export a rotatable 3D model (GLB for viewers, STEP for CAD)",
            "parameters": [
                {"name": "format", "in": "query", "required": False,
                 "schema": {"type": "string", "enum": ["glb", "step", "both"],
                            "default": "glb"}},
                {"name": "version", "in": "query", "required": False,
                 "schema": {"type": "string"}},
            ],
            "requestBody": {"content": {"multipart/form-data": {"schema": {
                "type": "object", "required": ["pcb"], "properties": {
                    "pcb": {"type": "string", "format": "binary"}}}}}},
            "responses": _FILE_RESP}},
        "/fab": {"post": {
            "summary": "Gerbers + drill + BOM + pos release zip",
            "parameters": [{"name": "version", "in": "query",
                            "schema": {"type": "string", "default": "v0.0.0-api"}}],
            "requestBody": {"content": {"multipart/form-data": {"schema": {
                "type": "object", "required": ["pcb", "sch"], "properties": {
                    "pcb": {"type": "string", "format": "binary"},
                    "sch": {"type": "string", "format": "binary"}}}}}},
            "responses": _FILE_RESP}},
    },
}

app = create_app()

if __name__ == "__main__":   # dev server
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=True)
