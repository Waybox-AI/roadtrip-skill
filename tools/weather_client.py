#!/usr/bin/env python3
"""
weather_client.py — per-day forecast by lat/lng.

Preferred (US, no key): NWS / NOAA api.weather.gov (point -> forecast).
Fallback: OpenWeather (OPENWEATHER_API_KEY) if set, else a web-search note.
Canada: api.weather.gov is US-only; for Canadian legs fall back to search /
Environment Canada.

Returns a list of {date, icon, high, low, summary} where possible. Icons map to
the renderer's set: sunny|partly-cloudy|cloudy|rain|snow|storm|windy|fog.

CLI:
    python3 weather_client.py 37.2982 -113.0263
"""

import json
import sys
from urllib.request import urlopen, Request

try:
    from web_search import fallback
except ImportError:
    from tools.web_search import fallback

UA = {"User-Agent": "roadtrip-navigator/1.0 (itinerary skill)"}


def _icon_from_text(text):
    t = (text or "").lower()
    if "thunder" in t or "storm" in t:
        return "storm"
    if "snow" in t or "flurr" in t or "blizzard" in t:
        return "snow"
    if "rain" in t or "shower" in t or "drizzle" in t:
        return "rain"
    if "fog" in t or "haze" in t or "mist" in t:
        return "fog"
    if "wind" in t:
        return "windy"
    if "partly" in t or "mostly sunny" in t or "few clouds" in t:
        return "partly-cloudy"
    if "cloud" in t or "overcast" in t:
        return "cloudy"
    if "sun" in t or "clear" in t:
        return "sunny"
    return "partly-cloudy"


def _nws(lat, lng, timeout=8):
    pt = "https://api.weather.gov/points/%f,%f" % (lat, lng)
    with urlopen(Request(pt, headers=UA), timeout=timeout) as r:
        meta = json.loads(r.read().decode())
    forecast_url = meta["properties"]["forecast"]
    with urlopen(Request(forecast_url, headers=UA), timeout=timeout) as r:
        fc = json.loads(r.read().decode())
    periods = fc["properties"]["periods"]
    days = []
    for p in periods:
        if not p.get("isDaytime"):
            continue
        days.append({
            "date": p.get("startTime", "")[:10],
            "name": p.get("name"),
            "high": p.get("temperature"),
            "low": None,
            "icon": _icon_from_text(p.get("shortForecast")),
            "summary": p.get("shortForecast"),
        })
    # attach overnight lows from the following night period
    for i, p in enumerate(periods):
        if not p.get("isDaytime"):
            d = p.get("startTime", "")[:10]
            for dd in days:
                if dd["date"] == d and dd["low"] is None:
                    dd["low"] = p.get("temperature")
    return days


def forecast(lat, lng, timeout=8):
    try:
        days = _nws(lat, lng, timeout)
        if days:
            return {"source": "nws", "units": "F", "days": days}
    except Exception as e:
        reason = "NWS unavailable (US-only or network): %s" % e
    else:
        reason = "NWS returned no periods"
    return fallback(reason,
                    ["weather forecast %.3f,%.3f next 7 days" % (lat, lng)],
                    ["https://forecast.weather.gov", "https://weather.gc.ca"])


if __name__ == "__main__":
    if len(sys.argv) >= 3:
        lat, lng = float(sys.argv[1]), float(sys.argv[2])
    else:
        lat, lng = 37.2982, -113.0263  # Zion
    print(json.dumps(forecast(lat, lng), indent=2))
