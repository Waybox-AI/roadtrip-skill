#!/usr/bin/env python3
"""
lodging_client.py — lodging & campground search links + reference pricing.

No free key-less hotel-price API exists, so this builds deep links to the major
platforms (Booking / Airbnb / KOA / Hipcamp / Recreation.gov) for the agent to
quote from, and returns a coarse reference nightly price by lodging tier so the
budget always has *something* graded "reference".

CLI:
    python3 lodging_client.py "Springdale, UT" 2026-09-12 2026-09-14
"""

import json
import sys
from urllib.parse import quote_plus

# Coarse US nightly reference priors ($/night). Override with a live quote.
TIER_PRICE = {
    "budget": 110, "midrange": 190, "upscale": 300,
    "campground": 35, "rv-site": 60, "in-park-lodge": 260,
}


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
