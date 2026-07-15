#!/usr/bin/env python3
"""
places_client.py — validate that a user-supplied place name actually exists.

Guards Step 1 (slot filling) against fabricated or misspelled places: the agent
must not plan a route from "ABC" just because the string parsed as a location.
Existence is checked against OpenStreetMap via the free Photon geocoder
(photon.komoot.io, no key) — OSM covers virtually every settlement, which beats
any model's recall of obscure town names (Zzyzx, CA and Why, AZ are real;
"ABC" is not).

validate_place() returns one of four verdicts:
  match         high-confidence real place → canonical name, lat/lng, country
                (outsideNA=True when it lies outside US/Canada/Mexico)
  did-you-mean  no confident match but close candidates exist — confirm the
                intended place with the user before planning
  no-match      nothing place-like in OSM resembles the name — stop and ask;
                never plan around an unverified place
  unverified    network unavailable — standard web-search fallback shape; the
                agent should use its own judgment and ask about names it does
                not recognize
NEVER read "unverified" (offline) as "fake" — only "no-match" means the name
looks nonexistent. Non-Latin queries (e.g. 中文地名) tend to land in
did-you-mean with the English name as the suggestion; treat that as a normal
confirm-with-the-user case.

CLI:
    python3 places_client.py "Las Vegas"
    python3 places_client.py "ABC"
    python3 places_client.py "Zzyzx, CA"
"""

import difflib
import json
import re
import sys
from urllib.parse import urlencode
from urllib.request import urlopen, Request

try:
    from web_search import fallback
except ImportError:
    from tools.web_search import fallback

PHOTON = "https://photon.komoot.io/api/"
UA = {"User-Agent": "roadtrip-navigator/1.0 (itinerary skill)"}
NA_COUNTRIES = ("US", "CA", "MX")   # the skill's coverage area

MATCH_SCORE = 0.85      # >= this → confident match
SUGGEST_SCORE = 0.65    # >= this → worth offering as "did you mean …?"
# 0.65, not 0.60: very short queries ("ABC") fuzz-match unrelated towns at
# ~0.60 (Abcoude…); real typos score well above it ("Zyon"→"Zion" = 0.75).

# Only these OSM keys make a *place* real — a same-named shop or street doesn't.
_PLACE_KEYS = ("place", "boundary")
# Tie-break: prefer the more significant settlement when scores are equal.
_PLACE_RANK = {"city": 5, "town": 4, "village": 3, "hamlet": 2,
               "suburb": 1, "locality": 1}


def _get_json(url, timeout):
    with urlopen(Request(url, headers=UA), timeout=timeout) as r:
        return json.loads(r.read().decode())


def _norm(s):
    """Lowercase, strip punctuation, collapse whitespace."""
    s = re.sub(r"[^\w\s]", " ", (s or "").lower())
    return re.sub(r"\s+", " ", s).strip()


def _score(query, props):
    """Similarity between the user's string and one Photon result, 0..1.
    Compares both the full query and the bare name (region qualifier stripped,
    'Springdale, UT' → 'springdale') against the result's name, also paired
    with its state/country so 'springdale utah' still scores 1.0."""
    qn = _norm(query)
    q_bare = _norm(re.split(r"[,(]", query)[0])
    queries = {q for q in (qn, q_bare) if q}
    name = _norm(props.get("name"))
    if not name or not queries:
        return 0.0
    cands = {name}
    for extra in (props.get("state"), props.get("country")):
        e = _norm(extra)
        if e:
            cands.add(name + " " + e)
    return max(difflib.SequenceMatcher(None, q, c).ratio()
               for q in queries for c in cands)


def _canonical(props):
    parts = [props.get("name"), props.get("state"), props.get("country")]
    return ", ".join(p for p in parts if p)


def _candidates(query, limit, timeout):
    """Photon lookup → scored place-typed candidates (may be empty)."""
    url = PHOTON + "?" + urlencode({"q": query, "limit": limit, "lang": "en"})
    data = _get_json(url, timeout)
    out = []
    for f in (data.get("features") or []):
        props = f.get("properties") or {}
        if props.get("osm_key") not in _PLACE_KEYS:
            continue
        coords = (f.get("geometry") or {}).get("coordinates") or []
        if len(coords) < 2 or not all(isinstance(c, (int, float)) for c in coords[:2]):
            continue
        out.append({
            "name": props.get("name"),
            "canonical": _canonical(props),
            "lat": round(coords[1], 5),
            "lng": round(coords[0], 5),
            "countryCode": (props.get("countrycode") or "").upper(),
            "osmKey": props.get("osm_key"),
            "osmValue": props.get("osm_value"),
            "score": _score(query, props),
            "rank": _PLACE_RANK.get(props.get("osm_value"), 0),
        })
    return out


def _slim(c):
    return {"canonical": c["canonical"], "lat": c["lat"], "lng": c["lng"],
            "countryCode": c["countryCode"], "score": round(c["score"], 2)}


def validate_place(name, na_bias=True, limit=8, timeout=8):
    """Does `name` exist as a real place? See module docstring for verdicts.

    na_bias: prefer a US/CA/MX match over an equally-scored one elsewhere
    (e.g. "Paris" → Paris, Texas rather than Paris, France) — sensible for a
    North-America road-trip skill; pass False for a neutral pick.
    """
    if not name or not str(name).strip():
        return {"source": "error", "reason": "empty place name"}
    name = str(name).strip()
    try:
        cands = _candidates(name, limit, timeout)
    except Exception as e:
        out = fallback("Photon geocoder unavailable: %s" % e,
                       ['"%s" city town — does this place exist' % name],
                       ["https://www.openstreetmap.org", "https://maps.google.com"])
        out.update({"verdict": "unverified", "query": name})
        return out

    key = (lambda c: (-round(c["score"], 2),
                      c["countryCode"] not in NA_COUNTRIES,
                      -c["rank"])) if na_bias else \
          (lambda c: (-round(c["score"], 2), -c["rank"]))
    cands.sort(key=key)

    if cands and cands[0]["score"] >= MATCH_SCORE:
        best = cands[0]
        return {
            "source": "photon", "verdict": "match", "query": name,
            "canonical": best["canonical"], "name": best["name"],
            "lat": best["lat"], "lng": best["lng"],
            "countryCode": best["countryCode"],
            "osmKey": best["osmKey"], "osmValue": best["osmValue"],
            "outsideNA": best["countryCode"] not in NA_COUNTRIES,
            "score": round(best["score"], 2),
            "alternates": [_slim(c) for c in cands[1:]
                           if c["score"] >= SUGGEST_SCORE][:3],
        }

    suggestions = [_slim(c) for c in cands if c["score"] >= SUGGEST_SCORE][:3]
    if suggestions:
        return {"source": "photon", "verdict": "did-you-mean", "query": name,
                "suggestions": suggestions,
                "note": "no confident match — confirm the intended place "
                        "with the user before planning."}
    return {"source": "photon", "verdict": "no-match", "query": name,
            "reason": "no place in OpenStreetMap matches %r" % name,
            "note": "looks nonexistent or badly misspelled — ask the user; "
                    "never plan a route around an unverified place."}


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "Las Vegas"
    print(json.dumps(validate_place(q), indent=2, ensure_ascii=False))
