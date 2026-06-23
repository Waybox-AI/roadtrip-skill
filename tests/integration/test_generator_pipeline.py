"""
Integration tests: generator pipeline end-to-end.

For each bundled demo JSON file, runs generate.py as a subprocess and asserts:
- exit code 0
- output HTML file exists and is non-empty
- injected TRIP_DATA JSON parses cleanly
- zero unexpected warnings on stderr
- required HTML landmarks are present: <title>, Leaflet map init, bookingCountdown data
"""

import json
import os
import re
import subprocess
import sys

import pytest

ASSETS = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "assets")
)
GENERATE = os.path.join(ASSETS, "generate.py")

DEMO_FILES = [
    "tripData.example.json",
    "tripData.tahoe.json",
    "tripData.pnw.json",
]

# Warnings (stripped "[warn] ..." lines) that are acceptable in the demo files.
# Empty: all three files are complete and should produce zero warnings.
ALLOWED_WARNINGS: set[str] = set()


@pytest.fixture(
    scope="module",
    params=DEMO_FILES,
    ids=lambda f: f.replace("tripData.", "").replace(".json", ""),
)
def pipeline(request, tmp_path_factory):
    """Run generate.py once per demo file; share results across all tests."""
    filename = request.param
    json_path = os.path.join(ASSETS, filename)
    out_dir = tmp_path_factory.mktemp("generated")
    out_path = os.path.join(out_dir, os.path.splitext(filename)[0] + ".html")

    proc = subprocess.run(
        [sys.executable, GENERATE, json_path, "-o", out_path],
        capture_output=True,
        text=True,
    )

    html = ""
    if os.path.exists(out_path):
        with open(out_path, encoding="utf-8") as fh:
            html = fh.read()

    # Extract the embedded JSON payload: `var TRIP_DATA = {...};`
    trip_data = None
    m = re.search(r"var TRIP_DATA = (\{.*?\});\n//", html, re.S)
    if m:
        try:
            trip_data = json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    return {
        "filename": filename,
        "out_path": out_path,
        "proc": proc,
        "html": html,
        "trip_data": trip_data,
    }


# ---------------------------------------------------------------------------
# Assertions
# ---------------------------------------------------------------------------


def test_exit_zero(pipeline):
    assert pipeline["proc"].returncode == 0, (
        f"{pipeline['filename']} — generate.py exited with "
        f"{pipeline['proc'].returncode}:\n{pipeline['proc'].stderr}"
    )


def test_output_file_exists_and_nonempty(pipeline):
    path = pipeline["out_path"]
    assert os.path.exists(path), f"Output file not created: {path}"
    assert os.path.getsize(path) > 0, f"Output file is empty: {path}"


def test_trip_data_json_parses(pipeline):
    assert pipeline["trip_data"] is not None, (
        f"{pipeline['filename']} — could not extract or parse TRIP_DATA JSON "
        "from generated HTML"
    )


def test_no_unexpected_warnings(pipeline):
    warn_lines = [
        line.strip()
        for line in pipeline["proc"].stderr.splitlines()
        if line.strip().startswith("[warn]")
    ]
    unexpected = [w for w in warn_lines if w not in ALLOWED_WARNINGS]
    assert not unexpected, (
        f"{pipeline['filename']} — unexpected warnings:\n" +
        "\n".join(f"  {w}" for w in unexpected)
    )


def test_html_has_title_tag(pipeline):
    assert "<title>" in pipeline["html"], (
        f"{pipeline['filename']} — <title> tag missing from output HTML"
    )


def test_html_has_leaflet_map_init(pipeline):
    assert "L.map(" in pipeline["html"], (
        f"{pipeline['filename']} — Leaflet map initialisation (L.map() call) "
        "missing from output HTML"
    )


def test_html_has_booking_countdown_data(pipeline):
    trip_data = pipeline["trip_data"]
    assert trip_data is not None
    assert "bookingCountdown" in trip_data, (
        f"{pipeline['filename']} — 'bookingCountdown' key missing from TRIP_DATA"
    )
    assert isinstance(trip_data["bookingCountdown"], list), (
        f"{pipeline['filename']} — 'bookingCountdown' is not a list"
    )
    assert len(trip_data["bookingCountdown"]) > 0, (
        f"{pipeline['filename']} — 'bookingCountdown' list is empty"
    )
