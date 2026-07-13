#!/usr/bin/env python3
"""
weather_client.py — per-day forecast (and seasonal climatology) by lat/lng.

Real forecast, no key, in priority order:
  1. NWS / NOAA api.weather.gov (US only, ~7-day daily periods).
  2. Open-Meteo api.open-meteo.com (global, ~16-day daily; covers Canada/Mexico
     legs NWS can't, and adds precip-probability + max wind).
Seasonal fallback (beyond any forecast window):
  climatology() — Open-Meteo archive, same calendar week last year, as a
  "typical for the season" signal (NOT a forecast).

forecast() returns {source, units, days:[{date, icon, high, low, summary,
precipProb?, windMph?}]}; on total failure, a web-search `fallback(...)` dict.
Icons map to the renderer's set: sunny|partly-cloudy|cloudy|rain|snow|storm|
windy|fog.

CLI:
    python3 weather_client.py 37.2982 -113.0263          # forecast
    python3 weather_client.py 37.2982 -113.0263 09-15    # climatology for a date
"""

import datetime
import json
import sys
from urllib.parse import urlencode
from urllib.request import urlopen, Request

try:
    from web_search import fallback
except ImportError:
    from tools.web_search import fallback

UA = {"User-Agent": "roadtrip-navigator/1.0 (itinerary skill)"}

# WMO weather codes (Open-Meteo `weather_code`) -> the renderer's icon set.
# https://open-meteo.com/en/docs — codes grouped by phenomenon.
_WMO_ICON = {
    0: "sunny", 1: "sunny", 2: "partly-cloudy", 3: "cloudy",
    45: "fog", 48: "fog",
    51: "rain", 53: "rain", 55: "rain", 56: "rain", 57: "rain",
    61: "rain", 63: "rain", 65: "rain", 66: "rain", 67: "rain",
    80: "rain", 81: "rain", 82: "rain",
    71: "snow", 73: "snow", 75: "snow", 77: "snow", 85: "snow", 86: "snow",
    95: "storm", 96: "storm", 99: "storm",
}
_WMO_SUMMARY = {
    0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    56: "Freezing drizzle", 57: "Freezing drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain",
    66: "Freezing rain", 67: "Freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Rain showers", 81: "Rain showers", 82: "Violent rain showers",
    85: "Snow showers", 86: "Snow showers",
    95: "Thunderstorm", 96: "Thunderstorm w/ hail", 99: "Thunderstorm w/ hail",
}


def _wmo_icon(code):
    return _WMO_ICON.get(int(code) if code is not None else -1, "partly-cloudy")


def _get_json(url, timeout):
    with urlopen(Request(url, headers=UA), timeout=timeout) as r:
        return json.loads(r.read().decode())


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


def _open_meteo(lat, lng, timeout=8):
    """Global daily forecast (~16 days) via Open-Meteo. No key. Adds precip
    probability and max wind, which NWS's daily periods don't expose."""
    q = urlencode({
        "latitude": "%.4f" % lat, "longitude": "%.4f" % lng,
        "daily": ("weather_code,temperature_2m_max,temperature_2m_min,"
                  "precipitation_probability_max,wind_speed_10m_max"),
        "temperature_unit": "fahrenheit", "wind_speed_unit": "mph",
        "forecast_days": "16", "timezone": "auto",
    })
    d = _get_json("https://api.open-meteo.com/v1/forecast?" + q, timeout)
    dl = d.get("daily") or {}
    times = dl.get("time") or []
    days = []
    for i, day in enumerate(times):
        code = (dl.get("weather_code") or [None])[i] if i < len(dl.get("weather_code", [])) else None
        hi = (dl.get("temperature_2m_max") or [None])[i]
        lo = (dl.get("temperature_2m_min") or [None])[i]
        pp = (dl.get("precipitation_probability_max") or [None])[i]
        wd = (dl.get("wind_speed_10m_max") or [None])[i]
        days.append({
            "date": day,
            "name": None,
            "high": int(round(hi)) if isinstance(hi, (int, float)) else None,
            "low": int(round(lo)) if isinstance(lo, (int, float)) else None,
            "icon": _wmo_icon(code),
            "summary": _WMO_SUMMARY.get(int(code) if code is not None else -1, ""),
            "precipProb": int(pp) if isinstance(pp, (int, float)) else None,
            "windMph": int(round(wd)) if isinstance(wd, (int, float)) else None,
        })
    return days


def forecast(lat, lng, timeout=8):
    """Real per-day forecast, NWS first (US) then Open-Meteo (global)."""
    try:
        days = _nws(lat, lng, timeout)
        if days:
            return {"source": "nws", "units": "F", "days": days}
    except Exception as e:
        nws_reason = "NWS unavailable (US-only or network): %s" % e
    else:
        nws_reason = "NWS returned no periods"
    try:
        days = _open_meteo(lat, lng, timeout)
        if days:
            return {"source": "open-meteo", "units": "F", "days": days}
    except Exception as e:
        return fallback(
            "%s; Open-Meteo also failed: %s" % (nws_reason, e),
            ["weather forecast %.3f,%.3f next 7 days" % (lat, lng)],
            ["https://forecast.weather.gov", "https://weather.gc.ca"])
    return fallback(nws_reason + "; Open-Meteo returned no days",
                    ["weather forecast %.3f,%.3f next 7 days" % (lat, lng)],
                    ["https://forecast.weather.gov", "https://weather.gc.ca"])


def climatology(lat, lng, month, day, span_days=7, timeout=8):
    """"Typical for the season" signal for a calendar date, from Open-Meteo's
    archive (same window last year). NOT a forecast — a climatological hint for
    trips whose dates are beyond any real forecast window. Returns
    {source:"climatology", units:"F", year:int, high, low, icon, summary,
    wetShare} (wetShare = fraction of sampled days with measurable precip), or
    None on failure."""
    try:
        ref_year = datetime.date.today().year - 1
        try:
            center = datetime.date(ref_year, int(month), int(day))
        except ValueError:                       # e.g. Feb 29 in a non-leap ref year
            center = datetime.date(ref_year, int(month), min(int(day), 28))
        half = max(0, span_days // 2)
        start = center - datetime.timedelta(days=half)
        end = center + datetime.timedelta(days=half)
        q = urlencode({
            "latitude": "%.4f" % lat, "longitude": "%.4f" % lng,
            "start_date": start.isoformat(), "end_date": end.isoformat(),
            "daily": ("weather_code,temperature_2m_max,temperature_2m_min,"
                      "precipitation_sum"),
            "temperature_unit": "fahrenheit", "timezone": "auto",
        })
        d = _get_json("https://archive-api.open-meteo.com/v1/archive?" + q, timeout)
        dl = d.get("daily") or {}
        highs = [h for h in (dl.get("temperature_2m_max") or []) if isinstance(h, (int, float))]
        lows = [l for l in (dl.get("temperature_2m_min") or []) if isinstance(l, (int, float))]
        precip = [p for p in (dl.get("precipitation_sum") or []) if isinstance(p, (int, float))]
        codes = [c for c in (dl.get("weather_code") or []) if isinstance(c, (int, float))]
        if not highs:
            return None
        # Representative icon = the most "notable" phenomenon seen that week
        # (storm/snow beat rain beat clear), not a bland average.
        worst = max(codes, key=lambda c: _WMO_ICON.get(int(c), "") in
                    ("storm", "snow", "rain")) if codes else None
        wet = sum(1 for p in precip if p and p > 0.01)
        return {
            "source": "climatology", "units": "F", "year": ref_year,
            "high": int(round(sum(highs) / len(highs))),
            "low": int(round(sum(lows) / len(lows))) if lows else None,
            "icon": _wmo_icon(worst) if worst is not None else "partly-cloudy",
            "summary": _WMO_SUMMARY.get(int(worst) if worst is not None else -1, ""),
            "wetShare": round(wet / len(precip), 2) if precip else 0.0,
        }
    except Exception as e:
        print("[warn] climatology unavailable: %s" % e, file=sys.stderr)
        return None


if __name__ == "__main__":
    if len(sys.argv) >= 3:
        lat, lng = float(sys.argv[1]), float(sys.argv[2])
    else:
        lat, lng = 37.2982, -113.0263  # Zion
    if len(sys.argv) >= 4 and "-" in sys.argv[3]:
        mo, dy = sys.argv[3].split("-")[:2]
        print(json.dumps(climatology(lat, lng, mo, dy), indent=2))
    else:
        print(json.dumps(forecast(lat, lng), indent=2))
