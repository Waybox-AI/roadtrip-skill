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
fix_endpoints(trip, start, destination) -> None
    Snap the first/last stop coordinates to the real start/destination.
despread_stops(trip) -> None
    Nudge/re-geocode stops whose coordinates collide so map pins separate.
geocode(query, timeout=3.0) -> {"lat","lng"} | None
geocode_near(query, lat, lng, timeout=3.0) -> {"lat","lng"} | None
    Best-effort Photon geocoding (free, no key), the latter biased to a locale.
"""

import functools
import json
import math
import os
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


def plan_live(payload, region, on_progress=None, log_fn=None):
    """Live phase-2 generation: one streaming Claude call framed by the skill's
    own docs. `on_progress(event)` (if given) is called with small dicts as JSON
    streams in so a caller can reflect progress:
      - {"expectedChars": n}  once, before streaming starts
      - {"charsReceived": n}  on every chunk (fine-grained ETA signal)
      - {"step": idx}         when a coarse phase threshold is crossed
    `log_fn(usage)` (if given) receives the final token-usage object."""
    import anthropic
    client = anthropic.Anthropic()
    system, prompt = build_messages(payload, region)
    text = ""

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
    with client.messages.stream(model=_MODEL, max_tokens=16000, system=system,
                                messages=[{"role": "user", "content": prompt}]) as stream:
        for chunk in stream.text_stream:
            text += chunk
            emit({"charsReceived": len(text)})
            for n, step in thresholds:
                if len(text) >= n:
                    emit({"step": step})
        final = stream.get_final_message()   # carries the authoritative token usage
    if log_fn:
        log_fn(final.usage)
    return _routes.extract_json(text)


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


def regenerate_day(trip, day_index, comment_body, log_fn=None):
    """Ask the AI to rewrite a single trip day based on a commenter's suggestion.

    Only the targeted day is regenerated; all other days remain unchanged.
    Returns the updated day dict (same schema as an element of trip["days"]).
    Raises on failure so callers can decide whether to surface or swallow the error.
    """
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
        "A traveler requests this change: \"%s\"\n\n"
        "Rewrite ONLY Day %d to honour this request. %s"
        "Keep the same 'date' value. Use accurate lat/lng for all stops. "
        "Output ONLY the JSON object for this single day — no prose, no markdown fences:\n%s\n"
        "Return JSON only."
    ) % (
        trip.get("title", ""),
        days_summary,
        day_index + 1,
        json.dumps(day, ensure_ascii=False, indent=2),
        comment_body,
        day_index + 1,
        continuity,
        schema,
    )
    msg = client.messages.create(
        model=_MODEL, max_tokens=4000,
        messages=[{"role": "user", "content": prompt}])
    text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
    if log_fn:
        log_fn(msg.usage)
    new_day = _routes.extract_json(text)
    # Preserve the original date so the calendar doesn't drift.
    new_day["date"] = day.get("date", new_day.get("date", ""))
    return new_day
