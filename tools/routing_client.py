#!/usr/bin/env python3
"""
routing_client.py — route distance & driving time between waypoints.

Preferred: OSRM public demo server (OSM-based, no key).
Fallback:  great-circle distance × a road-winding factor, with a web-search note.

Returns miles + an "Xh Ym" string. Units default to miles (US road trips).

CLI:
    python3 routing_client.py 36.1699,-115.1398 37.2982,-113.0263 ...
"""

import json
import math
import sys
from urllib.request import urlopen

try:
    from web_search import fallback
except ImportError:  # when imported as tools.web_search
    from tools.web_search import fallback

OSRM = "https://router.project-osrm.org/route/v1/driving/"
KM_PER_MILE = 1.60934
ROAD_FACTOR = 1.25  # straight-line → driving distance fudge factor for fallback
AVG_MPH = 55        # fallback average speed incl. stops


def _fmt_time(hours):
    h = int(hours)
    m = int(round((hours - h) * 60))
    if m == 60:
        h, m = h + 1, 0
    return "%dh%02dm" % (h, m)


def haversine_miles(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 3958.8 * math.asin(math.sqrt(h))


def route(waypoints, timeout=8):
    """waypoints: list of (lat, lng). Returns a dict with miles + driveTime."""
    if len(waypoints) < 2:
        return {"source": "error", "reason": "need >= 2 waypoints"}

    coords = ";".join("%f,%f" % (lng, lat) for (lat, lng) in waypoints)  # OSRM=lng,lat
    url = OSRM + coords + "?overview=false"
    try:
        with urlopen(url, timeout=timeout) as r:
            data = json.loads(r.read().decode())
        if data.get("code") == "Ok" and data.get("routes"):
            rt = data["routes"][0]
            miles = rt["distance"] / 1000.0 / KM_PER_MILE
            hours = rt["duration"] / 3600.0
            return {
                "source": "osrm",
                "miles": round(miles, 1),
                "driveTime": _fmt_time(hours),
                "hours": round(hours, 2),
            }
    except Exception as e:  # network blocked / OSRM down
        reason = "OSRM unavailable: %s" % e
    else:
        reason = "OSRM returned no route"

    # ---- fallback: straight-line × winding factor ----
    miles = sum(haversine_miles(waypoints[i], waypoints[i + 1])
                for i in range(len(waypoints) - 1)) * ROAD_FACTOR
    hours = miles / AVG_MPH
    out = fallback(reason, ["driving distance and time " + " to ".join(
        "%.3f,%.3f" % w for w in waypoints)])
    out.update({
        "miles": round(miles, 1),
        "driveTime": _fmt_time(hours),
        "hours": round(hours, 2),
        "note": "rough estimate (great-circle × %.2f); verify with a maps app" % ROAD_FACTOR,
    })
    return out


def _parse(s):
    lat, lng = s.split(",")
    return (float(lat), float(lng))


if __name__ == "__main__":
    pts = [_parse(a) for a in sys.argv[1:]]
    if len(pts) < 2:
        pts = [(36.1699, -115.1398), (37.2982, -113.0263)]  # Vegas -> Zion demo
    print(json.dumps(route(pts), indent=2))
