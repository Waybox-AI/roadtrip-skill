"""Weather provenance (PR①): weather_client's NWS→Open-Meteo→climatology
ladder and its WMO parsing, plus planner.refresh_trip_weather tagging days
forecast vs climatology. All network calls are stubbed — the suite is offline.
"""

import json

import pytest

from tools import weather_client as wc
from scripts import planner


# --------------------------------------------------------------------------- #
# weather_client: parsing + source ladder
# --------------------------------------------------------------------------- #

def _fake_http(mapping):
    """Return a _get_json stand-in: substring in URL -> canned dict."""
    def _get(url, timeout):
        for needle, payload in mapping.items():
            if needle in url:
                return payload
        raise AssertionError("unexpected URL: " + url)
    return _get


class TestWmoMapping:
    def test_codes_map_to_renderer_icons(self):
        assert wc._wmo_icon(0) == "sunny"
        assert wc._wmo_icon(3) == "cloudy"
        assert wc._wmo_icon(65) == "rain"
        assert wc._wmo_icon(75) == "snow"
        assert wc._wmo_icon(95) == "storm"
        assert wc._wmo_icon(45) == "fog"
        assert wc._wmo_icon(None) == "partly-cloudy"
        assert wc._wmo_icon(9999) == "partly-cloudy"     # unknown code


class TestForecastLadder:
    _OM = {"daily": {
        "time": ["2026-07-13", "2026-07-14"],
        "weather_code": [3, 95],
        "temperature_2m_max": [91.7, 88.0],
        "temperature_2m_min": [70.2, 68.0],
        "precipitation_probability_max": [9, 60],
        "wind_speed_10m_max": [15.9, 22.0],
    }}

    def test_nws_used_first(self, monkeypatch):
        monkeypatch.setattr(wc, "_nws", lambda lat, lng, t=8: [
            {"date": "2026-07-13", "icon": "storm", "high": 91, "low": 56}])
        out = wc.forecast(37.3, -113.0)
        assert out["source"] == "nws" and out["days"][0]["icon"] == "storm"

    def test_falls_back_to_open_meteo(self, monkeypatch):
        monkeypatch.setattr(wc, "_nws",
                            lambda *a, **k: (_ for _ in ()).throw(Exception("US-only")))
        monkeypatch.setattr(wc, "_get_json", _fake_http({"open-meteo": self._OM}))
        out = wc.forecast(51.18, -115.57)                 # Banff — NWS can't
        assert out["source"] == "open-meteo"
        assert len(out["days"]) == 2
        d1 = out["days"][1]
        assert d1["icon"] == "storm" and d1["high"] == 88      # WMO 95 -> storm
        assert d1["precipProb"] == 60 and d1["windMph"] == 22  # extra signals

    def test_total_failure_returns_fallback_shape(self, monkeypatch):
        monkeypatch.setattr(wc, "_nws",
                            lambda *a, **k: (_ for _ in ()).throw(Exception("down")))
        monkeypatch.setattr(wc, "_get_json",
                            lambda *a, **k: (_ for _ in ()).throw(Exception("down")))
        out = wc.forecast(0.0, 0.0)
        assert out["source"] == "fallback"                # never raises

    def test_mismatched_array_lengths_do_not_crash(self, monkeypatch):
        # Regression (PR review): value arrays shorter than `time` used to
        # IndexError. Missing values must degrade to None, not crash.
        ragged = {"daily": {
            "time": ["2026-07-13", "2026-07-14", "2026-07-15"],
            "weather_code": [3],                          # only 1 of 3
            "temperature_2m_max": [91.7, 88.0],           # only 2 of 3
            "temperature_2m_min": [],                     # empty
            "precipitation_probability_max": [9, 24, 47],
            "wind_speed_10m_max": [15.9],
        }}
        monkeypatch.setattr(wc, "_nws",
                            lambda *a, **k: (_ for _ in ()).throw(Exception("US-only")))
        monkeypatch.setattr(wc, "_get_json", _fake_http({"open-meteo": ragged}))
        out = wc.forecast(51.18, -115.57)
        assert out["source"] == "open-meteo" and len(out["days"]) == 3
        assert out["days"][2]["high"] is None and out["days"][2]["low"] is None
        assert out["days"][1]["high"] == 88


class TestClimatology:
    _ARCHIVE = {"daily": {
        "time": ["2025-09-12", "2025-09-13", "2025-09-14", "2025-09-15"],
        "weather_code": [3, 3, 95, 61],
        "temperature_2m_max": [88.0, 90.0, 78.0, 80.0],
        "temperature_2m_min": [60.0, 62.0, 55.0, 57.0],
        "precipitation_sum": [0.0, 0.0, 0.3, 0.1],
    }}

    def test_averages_and_flags_wet_share(self, monkeypatch):
        monkeypatch.setattr(wc, "_get_json", _fake_http({"archive": self._ARCHIVE}))
        c = wc.climatology(37.3, -113.0, 9, 13, span_days=4)
        assert c["source"] == "climatology" and c["year"] == 2025
        assert c["high"] == 84                            # mean of the 4 highs
        assert c["icon"] == "storm"                       # most notable = WMO 95
        assert 0.4 < c["wetShare"] <= 0.5                 # 2 of 4 days wet

    def test_storm_wins_even_when_rain_comes_first(self, monkeypatch):
        # Regression (PR review): a boolean key made max() pick the first truthy
        # (rain), not the most severe (storm). Rain days precede the storm here.
        archive = {"daily": {
            "time": ["2025-09-12", "2025-09-13", "2025-09-14"],
            "weather_code": [61, 63, 95],                 # rain, rain, storm
            "temperature_2m_max": [80.0, 82.0, 78.0],
            "temperature_2m_min": [55.0, 56.0, 54.0],
            "precipitation_sum": [0.2, 0.1, 0.4],
        }}
        monkeypatch.setattr(wc, "_get_json", _fake_http({"archive": archive}))
        c = wc.climatology(37.3, -113.0, 9, 13, span_days=3)
        assert c["icon"] == "storm"                       # severity, not position

    def test_wmo_severity_order(self):
        assert (wc._wmo_severity(95) > wc._wmo_severity(75)
                > wc._wmo_severity(61) > wc._wmo_severity(0))   # storm>snow>rain>clear

    def test_feb_29_reference_year_does_not_crash(self, monkeypatch):
        monkeypatch.setattr(wc, "_get_json", _fake_http({"archive": self._ARCHIVE}))
        assert wc.climatology(37.3, -113.0, 2, 29) is not None

    def test_empty_archive_returns_none(self, monkeypatch):
        monkeypatch.setattr(wc, "_get_json", _fake_http({"archive": {"daily": {}}}))
        assert wc.climatology(37.3, -113.0, 9, 13) is None


# --------------------------------------------------------------------------- #
# planner.refresh_trip_weather: whole-trip tagging
# --------------------------------------------------------------------------- #

def _trip(n=4):
    return {
        "dateRange": "2026-09-12 ~ 2026-09-15",
        "days": [
            {"date": "09/%02d" % (12 + k),
             "weather": {"icon": "sunny", "high": 88, "low": 60},
             "stops": [{"name": "S%d" % k, "lat": 37.3, "lng": -113.0}]}
            for k in range(n)
        ],
    }


class TestRefreshTripWeather:
    def test_forecast_days_tagged_climatology_days_tagged(self, monkeypatch):
        # Forecast covers 09/12–09/13 only; climatology covers the rest.
        monkeypatch.setattr(planner, "_weather_forecast", lambda lat, lng: {
            "source": "open-meteo", "days": [
                {"date": "2026-09-12", "icon": "rain", "high": 70, "low": 50},
                {"date": "2026-09-13", "icon": "storm", "high": 68, "low": 48},
            ]})
        monkeypatch.setattr(planner, "_climatology",
                            lambda lat, lng, iso: {"icon": "cloudy", "high": 75, "low": 55})
        trip = _trip()
        planner.refresh_trip_weather(trip)
        assert trip["days"][0]["weather"]["source"] == "forecast"
        assert trip["days"][0]["weather"]["icon"] == "rain"
        assert trip["days"][0]["weather"]["asOf"] == "2026-09-12"
        assert trip["days"][2]["weather"]["source"] == "climatology"
        assert trip["days"][2]["weather"]["icon"] == "cloudy"

    def test_all_offline_leaves_estimate_untagged(self, monkeypatch):
        monkeypatch.setattr(planner, "_weather_forecast", lambda lat, lng: None)
        monkeypatch.setattr(planner, "_climatology", lambda lat, lng, iso: None)
        trip = _trip()
        planner.refresh_trip_weather(trip)
        assert trip["days"][0]["weather"] == {"icon": "sunny", "high": 88, "low": 60}
        assert "source" not in trip["days"][0]["weather"]

    def test_undated_trip_is_a_noop(self, monkeypatch):
        monkeypatch.setattr(planner, "_weather_forecast",
                            lambda lat, lng: (_ for _ in ()).throw(AssertionError("called")))
        trip = {"days": [{"weather": {"icon": "sunny"}, "stops": [{"lat": 1, "lng": 1}]}]}
        planner.refresh_trip_weather(trip)               # no dateRange -> no calls
        assert trip["days"][0]["weather"] == {"icon": "sunny"}

    def test_precip_and_wind_carried_onto_the_day(self, monkeypatch):
        monkeypatch.setattr(planner, "_weather_forecast", lambda lat, lng: {
            "source": "open-meteo", "days": [
                {"date": "2026-09-12", "icon": "rain", "high": 70, "low": 50,
                 "precipProb": 80, "windMph": 25, "summary": "Heavy rain"}]})
        monkeypatch.setattr(planner, "_climatology", lambda lat, lng, iso: None)
        trip = _trip(1)
        planner.refresh_trip_weather(trip)
        w = trip["days"][0]["weather"]
        assert w["precipProb"] == 80 and w["windMph"] == 25 and w["summary"] == "Heavy rain"
