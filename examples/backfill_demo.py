#!/usr/bin/env python3
"""Hands-on local check for the post-generation backfills.

Builds a trip shaped like the model's single-shot output (guessed numbers, no
evPlan / crossBorder), runs each refresh_trip_* backfill, and prints before vs
after so you can SEE the tools/ clients rewrite the hard numbers.

Run from anywhere:
    python3 examples/backfill_demo.py

No API key needed. Routing hits the OSRM public server (needs network); if it's
unreachable the routing pass keeps the model's miles (all-or-nothing) and every
other backfill still runs offline.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "scripts"))
import planner

# A trip shaped like the model's single-shot output — deliberately with
# rough/guessed numbers and no evPlan / crossBorder yet.
trip = {
    "lang": "en", "travelers": "2 adults", "totalMiles": 900,
    "region": "coast", "dateRange": "2026-09-12 ~ 2026-09-15",
    "generationDate": "2026-07-16",
    "vehicle": {"type": "EV", "model": "Model Y", "mpg": None, "rangeMiles": 280},
    "budget": {"currency": "USD", "items": [
        {"label": "Charging (model guess)", "amount": 140, "reliability": "estimate"},
        {"label": "Lodging (3 nights)", "amount": 600, "reliability": "reference"},
    ], "total": 740, "perPerson": 370},
    "days": [
        {"date": "09/12", "title": "SF -> Monterey", "to": "Monterey, CA",
         "driveMiles": 130, "driveTime": "2h30m",
         "stops": [{"name": "San Francisco", "lat": 37.7749, "lng": -122.4194},
                   {"name": "Monterey", "lat": 36.6002, "lng": -121.8947}],
         "fuelCharging": [{"name": "Supercharger", "type": "charge", "powerKW": 250}]},
        {"date": "09/13", "title": "Big Sur", "to": "Big Sur, CA",
         "driveMiles": 30, "driveTime": "0h45m",
         "stops": [{"name": "Bixby Bridge", "lat": 36.3714, "lng": -121.9018}],
         "fuelCharging": []},
        {"date": "09/14", "title": "-> Los Angeles", "to": "Los Angeles, CA",
         "driveMiles": 320, "driveTime": "5h30m",
         "stops": [{"name": "Los Angeles", "lat": 34.0522, "lng": -118.2437}],
         "fuelCharging": [{"name": "Electrify America", "type": "charge", "powerKW": 150}]},
    ],
    "lodging": [{"name": "Post Ranch Inn", "area": "Big Sur, CA", "nights": 3,
                 "pricePerNight": 200, "rating": "4.7", "booked": False}],
    "bookingCountdown": [
        {"item": "Pfeiffer Big Sur campground", "bookBy": "2099-01-01",
         "where": "Recreation.gov", "priority": "high"},
    ],
}


def show(tag):
    print("\n==== %s ====" % tag)
    print("day driveMiles:", [d["driveMiles"] for d in trip["days"]],
          "| totalMiles:", trip["totalMiles"])
    fuel = next(i for i in trip["budget"]["items"]
                if "harg" in i["label"] or "uel" in i["label"])
    print("fuel/charge line:", fuel["label"], "= $%s" % fuel["amount"],
          "(source=%s)" % fuel.get("source"))
    print("evPlan present:", bool(trip.get("evPlan")),
          "| legs:", len(trip.get("evPlan", {}).get("legs", [])))
    print("countdown bookBy:", trip["bookingCountdown"][0]["bookBy"],
          "(source=%s)" % trip["bookingCountdown"][0].get("source"))
    print("lodging links:", list(trip["lodging"][0].get("links", {}).keys())[:3])


if __name__ == "__main__":
    show("BEFORE (model's guesses)")
    planner.refresh_trip_routing(trip)          # needs OSRM (network)
    planner.refresh_trip_fuel(trip, efficiency=None)
    planner.refresh_trip_ev_corridor(trip)
    planner.refresh_trip_countdown(trip)
    planner.refresh_trip_lodging_links(trip)
    show("AFTER (rewritten by tools/)")
