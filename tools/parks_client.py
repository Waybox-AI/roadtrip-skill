#!/usr/bin/env python3
"""
parks_client.py — national park info (NPS API) + reservation countdown helper.

NPS API: https://www.nps.gov/subjects/developer/  (free key -> NPS_API_KEY env)
Recreation.gov has an API too, but its booking windows are the operational truth;
here we build links and compute "book by" dates from common release rules.

CLI:
    NPS_API_KEY=xxx python3 parks_client.py zion
    python3 parks_client.py --countdown 2026-09-12
"""

import datetime as dt
import json
import os
import sys
from urllib.parse import urlencode, quote_plus
from urllib.request import urlopen

try:
    from web_search import fallback
except ImportError:
    from tools.web_search import fallback

NPS_BASE = "https://developer.nps.gov/api/v1/parks"

# Common reservation release windows (days before arrival) — STARTING POINTS,
# always confirm against the official rule for the specific park/site.
RELEASE_RULES = {
    "campground": 180,        # Recreation.gov rolling ~6 months
    "timed-entry": 7,         # many parks release a few days out (varies a lot)
    "wilderness-permit": 90,  # highly park-specific
    "in-park-lodge": 395,     # concessioners often ~13 months
    "one-way-rental": 60,     # lock price early
}


def park_info(query, timeout=8):
    """Look up a park by name/keyword via the NPS API."""
    key = os.environ.get("NPS_API_KEY")
    if not key:
        return fallback("no NPS_API_KEY set",
                        [query + " national park hours fees alerts site:nps.gov"],
                        ["https://www.nps.gov/findapark/index.htm"])
    try:
        url = NPS_BASE + "?" + urlencode({"q": query, "limit": 3, "api_key": key})
        with urlopen(url, timeout=timeout) as r:
            data = json.loads(r.read().decode())
        out = []
        for p in data.get("data", []):
            fees = p.get("entranceFees", [])
            out.append({
                "name": p.get("fullName"),
                "states": p.get("states"),
                "url": p.get("url"),
                "description": (p.get("description") or "")[:200],
                "entranceFee": fees[0].get("cost") if fees else None,
                "lat": _f(p.get("latitude")),
                "lng": _f(p.get("longitude")),
            })
        if out:
            return {"source": "nps", "parks": out}
        return fallback("NPS returned no match", [query + " national park site:nps.gov"])
    except Exception as e:
        return fallback("NPS API error: %s" % e, [query + " national park site:nps.gov"])


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def recreation_link(query):
    return "https://www.recreation.gov/search?q=" + quote_plus(query)


def book_by(arrival_date, rule, today=None):
    """Given an arrival date (YYYY-MM-DD) and a rule key, return the date by which
    you should book. Never returns a date before today — if the ideal release date
    has already passed, it clamps to today ("book ASAP")."""
    days = RELEASE_RULES.get(rule)
    if days is None:
        return None
    d = dt.date.fromisoformat(arrival_date)
    bb = d - dt.timedelta(days=days)
    today = today or dt.date.today()
    if bb < today:
        bb = min(today, d)        # don't suggest a past deadline
    return bb.isoformat()


def countdown(arrival_date, items=None):
    """Build a bookingCountdown[] for the schema.
    items: list of (label, rule, where). Defaults to a generic park set."""
    items = items or [
        ("Popular campground", "campground", "Recreation.gov"),
        ("Timed-entry permit", "timed-entry", "Recreation.gov / park site"),
        ("In-park lodge", "in-park-lodge", "Park concessioner"),
    ]
    out = []
    today = dt.date.today()
    for label, rule, where in items:
        bb = book_by(arrival_date, rule, today)
        ideal = (dt.date.fromisoformat(arrival_date) - dt.timedelta(days=RELEASE_RULES[rule]))
        note = ("book ASAP — already inside the normal booking window"
                if ideal < today else "~T-%d days (verify exact rule)" % RELEASE_RULES[rule])
        out.append({
            "item": label,
            "bookBy": bb,
            "where": where,
            "priority": "high" if rule in ("campground", "in-park-lodge", "timed-entry") else "medium",
            "note": note,
        })
    return {"source": "rules", "bookingCountdown": out,
            "disclaimer": "Release windows are starting points — confirm each on the right system. "
                          "Federal sites (national parks/forests) use Recreation.gov; STATE parks use "
                          "their own systems (e.g. ReserveCalifornia, and other state portals). "
                          "Canada uses Parks Canada / provincial systems."}


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--countdown":
        print(json.dumps(countdown(sys.argv[2] if len(sys.argv) > 2 else "2026-09-12"), indent=2))
    else:
        q = " ".join(sys.argv[1:]) or "zion"
        print(json.dumps(park_info(q), indent=2, ensure_ascii=False))
        print("recreation.gov:", recreation_link(q))
