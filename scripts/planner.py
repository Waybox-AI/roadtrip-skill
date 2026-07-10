#!/usr/bin/env python3
"""
planner.py — Phase 2: full itinerary generation, single-day regeneration, and
post-processing (endpoint snapping, map-pin de-stacking) for a planned trip.

Used by the roadtrip-webapp (imported via the skill submodule's scripts/
directory on sys.path, same as routes.py) and callable standalone for testing.

Public API
----------
live_mode() -> bool
    True when ANTHROPIC_API_KEY is set and the anthropic package is importable.
generate_trip(payload, live, on_progress=None, log_fn=None) -> dict
    Full flow: plan (live or demo) + schema defaults + endpoint/pin fixups.
    This is the one call the webapp needs — pass it a form payload and get
    back a tripData dict ready for generate.py to render.
plan_live(payload, region, on_progress=None, log_fn=None) -> dict
    One streaming Claude call, framed by SKILL.md + reference.md, that emits
    the full tripData JSON. `on_progress` receives {"step"|"expectedChars"|
    "charsReceived": ...} events a caller can use to drive a progress UI.
plan_demo(payload, region, on_progress=None) -> dict
    Offline fallback: serve the closest curated sample tripData.
regenerate_day(trip, day_index, comment_body, log_fn=None) -> dict
    Rewrite a single day of an existing trip per a commenter's request.
remove_city(trip, day_start, day_end, city_name="", log_fn=None) -> dict
    Trip edit: delete one overnight stop's days, regenerate the single joined
    driving day (one model call), then resequence dates, refresh totals and —
    where a real forecast covers the new dates — weather. Mutates only after
    the model call succeeds; raises on an invalid span or model failure.
set_nights(trip, day_start, day_end, city_name, nights, log_fn=None) -> dict
    Trip edit: change how long one overnight stop lasts. The city's run of
    days is rewritten as `nights` days by one model call (arrival driving leg
    preserved verbatim), then the same deterministic cascade as remove_city
    runs (dates, totals, lodging nights, weather). Same atomicity contract.
revise_stay(trip, day_start, day_end, city_name, instruction, nights=None,
            log_fn=None) -> dict
    Trip edit: rewrite one stay per a free-text traveler request, optionally
    resizing it in the same single model call. Same guards/cascade/atomicity.
fix_endpoints(trip, start, destination) -> None
    Snap the first/last stop coordinates to the real start/destination.
despread_stops(trip) -> None
    Nudge/re-geocode stops whose coordinates collide so map pins separate.
geocode(query, timeout=3.0) -> {"lat","lng"} | None
geocode_near(query, lat, lng, timeout=3.0) -> {"lat","lng"} | None
    Best-effort Photon geocoding (free, no key), the latter biased to a locale.
"""

import datetime
import functools
import json
import math
import os
import re
import sys
import time
import urllib.parse
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.normpath(os.path.join(_HERE, ".."))
_ASSETS = os.path.join(_ROOT, "assets")

# Allow importing routes/helper (siblings in scripts/)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import helper as _helper  # noqa: E402
import routes as _routes  # noqa: E402  (haversine_km, extract_json, payload_to_text)

_MODEL = os.environ.get("ROADTRIP_MODEL", "claude-sonnet-4-6")


def live_mode():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
        return True
    except Exception:
        return False


def _read_doc(name):
    try:
        with open(os.path.join(_ROOT, name), "r", encoding="utf-8") as f:
            return f.read()
    except OSError as e:
        print("[warn] could not read skill doc %s: %s" % (name, e), file=sys.stderr)
        return ""


SKILL_MD = _read_doc("SKILL.md")
REFERENCE_MD = _read_doc("reference.md")

# curated sample itineraries used as the offline/no-key fallback
SAMPLE_FILES = {
    "sw": "tripData.example.json",
    "tahoe": "tripData.tahoe.json",
    "pnw": "tripData.pnw.json",
    "chicago": "tripData.chicago.json",
}


# --------------------------------------------------------------------------- #
# Geocoding / post-processing
# --------------------------------------------------------------------------- #
@functools.lru_cache(maxsize=2048)
def _geocode_cached(key, timeout):
    """Cached implementation — keyed on the normalised query string."""
    res = None
    try:
        url = "https://photon.komoot.io/api/?limit=1&lang=en&q=" + urllib.parse.quote(key)
        req = urllib.request.Request(url, headers={"User-Agent": "roadtrip-navigator/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode())
        feats = d.get("features") or []
        if feats and feats[0].get("geometry"):
            c = feats[0]["geometry"]["coordinates"]   # [lng, lat]
            res = {"lat": round(c[1], 5), "lng": round(c[0], 5)}
    except Exception as e:
        print("[warn] geocode failed for %r: %s" % (key, e), file=sys.stderr)
    return res


def geocode(query, timeout=3.0):
    """Best-effort geocode via Photon (free, no key). Returns {lat,lng} or None."""
    if not query:
        return None
    return _geocode_cached(query.strip().lower(), timeout)


def fix_endpoints(trip, start, destination):
    """Snap the first stop to the real start and the last stop to the real
    destination, so the map endpoints are correct even if the model's coords drift."""
    try:
        days = trip.get("days") or []
        if start and days and (days[0].get("stops")):
            g = geocode(start if "," in start else start + ", USA")
            if g:
                days[0]["stops"][0]["lat"] = g["lat"]
                days[0]["stops"][0]["lng"] = g["lng"]
        if destination and days and (days[-1].get("stops")):
            g = geocode(destination if "," in destination else destination + ", USA")
            if g:
                days[-1]["stops"][-1]["lat"] = g["lat"]
                days[-1]["stops"][-1]["lng"] = g["lng"]
    except Exception as e:
        print("[warn] fix_endpoints failed:", e, file=sys.stderr)


@functools.lru_cache(maxsize=2048)
def _geocode_near_cached(key, lat, lon, timeout):
    """Geocode biased toward (lat, lon) so a name like 'Old Faithful' resolves
    near the trip's own cluster instead of a same-named place elsewhere."""
    res = None
    try:
        url = ("https://photon.komoot.io/api/?limit=1&lang=en&lat=%s&lon=%s&q=%s"
               % (lat, lon, urllib.parse.quote(key)))
        req = urllib.request.Request(url, headers={"User-Agent": "roadtrip-navigator/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode())
        feats = d.get("features") or []
        if feats and feats[0].get("geometry"):
            c = feats[0]["geometry"]["coordinates"]   # [lng, lat]
            res = {"lat": round(c[1], 5), "lng": round(c[0], 5)}
    except Exception as e:
        print("[warn] biased geocode failed for %r: %s" % (key, e), file=sys.stderr)
    return res


def geocode_near(query, lat, lng, timeout=3.0):
    """Best-effort name geocode, biased toward (lat, lng). Returns {lat,lng} or None."""
    if not query:
        return None
    return _geocode_near_cached(query.strip().lower(), round(lat, 2), round(lng, 2), timeout)


def despread_stops(trip):
    """Keep map markers from stacking.

    Only the first/last stops are geocoded (see fix_endpoints); the model's
    coordinates for the stops in between are frequently identical for several
    places in a dense area (e.g. many Yellowstone viewpoints sharing the park's
    coordinates), so those pins pile up and never separate, even when zoomed in.

    For every stop whose coordinates are missing or land within ~120m of one
    we've already placed, re-geocode it by name (biased to the local cluster);
    if that fails or still collides, nudge it onto a small deterministic ring
    around the cluster centre so each stop becomes a distinct, separable pin.
    Stops that are already distinct are left untouched.
    """
    days = trip.get("days") or []

    def valid(s):
        la, ln = s.get("lat"), s.get("lng")
        return isinstance(la, (int, float)) and isinstance(ln, (int, float)) and (la or ln)

    fallback_center = next(((s["lat"], s["lng"])
                            for d in days for s in (d.get("stops") or []) if valid(s)), None)
    if not fallback_center:
        return   # no usable coordinates at all — nothing to do

    placed = []   # accepted (lat, lng) so far

    def collides(la, ln):
        return any(_routes.haversine_km(la, ln, p[0], p[1]) < 0.12 for p in placed)   # ~120m

    nudges = 0
    for day in days:
        for stop in (day.get("stops") or []):
            if valid(stop) and not collides(stop["lat"], stop["lng"]):
                placed.append((stop["lat"], stop["lng"]))
                continue
            cla, cln = placed[-1] if placed else fallback_center   # bias to local cluster
            fixed = None
            g = geocode_near(stop.get("name", ""), cla, cln)
            if g and _routes.haversine_km(g["lat"], g["lng"], cla, cln) <= 150 and not collides(g["lat"], g["lng"]):
                fixed = (g["lat"], g["lng"])           # real, distinct location
            if fixed is None:                          # last resort: spread on a small ring
                nudges += 1
                ang = math.radians(nudges * 137.5)     # golden angle → even spread
                r = min(0.02 + 0.012 * nudges, 0.08)   # ~2-9 km, capped
                fixed = (round(cla + r * math.sin(ang), 5), round(cln + r * math.cos(ang), 5))
            stop["lat"], stop["lng"] = fixed[0], fixed[1]
            placed.append(fixed)


# --------------------------------------------------------------------------- #
# Full itinerary generation (phase 2)
# --------------------------------------------------------------------------- #

# Framing that adapts the multi-step agent skill to this single-shot JSON endpoint.
SKILL_SYSTEM_FRAMING = (
    "You are RoadTrip Navigator, an expert North American road-trip planner.\n"
    "The two documents below are your skill's source of truth — SKILL.md (your "
    "workflow, planning rules, and honesty boundaries) and reference.md "
    "(tripData schema, reliability grading, region cues, tool routing). Follow "
    "their planning intelligence: daily-drive pacing, overnight logic, "
    "reservation lead times and the correct booking system, fuel/EV reasoning, "
    "seasonal closures, cross-border rules, and reliability grading.\n\n"
    "EXECUTION CONTEXT — read carefully: you are running as a single-shot JSON "
    "endpoint, NOT the full agent. You CANNOT call tools, scripts, or web "
    "search, and you must not emit the skill's shell commands or step-by-step "
    "narration. Wherever the skill would call a tool or look something up, make "
    "your best expert estimate and grade it honestly (verified/reference/"
    "estimate) per reference.md. Your ENTIRE output is the single tripData JSON "
    "object specified in the user message — nothing else."
)


def build_messages(payload, region):
    """Return (system_blocks, user_text). The skill brain drives planning via a
    cached system prompt; the user message carries the live inputs and the exact
    renderer output contract (the tripData schema generate.py consumes)."""
    system = [
        {"type": "text", "text": SKILL_SYSTEM_FRAMING},
        {"type": "text", "text": "===== SKILL.md =====\n" + SKILL_MD},
        # one cache breakpoint at the end of the static prefix caches all of the
        # framing + SKILL.md + reference.md across requests (they never change
        # until this module's version changes).
        {"type": "text", "text": "===== reference.md =====\n" + REFERENCE_MD,
         "cache_control": {"type": "ephemeral"}},
    ]
    return system, build_user(payload, region)


def build_user(payload, region):
    schema = """{
 "title": str, "subtitle": str, "dateRange": str, "travelers": str,
 "vehicle": {"type": "gas|EV|RV", "model": str, "mpg": int|null, "rangeMiles": int|null},
 "loopType": "loop|one-way", "totalMiles": int, "drivingDays": int,
 "region": "desert|coast|forest|autumn|mountain",
 "units": {"distance":"mi","temp":"F","currency":"USD"},
 "days": [{"date":"MM/DD","title":str,"from":str,"to":str,"driveMiles":int,
   "driveTime":"Xh YYm","overnight":str|null,"timezoneNote":str?,
   "weather":{"icon":"sunny|partly-cloudy|cloudy|rain|snow|storm|windy|fog","high":int,"low":int},
   "stops":[{"name":str,"type":"park|hike|scenic|city|tour|food|lodging","lat":float,"lng":float,
     "timedEntry":bool?,"ticket":str?,"note":str}],
   "fuelCharging":[{"name":str,"type":"gas|charge","lat":float,"lng":float,"powerKW":int?,"note":str}],
   "meal":{"name":str,"perPerson":int},"risks":[str]}],
 "lodging":[{"name":str,"area":str,"nights":int,"pricePerNight":int,"rating":str,"booked":false}],
 "bookingCountdown":[{"item":str,"bookBy":"YYYY-MM-DD","where":str,"priority":"high|medium|low","note":str}],
 "budget":{"currency":"USD","items":[{"label":str,"amount":int,"reliability":"verified|reference|estimate"}],
   "total":int,"perPerson":int},
 "tips":[str], "disclaimer":str, "generationDate":"YYYY-MM-DD"
}"""
    user = json.dumps({k: v for k, v in payload.items() if v and k != "route"}, ensure_ascii=False)
    eff = payload.get("efficiency")
    if (payload.get("vehicle") or "").lower() == "ev":
        energy_rule = ("- The EV travels about %s miles per kWh. Estimate a realistic current public "
                       "DC fast-charging price ($/kWh) YOURSELF from typical regional rates (the user "
                       "won't know it) and compute the charging budget; show the assumed price in the "
                       "budget line label.\n" % (eff or "3.3"))
    else:
        energy_rule = ("- The vehicle averages about %s MPG. Estimate realistic current gas prices "
                       "($/gal) YOURSELF for the regions on the route (the user won't know them) and "
                       "compute the fuel budget (total miles / MPG x price); show the assumed price in "
                       "the budget line label.\n" % (eff or "26"))
    lang_rule = ""
    if (payload.get("lang") or "").lower().startswith("zh"):
        lang_rule = ("- Write ALL human-readable text (title, subtitle, notes, risks, tips, "
                     "labels, meal/lodging names where natural) in Simplified Chinese. "
                     "Keep JSON keys and enum values (type/reliability/icon/priority) in English, "
                     "and keep place names recognizable (Chinese with English in parentheses is fine).\n")
    # Trip shape is the user's explicit choice — round trip vs one way — and is
    # independent of the day count (5 days can be either). Honor it exactly.
    trip_type = (payload.get("tripType") or "").lower()
    trip_rule = ""
    if trip_type in ("round", "roundtrip", "return", "loop"):
        trip_rule = ("- TRIP SHAPE: ROUND TRIP. The route MUST return to the starting point by the "
                     "final day; set \"loopType\":\"loop\". Pace the days so the loop closes within the "
                     "requested number of days (plan the turnaround around the halfway day).\n")
    elif trip_type in ("oneway", "one-way", "one_way", "single"):
        trip_rule = ("- TRIP SHAPE: ONE WAY. The route ends at the destination and does NOT return to "
                     "the start; set \"loopType\":\"one-way\". Use the full number of days progressing "
                     "from start toward the destination (no return leg).\n")
    # If the user already picked one of the two candidate routes (phase 1), pin the
    # detailed plan to that route's waypoints so we expand exactly what they chose.
    route = payload.get("route") or {}
    wps = route.get("waypoints") or []
    route_rule = ""
    if wps:
        pts = " -> ".join(
            "%s (%.4f, %.4f)" % (w.get("name", "?"), w["lat"], w["lng"])
            for w in wps
            if isinstance(w.get("lat"), (int, float)) and isinstance(w.get("lng"), (int, float)))
        if pts:
            route_rule = ("- CHOSEN ROUTE: the user already picked \"%s\". Build the detailed "
                          "day-by-day itinerary ALONG this route, visiting these major waypoints in "
                          "order: %s. You may add sensible intermediate stops, but keep this overall "
                          "path and its endpoints.\n" % (route.get("label") or "the selected route", pts))
    # Apply your skill's planning rules (SKILL.md + reference.md, in the system
    # prompt) to these inputs, then emit ONLY the tripData JSON. The rules below
    # are the renderer's output contract + this request's runtime parameters —
    # they are NOT a re-statement of how to plan (that lives in the skill).
    return (
        "Plan a realistic, drivable itinerary — applying your skill's rules — for "
        "these inputs:\n" + user + "\n\n"
        "TODAY is " + time.strftime("%Y-%m-%d") + ". Region visual hint: " + region + ".\n\n"
        "Runtime parameters for THIS request:\n"
        + energy_rule + lang_rule + trip_rule + route_rule +
        "\nOutput contract (the renderer consumes this exact shape):\n"
        "- Output ONLY a single JSON object matching this schema — no prose, no markdown fences:\n"
        + schema + "\n"
        '- Strict JSON: any double quote inside a string value must be escaped as \\".\n'
        "- Every stop and fuel/charge point needs real, accurate decimal lat/lng; Day 1's first "
        "stop MUST be the exact start and the final stop MUST be the destination.\n"
        "- 'dateRange' and 'drivingDays' must match the requested number of days; set 'region' to "
        "the best visual match.\n"
        "- budget.total must equal the sum of budget.items and budget.perPerson = total / travelers; "
        "grade every line verified/reference/estimate.\n"
        "- No reservation 'bookBy' date may be before today.\n"
        "- Fill 'disclaimer' with a note to verify against official sources.\n"
        "Return JSON only."
    )


_STRICT_JSON_NUDGE = (
    "\n\nRETRY NOTICE: your previous response was not parseable JSON. Return "
    "STRICT JSON this time — most importantly, any double quote inside a "
    "string value must be escaped as \\\"."
)


def _log_bad_json(where, text, err, stop_reason=None):
    """Preserve the evidence when model JSON fails to parse: the error, the
    stop_reason and the text around the failure position go to stderr, so
    server logs show the root cause instead of a bare JSONDecodeError."""
    pos = getattr(err, "pos", None)
    ctx = ""
    if isinstance(pos, int):
        lo, hi = max(0, pos - 200), min(len(text), pos + 200)
        ctx = " … context @%d: %r" % (pos, text[lo:hi])
    print("[warn] %s: unparseable model JSON (%s; stop_reason=%s; %d chars)%s"
          % (where, err, stop_reason, len(text), ctx), file=sys.stderr)


def _parse_with_retry(text, retry_fn, where, stop_reason=None):
    """extract_json with one second chance: on failure, log the evidence and
    let `retry_fn() -> (text, stop_reason)` ask the model again (a JSON slip
    is a dice roll — one retry removes almost all user-visible failures)."""
    try:
        return _routes.extract_json(text)
    except Exception as e:
        _log_bad_json(where, text, e, stop_reason)
    text2, stop2 = retry_fn()
    try:
        return _routes.extract_json(text2)
    except Exception as e:
        _log_bad_json(where + " (retry)", text2, e, stop2)
        raise


def plan_live(payload, region, on_progress=None, log_fn=None):
    """Live phase-2 generation: one streaming Claude call framed by the skill's
    own docs (plus one automatic retry if the response isn't parseable JSON).
    `on_progress(event)` (if given) is called with small dicts as JSON
    streams in so a caller can reflect progress:
      - {"expectedChars": n}  once, before streaming starts
      - {"charsReceived": n}  on every chunk (fine-grained ETA signal)
      - {"step": idx}         when a coarse phase threshold is crossed
    `log_fn(usage)` (if given) receives each call's token-usage object."""
    import anthropic
    client = anthropic.Anthropic()
    system, prompt = build_messages(payload, region)

    def emit(event):
        if on_progress:
            on_progress(event)

    emit({"step": 1})
    # advance status as the JSON streams in (token-count milestones = real signal).
    # Expected length scales with day count so the thresholds — and therefore the
    # ETA derived from charsReceived/expectedChars — stay meaningful for both a
    # quick 2-day trip and a sprawling 3-week one.
    try:
        n_days = max(1, min(21, int(payload.get("days") or 5)))
    except (TypeError, ValueError):
        n_days = 5
    expected_chars = n_days * 1100           # e.g. 5d→5500, 7d→7700, 14d→15400
    thresholds = [
        (int(expected_chars * 0.15), 2),     # route (~15% in)
        (int(expected_chars * 0.37), 3),     # segment (~37% in)
        (int(expected_chars * 0.67), 4),     # budget/research (~67% in)
    ]
    emit({"expectedChars": expected_chars})

    def stream_once(p):
        text = ""
        with client.messages.stream(model=_MODEL, max_tokens=16000, system=system,
                                    messages=[{"role": "user", "content": p}]) as stream:
            for chunk in stream.text_stream:
                text += chunk
                emit({"charsReceived": len(text)})
                for n, step in thresholds:
                    if len(text) >= n:
                        emit({"step": step})
            final = stream.get_final_message()   # carries the authoritative token usage
        if log_fn:
            log_fn(final.usage)
        return text, getattr(final, "stop_reason", None)

    text, stop = stream_once(prompt)
    return _parse_with_retry(
        text, lambda: stream_once(prompt + _STRICT_JSON_NUDGE), "plan_live", stop)


def plan_demo(payload, region, on_progress=None):
    """No API key: serve the closest curated demo so the page always works."""
    dest = (payload.get("destination", "") + " " + payload.get("start", "")).lower()
    if any(w in dest for w in ["tahoe", "sacramento", "sierra"]):
        fn = "tripData.tahoe.json"
    elif any(w in dest for w in ["vancouver", "canada", "whistler", "seattle", "bc"]):
        fn = "tripData.pnw.json"
    elif any(w in dest for w in ["chicago", "illinois", "indiana dunes", "starved rock", "oak park"]):
        fn = "tripData.chicago.json"
    else:
        fn = "tripData.example.json"
    with open(os.path.join(_ASSETS, fn), "r", encoding="utf-8") as f:
        trip = json.load(f)
    # walk the status steps so the UX is visible
    for i in range(1, 5):
        if on_progress:
            on_progress({"step": i})
        time.sleep(1.0)
    trip["_demoNote"] = ("Demo mode: showing a curated sample itinerary. Set an "
                         "ANTHROPIC_API_KEY to generate a fresh plan for your exact input.")
    # reflect the user's framing where harmless
    if payload.get("start") or payload.get("destination"):
        trip["subtitle"] = (trip.get("subtitle", "") +
                            "  ·  (demo sample for: %s)" % _routes.payload_to_text(payload))
    return trip


def generate_trip(payload, live, on_progress=None, log_fn=None):
    """The one call a caller needs: plan (live or demo), stamp schema defaults
    (language, generation date, disclaimer), and apply endpoint/pin post-
    processing. Returns a tripData dict ready for generate.py to render."""
    region = payload.get("region")
    if not region:
        try:
            region = _helper.analyze(_routes.payload_to_text(payload))["slots"].get("region")
        except Exception:
            region = None
    region = region or "desert"

    if live:
        trip = plan_live(payload, region, on_progress=on_progress, log_fn=log_fn)
    else:
        trip = plan_demo(payload, region, on_progress=on_progress)

    # Stamp the generation language so shared pages render in the same language.
    trip_lang = (payload.get("lang") or "en").lower()
    trip["lang"] = "zh" if trip_lang.startswith("zh") else "en"
    trip.setdefault("generationDate", time.strftime("%Y-%m-%d"))
    if trip["lang"] == "zh":
        trip.setdefault("disclaimer",
                        "内容由 AI 整理，可能存在偏差——出行前请以官方渠道核实"
                        "营业时间、价格、预订及道路/边境状况。")
    else:
        trip.setdefault("disclaimer",
                        "AI-assembled and may be out of date — verify hours, prices, "
                        "reservations and road/border conditions with official sources.")
    if live:
        fix_endpoints(trip, payload.get("start"), payload.get("destination"))
    despread_stops(trip)   # stop coincident map pins from stacking (see docstring)
    return trip


def _regenerate_day_with_instruction(trip, day_index, instruction, log_fn=None):
    """Single-shot model call that rewrites one trip day per `instruction`
    (a complete sentence describing the change). Shared by regenerate_day
    (comments) and remove_city (trip editing). Raises on failure."""
    import anthropic
    client = anthropic.Anthropic()
    days = trip.get("days") or []
    day = days[day_index]
    days_summary = "\n".join(
        "Day %d (%s): %s  [%s → %s]" % (
            i + 1, d.get("date", ""), d.get("title", ""),
            d.get("from", ""), d.get("to", ""))
        for i, d in enumerate(days)
    )
    prev_to   = days[day_index - 1].get("to", "") if day_index > 0 else ""
    next_from = days[day_index + 1].get("from", "") if day_index + 1 < len(days) else ""
    continuity = ""
    if prev_to:
        continuity += "The previous day (Day %d) ends at '%s'. " % (day_index, prev_to)
    if next_from:
        continuity += "The next day (Day %d) starts at '%s'. " % (day_index + 2, next_from)
    schema = (
        '{"date":str,"title":str,"from":str,"to":str,"driveMiles":int,"driveTime":str,'
        '"overnight":str|null,"timezoneNote":str?,'
        '"weather":{"icon":"sunny|partly-cloudy|cloudy|rain|snow|storm|windy|fog","high":int,"low":int},'
        '"stops":[{"name":str,"type":"park|hike|scenic|city|tour|food|lodging",'
        '"lat":float,"lng":float,"note":str}],'
        '"fuelCharging":[{"name":str,"type":"gas|charge","lat":float,"lng":float,"note":str}],'
        '"meal":{"name":str,"perPerson":int},"risks":[str]}'
    )
    prompt = (
        "You are updating one day of an existing road trip itinerary.\n\n"
        "Trip: %s\n"
        "All days (for continuity context):\n%s\n\n"
        "Current Day %d:\n%s\n\n"
        "%s\n\n"
        "Rewrite ONLY Day %d to honour this request. %s"
        "Keep the same 'date' value. Use accurate lat/lng for all stops. "
        "Output ONLY the JSON object for this single day — no prose, no markdown "
        "fences; any double quote inside a string value must be escaped as \\\":\n%s\n"
        "Return JSON only."
    ) % (
        trip.get("title", ""),
        days_summary,
        day_index + 1,
        json.dumps(day, ensure_ascii=False, indent=2),
        instruction,
        day_index + 1,
        continuity,
        schema,
    )
    def create_once(p):
        msg = client.messages.create(
            model=_MODEL, max_tokens=4000,
            messages=[{"role": "user", "content": p}])
        t = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
        if log_fn:
            log_fn(msg.usage)
        return t, getattr(msg, "stop_reason", None)

    text, stop = create_once(prompt)
    new_day = _parse_with_retry(
        text, lambda: create_once(prompt + _STRICT_JSON_NUDGE),
        "regenerate_day", stop)
    # Preserve the original date so the calendar doesn't drift.
    new_day["date"] = day.get("date", new_day.get("date", ""))
    return new_day


def regenerate_day(trip, day_index, comment_body, log_fn=None):
    """Ask the AI to rewrite a single trip day based on a commenter's suggestion.

    Only the targeted day is regenerated; all other days remain unchanged.
    Returns the updated day dict (same schema as an element of trip["days"]).
    Raises on failure so callers can decide whether to surface or swallow the error.
    """
    return _regenerate_day_with_instruction(
        trip, day_index,
        "A traveler requests this change: \"%s\"" % comment_body,
        log_fn=log_fn)


def _s(v):
    """Text of a possibly-null model field. `str(None)` would leak the literal
    "None" into match strings and rendered entries."""
    return "" if v is None else str(v)


def _coerce_miles(v):
    """Model mileage as an int. Accepts 150, 150.0, "150", "150 mi"; rejects
    booleans (isinstance(True, int) is True) and anything unparseable."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(v)
    m = re.search(r"-?\d+(?:\.\d+)?", _s(v))
    return int(float(m.group())) if m else None


def _stay_lodging(trip, city_name):
    """The lodging entry for a stay's city, or None. Cheap name/area match —
    same heuristic as _set_lodging_nights."""
    if not (city_name or "").strip() or not isinstance(trip.get("lodging"), list):
        return None
    needle = city_name.strip().lower()
    core = needle.split(",")[0].strip()
    word = re.compile(r"\b%s\b" % re.escape(core)) if core else None
    for l in trip["lodging"]:
        t = ("%s %s" % (_s(l.get("name")), _s(l.get("area")))).lower()
        if needle in t or (word and word.search(t)):
            return l
    return None


def _stop_key(name):
    """'Antelope Canyon (guided tour)' -> 'antelope canyon' — the part of a stop
    name that a booking entry is likely to echo."""
    s = re.sub(r"\(.*?\)", " ", str(name or "")).lower()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) >= 6 else ""


def _stay_bookings(trip, city_name, span_days=None):
    """Booking-countdown entries belonging to a stay.

    Matched by the city name OR by any stop in the stay's days — plenty of
    bookings never name the town ("Antelope Canyon guided tour" belongs to the
    Page stay), and those are exactly the ones travelers ask to drop."""
    if not isinstance(trip.get("bookingCountdown"), list):
        return []
    needles = []
    if (city_name or "").strip():
        needle = city_name.strip().lower()
        needles.append(needle)
        core = needle.split(",")[0].strip()
        if core:
            needles.append(core)
    for d in (span_days or []):
        for s in (d.get("stops") or []):
            k = _stop_key(s.get("name"))
            if k:
                needles.append(k)
    out = []
    for b in trip["bookingCountdown"]:
        t = ("%s %s" % (_s(b.get("item")), _s(b.get("where")))).lower()
        if any(n in t for n in needles):
            out.append(b)
    return out


def _regenerate_span_with_instruction(trip, day_start, day_end, out_count,
                                      instruction, city_name="", log_fn=None):
    """Single-shot model call that rewrites a run of consecutive days as
    EXACTLY `out_count` replacement days per `instruction`. The wire format is
    an object — {"days": [...], "lodging"?: {...}, "bookingCountdown"?: [...]} —
    so a request like "swap that hotel" or "skip the permit" can also update the
    trip-level sections that belong to this stay.

    Returns (new_days, lodging_or_None, bookings_or_None); raises on failure or
    day-count mismatch."""
    import anthropic
    client = anthropic.Anthropic()
    days = trip.get("days") or []
    span = days[day_start:day_end + 1]
    cur_lodging = _stay_lodging(trip, city_name)
    cur_bookings = _stay_bookings(trip, city_name, span)
    days_summary = "\n".join(
        "Day %d (%s): %s  [%s → %s]" % (
            i + 1, d.get("date", ""), d.get("title", ""),
            d.get("from", ""), d.get("to", ""))
        for i, d in enumerate(days)
    )
    prev_to   = days[day_start - 1].get("to", "") if day_start > 0 else ""
    next_from = days[day_end + 1].get("from", "") if day_end + 1 < len(days) else ""
    continuity = ""
    if prev_to:
        continuity += "The day before this run ends at '%s'. " % prev_to
    if next_from:
        continuity += "The day after this run starts at '%s'. " % next_from
    day_schema = (
        '{"date":str,"title":str,"from":str,"to":str,"driveMiles":int,"driveTime":str,'
        '"overnight":str|null,"timezoneNote":str?,'
        '"weather":{"icon":"sunny|partly-cloudy|cloudy|rain|snow|storm|windy|fog","high":int,"low":int},'
        '"stops":[{"name":str,"type":"park|hike|scenic|city|tour|food|lodging",'
        '"lat":float,"lng":float,"note":str}],'
        '"fuelCharging":[{"name":str,"type":"gas|charge","lat":float,"lng":float,"note":str}],'
        '"meal":{"name":str,"perPerson":int},"risks":[str]}'
    )
    # Trip-level sections that belong to this stay: hand them over so requests
    # like "swap that hotel" or "drop the tour booking" can actually land.
    extras, extra_schema = "", ""
    if cur_lodging is not None:
        extras += ("\nThis stay's lodging entry:\n%s\n"
                   % json.dumps(cur_lodging, ensure_ascii=False))
        extra_schema += (
            ',\n "lodging": {"name":str,"area":str,"pricePerNight":int,"rating":str}'
            "   // OPTIONAL — include ONLY if the request changes where they sleep"
            " (a different hotel, cheaper, closer). Omit 'nights' and 'booked'.")
    if cur_bookings:
        extras += ("\nThis stay's booking-countdown entries:\n%s\n"
                   % json.dumps(cur_bookings, ensure_ascii=False))
        extra_schema += (
            ',\n "bookingCountdown": [{"item":str,"bookBy":"YYYY-MM-DD","where":str,'
            '"priority":"high|medium|low","note":str}]'
            "   // OPTIONAL — include ONLY if the request changes what must be"
            " reserved for this stay; return the FULL replacement list for it"
            " (empty list = drop them all). No bookBy date before today.")
    prompt = (
        "You are updating a run of consecutive days in an existing road trip itinerary.\n\n"
        "Trip: %s\nTODAY is %s.\n"
        "All days (for continuity context):\n%s\n\n"
        "Current run — Days %d to %d:\n%s\n%s\n"
        "%s\n\n"
        "Rewrite ONLY this run, as EXACTLY %d day(s) total. %s"
        "You MAY update this run's driving distance/time, stops, meals, fuel/charging, "
        "risks%s — whatever the request calls for. Use accurate lat/lng for all stops.\n"
        "Output ONLY a JSON object — no prose, no markdown fences; any double quote "
        'inside a string value must be escaped as \\". Shape:\n'
        '{\n "days": [day, ...]   // EXACTLY %d element(s)%s\n}\n'
        "Each day matches: %s\n"
        "Return JSON only."
    ) % (
        trip.get("title", ""),
        time.strftime("%Y-%m-%d"),
        days_summary,
        day_start + 1, day_end + 1,
        json.dumps(span, ensure_ascii=False, indent=2),
        extras,
        instruction,
        out_count,
        continuity,
        (", the hotel and the bookings for this stay"
         if (cur_lodging is not None or cur_bookings) else ""),
        out_count,
        extra_schema,
        day_schema,
    )

    def create_once(p):
        msg = client.messages.create(
            model=_MODEL, max_tokens=min(16000, 2500 + 2600 * out_count),
            messages=[{"role": "user", "content": p}])
        t = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
        if log_fn:
            log_fn(msg.usage)
        return t, getattr(msg, "stop_reason", None)

    text, stop = create_once(prompt)
    got = _parse_with_retry(
        text, lambda: create_once(prompt + _STRICT_JSON_NUDGE),
        "regenerate_span", stop)
    new_days = got.get("days") if isinstance(got, dict) else None
    if (not isinstance(new_days, list) or len(new_days) != out_count
            or not all(isinstance(d, dict) for d in new_days)):
        raise ValueError("model returned %s day(s) for the run, expected %d"
                         % (len(new_days) if isinstance(new_days, list) else "no",
                            out_count))
    new_lodging = got.get("lodging")
    if not isinstance(new_lodging, dict) or not new_lodging.get("name"):
        new_lodging = None
    new_bookings = got.get("bookingCountdown")
    if not isinstance(new_bookings, list) or not all(
            isinstance(b, dict) and b.get("item") for b in new_bookings):
        new_bookings = None
    return new_days, new_lodging, new_bookings


# --------------------------------------------------------------------------- #
# Trip editing (phase 3): remove one overnight stop from an existing trip
# --------------------------------------------------------------------------- #

def _trip_start_date(trip):
    """datetime.date of Day 1, or None when it can't be derived. Month/day come
    from days[0].date ('MM/DD'); the year from dateRange ('YYYY-MM-DD ~ …'),
    falling back to generationDate."""
    days = trip.get("days") or []
    if not days:
        return None
    m = re.match(r"^\s*(\d{1,2})/(\d{1,2})", str(days[0].get("date") or ""))
    if not m:
        return None
    year = None
    for field in ("dateRange", "generationDate"):
        ym = re.match(r"\s*(\d{4})-", str(trip.get(field) or ""))
        if ym:
            year = int(ym.group(1))
            break
    if not year:
        return None
    try:
        return datetime.date(year, int(m.group(1)), int(m.group(2)))
    except ValueError:
        return None


def _resequence_dates(trip):
    """Rewrite every day's 'MM/DD' date as Day1+k and rebuild dateRange.
    Returns the per-day ISO dates (aligned with trip['days']), or None when
    the trip's dates can't be parsed — nothing is changed in that case."""
    start = _trip_start_date(trip)
    if not start:
        return None
    iso = []
    for k, d in enumerate(trip.get("days") or []):
        cur = start + datetime.timedelta(days=k)
        d["date"] = cur.strftime("%m/%d")
        iso.append(cur.strftime("%Y-%m-%d"))
    if iso:
        trip["dateRange"] = "%s ~ %s" % (iso[0], iso[-1])
    return iso


def _weather_forecast(lat, lng):
    """Real per-day forecast via tools/weather_client (NWS, free, no key).
    Returns the client's dict, or None on any failure — trip editing must keep
    working fully offline."""
    try:
        if _ROOT not in sys.path:
            sys.path.insert(0, _ROOT)
        from tools import weather_client
        return weather_client.forecast(lat, lng)
    except Exception as e:
        print("[warn] weather refresh unavailable: %s" % e, file=sys.stderr)
        return None


def _refresh_weather(trip, first_idx, iso_dates):
    """Overwrite weather with a real forecast for every day from `first_idx` on
    (their calendar dates just changed), where the forecast actually covers the
    new date; other days keep the model's estimate. Best-effort, never raises."""
    if not iso_dates:
        return
    days = trip.get("days") or []
    cache = {}
    for i in range(max(first_idx, 0), len(days)):
        d = days[i]
        stop = next((s for s in reversed(d.get("stops") or [])
                     if isinstance(s.get("lat"), (int, float))
                     and isinstance(s.get("lng"), (int, float))), None)
        if not stop:
            continue
        key = (round(stop["lat"], 1), round(stop["lng"], 1))
        if key not in cache:
            cache[key] = _weather_forecast(stop["lat"], stop["lng"]) or {}
        fc = cache[key]
        if fc.get("source") != "nws":
            continue   # fallback shape = no real data for this location
        hit = next((x for x in (fc.get("days") or [])
                    if x.get("date") == iso_dates[i]), None)
        if not hit:
            continue   # date beyond the forecast window — keep the estimate
        w = d.get("weather") or {}
        w["icon"] = hit.get("icon") or w.get("icon") or "partly-cloudy"
        if isinstance(hit.get("high"), (int, float)):
            w["high"] = int(hit["high"])
        if isinstance(hit.get("low"), (int, float)):
            w["low"] = int(hit["low"])
        d["weather"] = w


def _mi(day):
    """driveMiles as an int, tolerating missing/garbage model values."""
    return _coerce_miles(day.get("driveMiles")) or 0


def _set_lodging_nights(trip, city_name, nights):
    """Keep the lodging list consistent with a stay-length change: entries
    referencing the city get the new night count (same cheap matching as
    _drop_city_references)."""
    if not (city_name or "").strip() or not isinstance(trip.get("lodging"), list):
        return
    needle = city_name.strip().lower()
    core = needle.split(",")[0].strip()
    word = re.compile(r"\b%s\b" % re.escape(core)) if core else None
    for l in trip["lodging"]:
        t = ("%s %s" % (_s(l.get("name")), _s(l.get("area")))).lower()
        if needle in t or (word and word.search(t)):
            l["nights"] = nights


def _drop_city_references(trip, city_name):
    """Drop lodging / booking-countdown lines that reference the removed city,
    so the visible page doesn't keep advertising a hotel we no longer stay at."""
    if not (city_name or "").strip():
        return
    needle = city_name.strip().lower()
    core = needle.split(",")[0].strip()
    word = re.compile(r"\b%s\b" % re.escape(core)) if core else None

    def refers(text):
        t = (text or "").lower()
        return needle in t or bool(word and word.search(t))

    if isinstance(trip.get("lodging"), list):
        trip["lodging"] = [l for l in trip["lodging"]
                           if not refers("%s %s" % (_s(l.get("name")), _s(l.get("area"))))]
    if isinstance(trip.get("bookingCountdown"), list):
        trip["bookingCountdown"] = [b for b in trip["bookingCountdown"]
                                    if not refers("%s %s" % (_s(b.get("item")), _s(b.get("where"))))]


def remove_city(trip, day_start, day_end, city_name="", log_fn=None):
    """Remove one overnight stop (days [day_start..day_end], 0-based inclusive)
    from an existing trip and stitch the itinerary back together.

    One model call rewrites the joined driving day (previous overnight → the
    removed stop's successor); everything else is deterministic: later days
    shift earlier, drivingDays/totalMiles/dateRange are recomputed, lodging and
    booking-countdown lines for the removed city are dropped, and weather is
    refreshed from a real forecast where one covers the shifted dates.

    The trip's first and last day can never be removed. The trip dict is only
    mutated after the model call succeeds, so a failed edit never leaves a
    half-edited trip for callers to persist.
    """
    days = trip.get("days") or []
    n = len(days)
    if n < 3:
        raise ValueError("trip is too short to edit")
    if not (1 <= day_start <= day_end <= n - 2):
        raise ValueError("span must keep the trip's first and last day")

    old_day_count = n
    old_total_miles = trip.get("totalMiles") if isinstance(
        trip.get("totalMiles"), (int, float)) else 0
    join_idx = day_end + 1
    join_day = days[join_idx]
    prev_day = days[day_start - 1]
    new_from = prev_day.get("overnight") or prev_day.get("to") or ""
    old_to   = join_day.get("to") or ""
    removed  = (city_name or days[day_start].get("overnight")
                or join_day.get("from") or "that stop")
    instruction = (
        "The overnight stop '%s' has been REMOVED from the trip. This day "
        "previously drove '%s' -> '%s'. Rewrite it as ONE day driving DIRECTLY "
        "from '%s' to '%s': recompute driveMiles and driveTime realistically for "
        "that direct route, choose stops and fuel/charging along the direct route "
        "only, and do not route through or mention '%s'."
        % (removed, join_day.get("from", ""), old_to, new_from, old_to, removed)
    )
    new_join = _regenerate_day_with_instruction(trip, join_idx, instruction, log_fn=log_fn)
    # The model rewrote the leg's content; its endpoints are ours to enforce.
    new_join["from"] = new_from
    new_join["to"] = old_to
    new_join["overnight"] = join_day.get("overnight")

    removed_miles = sum(_mi(d) for d in days[day_start:join_idx + 1])
    trip["days"] = days[:day_start] + [new_join] + days[join_idx + 1:]
    trip["drivingDays"] = len(trip["days"])
    if isinstance(trip.get("totalMiles"), (int, float)):
        delta = _mi(new_join) - removed_miles
        trip["totalMiles"] = max(0, int(trip["totalMiles"]) + delta)

    iso = _resequence_dates(trip)
    _drop_city_references(trip, city_name)
    _recompute_budget(trip, old_day_count, old_total_miles)
    _refresh_weather(trip, day_start, iso)
    despread_stops(trip)   # the rewritten day may introduce coincident pins
    return trip


def set_nights(trip, day_start, day_end, city_name, nights, log_fn=None):
    """Change how long one overnight stop lasts: the city's run of days
    [day_start..day_end] is rewritten as `nights` days by one model call, then
    the same deterministic cascade as remove_city runs (dates, totals, lodging
    night counts, weather, pin de-stacking).

    Unlike remove_city, a run anchored to the trip's FIRST day is editable —
    the arrival day always survives with its driving leg preserved verbatim;
    only the stay length changes. The trip's final day stays untouched.

    The trip dict is mutated only after the model call succeeds, so a failed
    edit never leaves a half-edited trip for callers to persist.
    """
    days = trip.get("days") or []
    n = len(days)
    if n < 2:
        raise ValueError("trip is too short to edit")
    if not (0 <= day_start <= day_end <= n - 2):
        raise ValueError("span must lie before the trip's final day")
    try:
        nights = int(nights)
    except (TypeError, ValueError):
        raise ValueError("invalid night count")
    current = day_end - day_start + 1
    if not (1 <= nights <= 7):
        raise ValueError("nights must be between 1 and 7")
    if nights == current:
        raise ValueError("stay is already %d night(s) long" % current)
    if n - current + nights > 21:
        raise ValueError("trip would exceed 21 days")

    return _replan_stay(trip, day_start, day_end, city_name, nights, "", log_fn)


def _replan_stay(trip, day_start, day_end, city_name, out_count, extra_request, log_fn):
    """Shared engine behind set_nights / revise_stay: rewrite one stay's run as
    `out_count` days via a single model call (honoring an optional traveler
    request), then run the deterministic cascade. Callers own the validation."""
    days = trip.get("days") or []
    arrival = days[day_start]
    city = city_name or arrival.get("overnight") or "that stop"
    current = day_end - day_start + 1
    parts = []
    if out_count != current:
        parts.append("The traveler changed the stay at '%s' from %d to %d night(s)."
                     % (city, current, out_count))
    else:
        parts.append("The traveler wants this %d-night stay at '%s' replanned."
                     % (current, city))
    if extra_request:
        parts.append("Traveler request — honor it as the top priority: \"%s\"."
                     % extra_request)
    parts.append(
        "Replan this run: the FIRST day still drives '%s' -> '%s' (currently "
        "%s mi, %s) — keep those endpoints, but its sightseeing, and therefore "
        "its distance and time, may change; every other day stays local around "
        "'%s'. Redistribute the area's best sights across the new length — drop "
        "the least essential ones when shrinking, add worthwhile nearby ones "
        "when growing."
        % (arrival.get("from", ""), arrival.get("to", ""),
           arrival.get("driveMiles", "?"), arrival.get("driveTime", "?"),
           city))
    instruction = " ".join(parts)
    old_day_count = len(days)
    old_total_miles = trip.get("totalMiles") if isinstance(
        trip.get("totalMiles"), (int, float)) else 0
    old_span = days[day_start:day_end + 1]
    stale_bookings = _stay_bookings(trip, city, old_span)
    new_run, new_lodging, new_bookings = _regenerate_span_with_instruction(
        trip, day_start, day_end, out_count, instruction,
        city_name=city, log_fn=log_fn)

    # Anchors are ours to enforce: the stay's identity (overnight) and where the
    # arrival leg starts and ends. Its distance/time may now change — a scenic
    # detour on the way in must show up in the mileage, not be silently reverted.
    overnight = arrival.get("overnight")
    for k, d in enumerate(new_run):
        d["overnight"] = overnight
        if k == 0:
            d["from"] = arrival.get("from", "")
            d["to"] = arrival.get("to", "")
            miles = _coerce_miles(d.get("driveMiles"))
            d["driveMiles"] = miles if miles is not None else arrival.get("driveMiles")
            drive_time = _s(d.get("driveTime")).strip()
            d["driveTime"] = drive_time or arrival.get("driveTime")
            # Day 1 of the trip anchors date resequencing — when the run is
            # start-anchored the model's date must never displace the calendar.
            d["date"] = arrival.get("date", d.get("date", ""))
        else:
            d["from"] = overnight or d.get("from", "")
            d["to"] = overnight or d.get("to", "")

    old_miles = sum(_mi(d) for d in days[day_start:day_end + 1])
    trip["days"] = days[:day_start] + new_run + days[day_end + 1:]
    trip["drivingDays"] = len(trip["days"])
    if isinstance(trip.get("totalMiles"), (int, float)):
        delta = sum(_mi(d) for d in new_run) - old_miles
        trip["totalMiles"] = max(0, int(trip["totalMiles"]) + delta)

    _apply_stay_lodging(trip, city, new_lodging, out_count)
    _apply_stay_bookings(trip, stale_bookings, new_bookings)
    if out_count != current:
        _set_lodging_nights(trip, city, out_count)
    iso = _resequence_dates(trip)
    _recompute_budget(trip, old_day_count, old_total_miles)
    _refresh_weather(trip, day_start, iso)
    despread_stops(trip)
    return trip


def _apply_stay_lodging(trip, city_name, new_lodging, nights):
    """Swap in the model's replacement hotel for this stay. The night count
    stays ours (it follows the edit, not the model) and `booked` resets to
    False — it's a different property. No-op when the model proposed none."""
    if not new_lodging:
        return
    cur = _stay_lodging(trip, city_name)
    entry = {
        "name": _s(new_lodging.get("name")).strip()[:120],
        "area": _s(new_lodging.get("area") or (cur or {}).get("area") or city_name)[:120],
        "nights": nights,
        "booked": False,
    }
    price = new_lodging.get("pricePerNight")
    if isinstance(price, (int, float)) and price >= 0:
        entry["pricePerNight"] = int(price)
    elif cur and "pricePerNight" in cur:
        entry["pricePerNight"] = cur["pricePerNight"]
    rating = _s(new_lodging.get("rating")).strip()
    if rating:
        entry["rating"] = rating[:16]
    elif cur and cur.get("rating"):
        entry["rating"] = cur["rating"]
    if cur is not None:
        cur.clear()
        cur.update(entry)
    else:
        trip.setdefault("lodging", []).append(entry)


def _apply_stay_bookings(trip, stale, new_bookings):
    """Replace this stay's booking-countdown entries (`stale`, matched BEFORE the
    days were spliced) with the model's list — an empty list means the request
    dropped them. No-op when the model omitted the key, so unrelated bookings are
    never disturbed."""
    if new_bookings is None or not isinstance(trip.get("bookingCountdown"), list):
        return
    keep = [b for b in trip["bookingCountdown"] if b not in stale]
    cleaned = []
    for b in new_bookings:
        item = _s(b.get("item")).strip()
        if not item:
            continue
        entry = {"item": item[:160],
                 "bookBy": _s(b.get("bookBy")).strip()[:10],
                 "where": _s(b.get("where")).strip()[:120],
                 "priority": (b.get("priority")
                              if b.get("priority") in ("high", "medium", "low")
                              else "medium")}
        note = _s(b.get("note")).strip()
        if note:
            entry["note"] = note[:240]
        cleaned.append(entry)
    trip["bookingCountdown"] = keep + cleaned


# --------------------------------------------------------------------------- #
# Budget recomputation (deterministic — no model call)
# --------------------------------------------------------------------------- #

_LODGING_WORDS = ("lodging", "hotel", "accommodation", "stay",
                  "\u4f4f\u5bbf", "\u9152\u5e97")          # 住宿 / 酒店
_FUEL_WORDS = ("fuel", "gas", "gasoline", "charging", "electricity",
               "\u71c3\u6cb9", "\u6cb9\u8d39", "\u52a0\u6cb9",
               "\u5145\u7535", "\u7535\u8d39")             # 燃油/油费/加油/充电/电费
_DAYS_RE = re.compile(r"(\d+)\s*(days?|\u5929)", re.I)       # "7 days" / "7 天"
_NIGHTS_RE = re.compile(r"(\d+)\s*(nights?|\u665a)", re.I)   # "6 nights" / "6 晚"
_MILES_RE = re.compile(r"([\d,]+)\s*(mi\b|miles?|km\b|\u82f1\u91cc|\u516c\u91cc)", re.I)


def _travelers_count(trip):
    """'2 adults' -> 2; '2 adults + 1 kid' -> 3. Falls back to 1."""
    nums = [int(n) for n in re.findall(r"\d+", str(trip.get("travelers") or ""))]
    return sum(nums) if nums else 1


def _sub_first_number(text, pattern, value):
    """Rewrite the first number matched by `pattern` (a 2-group regex whose
    group(1) is the number) with `value`, keeping the unit intact."""
    text = _s(text)
    m = pattern.search(text)
    if not m:
        return text
    fmt = "{:,}".format(value) if "," in m.group(1) else str(value)
    return text[:m.start(1)] + fmt + text[m.end(1):]


def _lodging_total(trip):
    total = 0
    for l in (trip.get("lodging") or []):
        price, nights = l.get("pricePerNight"), l.get("nights")
        if isinstance(price, (int, float)) and isinstance(nights, (int, float)):
            total += int(price) * int(nights)
    return total


def _recompute_budget(trip, old_days, old_miles):
    """Bring the budget back in line with an edited trip. Deterministic:

      * lodging line  -> recomputed from the lodging list (authoritative after
                         a hotel swap or a night-count change)
      * fuel line     -> scaled by new/old total miles
      * "N days" line -> scaled by new/old day count (food, rental car, ...)
      * anything else -> untouched (park passes, tours, misc)

    Labels carrying a night/day/mile count are rewritten to match. Totals and
    per-person are always recomputed from the item list. Best-effort: any item
    it cannot interpret is left exactly as it was.
    """
    budget = trip.get("budget")
    if not isinstance(budget, dict) or not isinstance(budget.get("items"), list):
        return
    new_days = len(trip.get("days") or []) or old_days
    new_miles = trip.get("totalMiles")
    if not isinstance(new_miles, (int, float)):
        new_miles = old_miles
    nights_total = sum(int(l.get("nights") or 0) for l in (trip.get("lodging") or []))

    for item in budget["items"]:
        label = _s(item.get("label"))     # normalized once; never touch the raw value
        low = label.lower()
        amount = _coerce_miles(item.get("amount"))   # ints, floats and "186"
        if amount is None:
            continue
        if any(w in low for w in _LODGING_WORDS):
            total = _lodging_total(trip)
            if total > 0:
                item["amount"] = total
                if nights_total:
                    item["label"] = _sub_first_number(label, _NIGHTS_RE, nights_total)
            continue
        if any(w in low for w in _FUEL_WORDS):
            if old_miles and new_miles and old_miles > 0:
                item["amount"] = max(0, int(round(amount * float(new_miles) / old_miles)))
                item["label"] = _sub_first_number(label, _MILES_RE, int(new_miles))
            continue
        if _DAYS_RE.search(label) and old_days > 0 and new_days != old_days:
            item["amount"] = max(0, int(round(amount * float(new_days) / old_days)))
            item["label"] = _sub_first_number(label, _DAYS_RE, new_days)

    total = sum(a for a in (_coerce_miles(i.get("amount")) for i in budget["items"])
                if a is not None)
    budget["total"] = total
    budget["perPerson"] = int(round(total / max(1, _travelers_count(trip))))



def revise_stay(trip, day_start, day_end, city_name, instruction, nights=None, log_fn=None):
    """Free-text trip edit: rewrite one overnight stop's days per the traveler's
    request ("don't want that hotel", "more hiking, less driving"), optionally
    resizing the stay in the same single model call.

    `instruction` is required (capped at 500 chars — it is embedded into the
    prompt). `nights=None` or equal to the current length keeps the stay length;
    otherwise the same rules as set_nights apply (1-7 nights, trip <= 21 days).
    Same span guards, anchor enforcement, deterministic cascade and atomicity
    contract as the other edit operations.
    """
    days = trip.get("days") or []
    n = len(days)
    if n < 2:
        raise ValueError("trip is too short to edit")
    if not (0 <= day_start <= day_end <= n - 2):
        raise ValueError("span must lie before the trip's final day")
    text = (instruction or "").strip()[:500]
    if not text:
        raise ValueError("an instruction is required")
    current = day_end - day_start + 1
    if nights is None:
        out_count = current
    else:
        try:
            out_count = int(nights)
        except (TypeError, ValueError):
            raise ValueError("invalid night count")
        if not (1 <= out_count <= 7):
            raise ValueError("nights must be between 1 and 7")
        if n - current + out_count > 21:
            raise ValueError("trip would exceed 21 days")
    return _replan_stay(trip, day_start, day_end, city_name, out_count, text, log_fn)
