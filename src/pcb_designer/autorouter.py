"""Freerouting wrapper: DSN/SES round-trip + Java 21 detection ladder.

Lift-and-shift of the autorouter pipeline from projects/mt1/tools/run_autorouter.py.
All functions take paths as explicit parameters (board-agnostic).

Public API:
- `find_java21() -> str` — class-file-65+ aware detection ladder
  (LESSONS_LEARNED §10).
- `ensure_tools(jar_path) -> str` — validate freerouting JAR exists +
  return a Java 21+ binary; sys.exit(2) on failure.
- `export_specctra_dsn(pcb_path, dsn_path)` — load .kicad_pcb, strip
  existing tracks, export DSN (LESSONS_LEARNED §9).
- `run_freerouting(java_bin, jar_path, dsn_path, ses_path, log_path,
  max_passes=30, threads=4, optim_rounds=5)` — invoke the OSS autorouter.
- `add_gnd_stitches(board, stitches)` — inject B.Cu GND bridge tracks
  (LESSONS_LEARNED §12). `stitches` is list of (x1, y1, x2, y2) in mm.
- `import_ses_and_fill(pcb_path, ses_path, stitches=None)` — strip old
  tracks → import SES → optionally add stitches → ZONE_FILLER → save
  (LESSONS_LEARNED §11).

Default Java 21 search ladder (override with JAVA_BIN_CANDIDATES env or
pass `candidates` to find_java21):
- /usr/lib/jvm/java-21-openjdk-amd64/bin/java
- /usr/lib/jvm/temurin-21-jdk-amd64/bin/java
- /opt/homebrew/opt/openjdk@21/bin/java
- `which java` (validated 21+)
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

try:
    import pcbnew
except ImportError:  # pragma: no cover — defer the error to first use
    pcbnew = None  # type: ignore

__all__ = [
    "DEFAULT_JAVA_CANDIDATES",
    "find_java21",
    "ensure_tools",
    "export_specctra_dsn",
    "run_freerouting",
    "add_gnd_stitches",
    "import_ses_and_fill",
]


DEFAULT_JAVA_CANDIDATES = [
    "/usr/lib/jvm/java-21-openjdk-amd64/bin/java",
    "/usr/lib/jvm/temurin-21-jdk-amd64/bin/java",
    "/opt/homebrew/opt/openjdk@21/bin/java",
    "java",
]


def _step(msg: str) -> None:
    print(f"\n=== {msg} ===")


def find_java21(candidates: list | None = None) -> str:
    """Return a path to a Java 21+ runtime, trying common locations.
    Falls back to whatever `java` is on PATH if validated 21+."""
    candidates = candidates or DEFAULT_JAVA_CANDIDATES
    for cand in candidates:
        path = cand if "/" in cand else shutil.which(cand)
        if not path or not Path(path).exists():
            continue
        try:
            out = subprocess.run([path, "-version"],
                                 capture_output=True, text=True,
                                 check=False).stderr
        except Exception:
            continue
        for line in out.splitlines():
            if "version" not in line:
                continue
            try:
                major = int(line.split('"')[1].split(".")[0])
            except (IndexError, ValueError):
                continue
            if major >= 21:
                return path
    raise RuntimeError(
        "Java 21+ not found. Install with `sudo apt install -y "
        "openjdk-21-jre-headless` (Ubuntu) or pass an explicit path.")


def ensure_tools(jar_path: Path, candidates: list | None = None) -> str:
    """Fail-fast: check freerouting JAR exists + return a Java 21+ binary."""
    if not jar_path.exists():
        print(f"ERROR: freerouting JAR not found at {jar_path}", file=sys.stderr)
        print("Download it once with:", file=sys.stderr)
        print(f"  curl -fsSL -o {jar_path} \\", file=sys.stderr)
        print("    https://github.com/freerouting/freerouting/releases/"
              "download/v2.1.0/freerouting-2.1.0.jar", file=sys.stderr)
        sys.exit(2)
    try:
        return find_java21(candidates)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)


def export_specctra_dsn(pcb_path: Path, dsn_path: Path) -> None:
    """Load .kicad_pcb, strip existing tracks, export Specctra DSN.

    Why strip: freerouting v2 LOOKS at existing routing in the DSN and
    decides the board is already mostly routed if many traces exist —
    it then exits after a single pass without writing the SES. By
    starting from a clean state every time we force a full re-route.
    Zones are left intact (they re-fill at the end of the pipeline).
    """
    if pcbnew is None:
        raise ImportError("pcbnew not importable; install KiCad 9 system package")
    _step(f"Exporting DSN ({dsn_path.name})")
    board = pcbnew.LoadBoard(str(pcb_path))

    tracks = list(board.GetTracks())
    for t in tracks:
        board.RemoveNative(t)
    print(f"  Stripped {len(tracks)} existing track/via items before DSN export")

    ok = pcbnew.ExportSpecctraDSN(board, str(dsn_path))
    if not ok:
        print("ERROR: ExportSpecctraDSN returned False", file=sys.stderr)
        sys.exit(3)
    print(f"  → {dsn_path.name} ({dsn_path.stat().st_size // 1024} KB)")
    # IMPORTANT: do NOT save the board here.


def run_freerouting(java_bin: str, jar_path: Path, dsn_path: Path,
                    ses_path: Path, log_path: Path,
                    max_passes: int = 30, threads: int = 4,
                    optim_rounds: int = 5) -> None:
    """Step 3: run freerouting on the DSN to produce the SES."""
    _step("Running freerouting (autorouter)")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if ses_path.exists():
        ses_path.unlink()
    args = [
        "-de", str(dsn_path),
        "-do", str(ses_path),
        "-mp", str(max_passes),
        "-mt", str(threads),
        "-dr", str(optim_rounds),
    ]
    cmd = [java_bin, "-jar", str(jar_path), *args]
    print(f"  {' '.join(cmd)}")
    t0 = time.time()
    with log_path.open("w") as logf:
        rc = subprocess.run(cmd, stdout=logf, stderr=subprocess.STDOUT,
                            check=False).returncode
    elapsed = time.time() - t0
    if rc != 0 or not ses_path.exists():
        print(f"ERROR: freerouting exited {rc} after {elapsed:.1f}s.",
              file=sys.stderr)
        print(f"  Log: {log_path}", file=sys.stderr)
        if log_path.exists():
            tail = log_path.read_text().splitlines()[-15:]
            for line in tail:
                print(f"    {line}", file=sys.stderr)
        sys.exit(4)
    print(f"  → {ses_path.name} ({ses_path.stat().st_size // 1024} KB) "
          f"in {elapsed:.1f}s")


def add_gnd_stitches(board, stitches: list) -> int:
    """Inject explicit B.Cu GND bridge tracks at the given coords.

    `stitches` is a list of (x1, y1, x2, y2) tuples in mm. Each tuple
    becomes a 0.4 mm wide B.Cu track on the /GND net. Useful when the
    ZONE_FILLER would otherwise leave fragments isolated by a fence of
    signal traces (LESSONS_LEARNED §12).
    """
    if pcbnew is None:
        raise ImportError("pcbnew not importable")
    gnd = board.FindNet("/GND")
    if gnd is None:
        print("  [WARN] /GND net not found, skipping stitches")
        return 0
    added = 0
    for x1, y1, x2, y2 in stitches:
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(pcbnew.VECTOR2I(int(x1 * 1e6), int(y1 * 1e6)))
        t.SetEnd(pcbnew.VECTOR2I(int(x2 * 1e6), int(y2 * 1e6)))
        t.SetWidth(int(0.4 * 1e6))
        t.SetLayer(pcbnew.B_Cu)
        t.SetNet(gnd)
        board.Add(t)
        added += 1
    return added


def import_ses_and_fill(pcb_path: Path, ses_path: Path,
                        stitches: list | None = None) -> None:
    """Strip old tracks → import SES → optional stitches → ZONE_FILLER → save."""
    if pcbnew is None:
        raise ImportError("pcbnew not importable")
    _step("Importing SES + filling zones + saving")
    board = pcbnew.LoadBoard(str(pcb_path))

    old = list(board.GetTracks())
    for t in old:
        board.RemoveNative(t)
    if old:
        print(f"  Cleared {len(old)} pre-existing track/via items")

    ok = pcbnew.ImportSpecctraSES(board, str(ses_path))
    if not ok:
        print("ERROR: ImportSpecctraSES returned False", file=sys.stderr)
        sys.exit(5)
    n_tracks = sum(1 for _ in board.GetTracks())
    print(f"  Imported SES → board has {n_tracks} track/via items now")

    if stitches:
        n = add_gnd_stitches(board, stitches)
        print(f"  Added {n} GND stitch(es)")

    filler = pcbnew.ZONE_FILLER(board)
    zones = list(board.Zones())
    filler.Fill(zones)
    print(f"  Filled {len(zones)} zone(s)")

    pcbnew.SaveBoard(str(pcb_path), board)
    print(f"  Saved {pcb_path.name}")
