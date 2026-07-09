#!/usr/bin/env python3
"""
routes.py — Phase 1: propose two candidate route options before full planning.

Used by the roadtrip-webapp (imported via the skill submodule's scripts/
directory on sys.path) and can be called standalone for testing.

Public API
----------
plan_routes(payload, log_fn=None) -> list[dict]
    Returns exactly two route dicts (or falls back to demo_routes).
demo_routes(payload) -> list[dict]
    Offline fallback: derive two coarse variants from curated sample data.
payload_to_text(p) -> str
    Flatten a form payload dict to a short natural-language string.
extract_json(text) -> dict | list
    Tolerantly parse JSON from model output (fences, prose, truncation).
haversine_km(a_lat, a_lng, b_lat, b_lng) -> float
    Great-circle distance in km between two lat/lng points.
"""

import json
import math
import os
import re
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ASSETS = os.path.normpath(os.path.join(_HERE, "..", "assets"))

# Allow importing helper (sibling in scripts/)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import helper as _helper  # noqa: E402

_MODEL = os.environ.get("ROADTRIP_MODEL", "claude-sonnet-4-6")


def _live_mode():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# Shared utilities (also consumed by the webapp)
# --------------------------------------------------------------------------- #

def haversine_km(a_lat, a_lng, b_lat, b_lng):
    R = 6371.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp = math.radians(b_lat - a_lat)
    dl = math.radians(b_lng - a_lng)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(min(1.0, math.sqrt(h)))


def payload_to_text(p):
    bits = []
    if p.get("start"):
        bits.append("from " + p["start"])
    if p.get("destination"):
        bits.append("to " + p["destination"])
    if p.get("days"):
        bits.append("%s days" % p["days"])
    tt = (p.get("tripType") or "").lower()
    if tt in ("round", "roundtrip", "return", "loop"):
        bits.append("round trip")
    elif tt in ("oneway", "one-way", "one_way", "single"):
        bits.append("one way")
    if p.get("startDate"):
        bits.append("starting " + p["startDate"])
    if p.get("party"):
        bits.append(p["party"])
    if p.get("vehicle"):
        bits.append(p["vehicle"] + (" EV" if p["vehicle"] == "EV" else ""))
    return ", ".join(bits)


def _repair_truncated(s):
    """Close a truncated JSON string: walk it tracking string state and the open
    bracket stack, rewind to the last completed value, and append the closers."""
    stack, in_str, esc = [], False, False
    last_safe, last_stack = None, None
    for idx, ch in enumerate(s):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]":
            if stack:
                stack.pop()
            last_safe, last_stack = idx + 1, stack[:]
        elif ch == ",":
            last_safe, last_stack = idx, stack[:]
    if last_safe is None or last_stack is None:
        raise ValueError("could not repair truncated JSON")
    return s[:last_safe] + "".join(reversed(last_stack))


def _escape_inner_quotes(s):
    """Escape bare double quotes that the model left INSIDE string values —
    a recurring slip like  "note": "leaving "Golden Gate" at dawn".

    While inside a string, a quote counts as the real terminator only when the
    next non-whitespace character is structural (one of , : } ] or end of
    text); anything else means the quote was content, so it is escaped. Valid
    JSON passes through unchanged (after every real terminator the next token
    IS structural). Known limit: an embedded quote directly before a comma —
    "we said "hi", then left" — still parses wrong; no lexical fix can tell
    that terminator apart, and the retry layer covers it instead."""
    out, in_str, esc, n = [], False, False, len(s)
    for i, ch in enumerate(s):
        if not in_str:
            if ch == '"':
                in_str = True
            out.append(ch)
            continue
        if esc:
            esc = False
            out.append(ch)
            continue
        if ch == "\\":
            esc = True
            out.append(ch)
            continue
        if ch == '"':
            j = i + 1
            while j < n and s[j] in " \t\r\n":
                j += 1
            if j >= n or s[j] in ",:}]":
                in_str = False
                out.append(ch)          # real terminator
            else:
                out.append('\\"')       # embedded quote — keep it as content
            continue
        out.append(ch)
    return "".join(out)


def extract_json(text):
    """Parse the model's JSON, tolerating code fences, surrounding prose, trailing
    commas, unescaped quotes inside string values, and — crucially — truncation
    (when the response hits max_tokens we salvage the JSON by closing open
    brackets at the last complete element)."""
    t = text.strip()
    if "```" in t:
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", t, re.S)
        if m:
            t = m.group(1)
    i = t.find("{")
    if i > 0:
        t = t[i:]

    candidates = [t]
    j = t.rfind("}")
    if j > 0:
        candidates.append(t[:j + 1])
    for c in candidates:
        try:
            return json.loads(c)
        except Exception:
            pass
        try:
            return json.loads(re.sub(r",\s*([}\]])", r"\1", c))
        except Exception:
            pass

    # unescaped quotes inside string values: repair, then walk the same ladder
    # again (a document can be both malformed and truncated).
    fixed = _escape_inner_quotes(t)
    if fixed != t:
        for c in (fixed, re.sub(r",\s*([}\]])", r"\1", fixed)):
            try:
                return json.loads(c)
            except Exception:
                pass
        try:
            return json.loads(_repair_truncated(re.sub(r",\s*([}\]])", r"\1", fixed)))
        except Exception:
            pass

    # last resort: repair a truncated document
    return json.loads(_repair_truncated(re.sub(r",\s*([}\]])", r"\1", t)))


# --------------------------------------------------------------------------- #
# Phase 1: two quick candidate routes (the user picks one before we expand it)
# --------------------------------------------------------------------------- #

ROUTES_SYSTEM = (
    "You are RoadTrip Navigator, an expert North American road-trip planner. "
    "For the given trip, propose EXACTLY TWO genuinely distinct, realistic, "
    "drivable route options — different enough that a traveler would meaningfully "
    "choose between them (e.g. a faster direct line vs a scenic detour, or two "
    "different geographic corridors). Give each a short label (2-4 words) and a "
    "one-line summary, plus 4-8 MAJOR waypoints in order, each with a real, "
    "accurate decimal latitude/longitude and a one-sentence blurb. Every waypoint "
    "must have a DISTINCT location — never reuse the same coordinates for two "
    "stops. This is a quick preview for route selection, NOT the full itinerary, "
    "so keep it concise. Output ONLY the JSON object specified — no prose, no "
    "markdown fences."
)


def build_routes_user(payload, region):
    schema = ('{"routes":[{"label":str,"summary":str,"totalMiles":int,'
              '"drivingDays":int,"waypoints":[{"name":str,"lat":float,"lng":float,'
              '"blurb":str}]}]}')
    inputs = json.dumps({k: v for k, v in payload.items() if v and k != "route"},
                        ensure_ascii=False)
    lang_rule = ""
    if (payload.get("lang") or "").lower().startswith("zh"):
        lang_rule = ("- Write label/summary/blurb in Simplified Chinese; keep JSON keys in "
                     "English and place names recognizable.\n")
    tt = (payload.get("tripType") or "").lower()
    if tt in ("oneway", "one-way", "one_way", "single"):
        shape = "- Each route ends at the destination (one way, no return leg).\n"
    else:
        shape = "- Each route is a round trip that returns to the starting point.\n"
    return (
        "Propose two route options for these inputs:\n" + inputs + "\n\n"
        "TODAY is " + time.strftime("%Y-%m-%d") + ". Region hint: " + region + ".\n\n"
        + shape + lang_rule +
        "\nOutput ONLY this JSON (exactly two routes):\n" + schema + "\nReturn JSON only."
    )


def _dedup_waypoints(wps):
    """Light de-dup so preview pins don't stack (nudge-only, no network)."""
    placed = []
    n = 0
    for w in wps:
        la, ln = w.get("lat"), w.get("lng")
        if not (isinstance(la, (int, float)) and isinstance(ln, (int, float))):
            la, ln = placed[-1] if placed else (39.5, -98.35)        # US centroid fallback
        if any(haversine_km(la, ln, p[0], p[1]) < 0.5 for p in placed):
            n += 1
            cla, cln = placed[-1] if placed else (la, ln)
            ang = math.radians(n * 137.5)
            r = min(0.05 + 0.02 * n, 0.25)
            la, ln = round(cla + r * math.sin(ang), 5), round(cln + r * math.cos(ang), 5)
        w["lat"], w["lng"] = la, ln
        placed.append((la, ln))
    return wps


def _normalize_routes(data):
    out = []
    for r in ((data or {}).get("routes") or [])[:2]:
        if not isinstance(r, dict):
            continue
        wps = [w for w in (r.get("waypoints") or []) if isinstance(w, dict) and w.get("name")]
        if not wps:
            continue
        _dedup_waypoints(wps)
        out.append({
            "label": r.get("label") or "Route",
            "summary": r.get("summary") or "",
            "totalMiles": r.get("totalMiles"),
            "drivingDays": r.get("drivingDays"),
            "waypoints": wps,
        })
    return out


def plan_routes(payload, log_fn=None):
    """Phase 1: two quick candidate routes. Live by default (one fast model call);
    a tiny offline fallback keeps local/no-key dev from crashing."""
    region = "desert"
    try:
        analysis = _helper.analyze(payload_to_text(payload))
        region = payload.get("region") or analysis["slots"].get("region") or "desert"
    except Exception:
        pass
    if _live_mode():
        try:
            import anthropic
            client = anthropic.Anthropic()
            msg = client.messages.create(
                model=_MODEL, max_tokens=4000, system=ROUTES_SYSTEM,
                messages=[{"role": "user", "content": build_routes_user(payload, region)}])
            text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
            if log_fn:
                log_fn("routes-phase", msg.usage)
            routes = _normalize_routes(extract_json(text))
            if len(routes) >= 2:
                return routes[:2]
        except Exception as e:
            print("[warn] plan_routes live failed: %s" % e, file=sys.stderr)
    return demo_routes(payload)


def demo_routes(payload):
    """Offline/safety fallback: derive two coarse route variants from a curated
    sample so the selection UI still works without an API key."""
    dest = (payload.get("destination", "") + " " + payload.get("start", "")).lower()
    if any(w in dest for w in ["tahoe", "sacramento", "sierra"]):
        fn = "tripData.tahoe.json"
    elif any(w in dest for w in ["vancouver", "canada", "whistler", "seattle", "bc"]):
        fn = "tripData.pnw.json"
    elif any(w in dest for w in ["chicago", "illinois", "indiana", "oak park"]):
        fn = "tripData.chicago.json"
    else:
        fn = "tripData.example.json"
    with open(os.path.join(_ASSETS, fn), "r", encoding="utf-8") as f:
        trip = json.load(f)
    pts = []
    for d in (trip.get("days") or []):
        for s in (d.get("stops") or []):
            if isinstance(s.get("lat"), (int, float)) and isinstance(s.get("lng"), (int, float)):
                pts.append({"name": s.get("name", ""), "lat": s["lat"], "lng": s["lng"],
                            "blurb": s.get("note", "") or ""})
    if not pts:
        pts = [{"name": payload.get("start", "Start"), "lat": 39.5, "lng": -98.35, "blurb": ""}]
    a = pts[:8]
    b = (pts[::2] or pts)[:8]
    return [
        {"label": "Scenic route", "summary": "The full curated path with every stop.",
         "totalMiles": trip.get("totalMiles"), "drivingDays": trip.get("drivingDays"),
         "waypoints": [dict(p) for p in a]},
        {"label": "Highlights route", "summary": "A faster line hitting just the highlights.",
         "totalMiles": trip.get("totalMiles"), "drivingDays": trip.get("drivingDays"),
         "waypoints": [dict(p) for p in b]},
    ]
