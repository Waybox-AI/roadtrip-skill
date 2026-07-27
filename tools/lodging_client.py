#!/usr/bin/env python3
"""
lodging_client.py — lodging & campground search links + reference pricing.

No free key-less hotel-price API exists, so this builds deep links to the major
platforms (Booking / Airbnb / KOA / Hipcamp / Recreation.gov — plus a Ctrip
携程 city deep link for China-domestic places) for the agent to quote from,
and returns a coarse reference nightly price by lodging tier so the budget
always has *something* graded "reference".

CLI:
    python3 lodging_client.py "Springdale, UT" 2026-09-12 2026-09-14
    python3 lodging_client.py "成都博舍, 成都·太古里"
"""

import json
import re
import sys
from urllib.parse import quote as urlquote, quote_plus

try:
    from ctrip_city_ids import CITY_SLUGS
except ImportError:
    from tools.ctrip_city_ids import CITY_SLUGS

# Coarse US nightly reference priors ($/night). Override with a live quote.
TIER_PRICE = {
    "budget": 110, "midrange": 190, "upscale": 300,
    "campground": 35, "rv-site": 60, "in-park-lodge": 260,
}


_CJK = re.compile(r"[一-鿿]")


def ctrip_link(place, checkin=None, checkout=None):
    """hotels.ctrip.com/hotel/<city>/k1<keyword> deep link for a
    China-domestic place, else None.

    Ctrip's list pages are city-scoped: keyword params without a resolved
    city are silently dropped and the page falls back to its default city,
    so a link is only built when the place names a city in CITY_SLUGS.
    The k1 segment prefills the in-city keyword box; startDate/endDate
    feed the page's first search request when both dates are given.
    """
    place = (place or "").strip()
    if not _CJK.search(place):
        return None
    name, _, area = place.partition(",")
    name, area = name.strip(), area.strip()
    hits = [c for c in CITY_SLUGS if c in (area or place)]
    if not hits and area:
        hits = [c for c in CITY_SLUGS if c in name]
    if not hits:
        return None
    city = max(hits, key=len)
    kw = name[len(city):].strip("·- ") if name.startswith(city) else name
    url = "https://hotels.ctrip.com/hotel/%s/" % CITY_SLUGS[city]
    if kw and kw != city:
        url += "k1" + urlquote(kw)
    if checkin and checkout:
        url += "?startDate=%s&endDate=%s" % (checkin, checkout)
    return url


def search_links(place, checkin=None, checkout=None):
    p = quote_plus(place)
    links = {
        "booking": "https://www.booking.com/searchresults.html?ss=" + p,
        "airbnb": "https://www.airbnb.com/s/" + p + "/homes",
        "google_hotels": "https://www.google.com/travel/hotels/" + p,
        "koa": "https://koa.com/search/?q=" + p,
        "hipcamp": "https://www.hipcamp.com/en-US/search?q=" + p,
        "recreation_gov": "https://www.recreation.gov/search?q=" + p,
    }
    ctrip = ctrip_link(place, checkin, checkout)
    if ctrip:
        links["ctrip"] = ctrip
    if checkin and checkout:
        links["booking"] += "&checkin=" + checkin + "&checkout=" + checkout
    return links


def reference_price(tier="midrange"):
    return {
        "source": "reference",
        "reliability": "reference",
        "tier": tier,
        "pricePerNight": TIER_PRICE.get(tier, TIER_PRICE["midrange"]),
        "note": "coarse reference; replace with a live quote when possible.",
    }


def quote(place, checkin=None, checkout=None, tier="midrange"):
    out = reference_price(tier)
    out["place"] = place
    out["links"] = search_links(place, checkin, checkout)
    return out


if __name__ == "__main__":
    place = sys.argv[1] if len(sys.argv) > 1 else "Springdale, UT"
    ci = sys.argv[2] if len(sys.argv) > 2 else None
    co = sys.argv[3] if len(sys.argv) > 3 else None
    print(json.dumps(quote(place, ci, co), indent=2))
