#!/usr/bin/env python3
"""
generate.py — turn a tripData JSON file into a single-file, offline-friendly HTML itinerary.

Usage:
    python3 generate.py tripData.json [-o trip.html] [-t template.html]

The template contains the literal token  __TRIP_DATA__  inside a <script> block.
We replace that token with the validated JSON so all view logic stays in the
browser (data/view separation) and the output works without a server.

Design notes (see plan §9):
  * Everything is inlined except Leaflet + OSM tiles, which load from CDN.
    Offline, the map degrades gracefully; the rest of the page still renders.
  * We do a light schema check and emit warnings rather than hard-failing, so a
    partial tripData (MVP / fallback data) still produces a usable page.
"""

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN = "__TRIP_DATA__"

REQUIRED_TOP = ["title", "days"]
REQUIRED_DAY = ["date", "title"]


def warn(msg):
    print("  [warn] " + msg, file=sys.stderr)


def validate(trip):
    """Light, non-fatal validation. Returns list of warnings."""
    warnings = []
    for k in REQUIRED_TOP:
        if k not in trip:
            warnings.append("missing top-level field: %s" % k)

    days = trip.get("days", [])
    if not isinstance(days, list) or not days:
        warnings.append("'days' is empty or not a list")

    has_coords = False
    for i, d in enumerate(days, 1):
        for k in REQUIRED_DAY:
            if k not in d:
                warnings.append("day %d missing field: %s" % (i, k))
        for s in d.get("stops", []) or []:
            if isinstance(s.get("lat"), (int, float)) and isinstance(s.get("lng"), (int, float)):
                if s.get("lat") or s.get("lng"):
                    has_coords = True
    if not has_coords:
        warnings.append("no stop has lat/lng coordinates — the map will be empty")

    b = trip.get("budget")
    if b and "items" in b:
        s = sum(float(it.get("amount", 0) or 0) for it in b["items"])
        if "total" in b and abs(s - float(b["total"])) > 1:
            warnings.append("budget total (%s) != sum of items (%s)" % (b["total"], round(s)))

    if not trip.get("disclaimer"):
        warnings.append("no disclaimer set — a safety disclaimer is strongly recommended")

    return warnings


def build_html(trip, template):
    if TOKEN not in template:
        raise ValueError("template is missing the %s token" % TOKEN)
    # json.dumps is safe to embed in a <script>; guard the only sequence that can
    # break out of a script element.
    payload = json.dumps(trip, ensure_ascii=False, indent=2)
    payload = payload.replace("</script>", "<\\/script>").replace("<!--", "<\\!--")
    # Use a function for replacement so backslashes in the JSON aren't treated as
    # regex backreferences.
    return template.replace(TOKEN, payload)


def syntax_check(html):
    """Best-effort: confirm the injected JSON parses as JSON (since it is also
    valid JS object-literal). Catches malformed data before the user opens it."""
    m = re.search(r"var TRIP_DATA = (\{.*?\});\n// -----", html, re.S)
    if not m:
        return  # token layout changed; skip
    try:
        json.loads(m.group(1))
    except Exception as e:  # pragma: no cover
        raise ValueError("injected TRIP_DATA failed to parse: %s" % e)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Render a tripData JSON into single-file HTML.")
    ap.add_argument("data", help="path to tripData JSON")
    ap.add_argument("-o", "--out", help="output HTML path (default: <data>.html)")
    ap.add_argument("-t", "--template", default=os.path.join(HERE, "template.html"),
                    help="HTML template path")
    args = ap.parse_args(argv)

    with open(args.data, "r", encoding="utf-8") as f:
        trip = json.load(f)
    with open(args.template, "r", encoding="utf-8") as f:
        template = f.read()

    warnings = validate(trip)
    for w in warnings:
        warn(w)

    html = build_html(trip, template)
    syntax_check(html)

    out = args.out or (os.path.splitext(args.data)[0] + ".html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)

    print("Wrote %s (%d days, %d KB)%s" % (
        out, len(trip.get("days", [])), len(html) // 1024,
        "" if not warnings else " — %d warning(s), see above" % len(warnings)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
