"""Tests for trip editing: planner.remove_city and its deterministic cascade.

The model call and the weather client are always mocked — the suite runs
offline with no keys (repo hard constraint). Fixture data is the bundled
Southwest sample (7 days, overnights: Springdale x2, Bryce, Page, Grand
Canyon x2, return).
"""

import copy
import json
import os

import pytest

from scripts import planner
from scripts.planner import remove_city

_ROOT = os.path.join(os.path.dirname(__file__), "..")

# A canned "stitched day" the mocked model returns. Endpoint fields are wrong
# on purpose — remove_city must enforce from/to/overnight itself.
_STITCHED = {
    "date": "01/01", "title": "STITCHED DAY", "from": "model-from", "to": "model-to",
    "driveMiles": 200, "driveTime": "3h 30m", "overnight": "model-overnight",
    "weather": {"icon": "cloudy", "high": 70, "low": 50},
    "stops": [{"name": "Somewhere en route", "type": "scenic",
               "lat": 37.0, "lng": -112.5, "note": ""}],
    "fuelCharging": [], "meal": {"name": "Diner", "perPerson": 20}, "risks": [],
}


@pytest.fixture
def trip():
    with open(os.path.join(_ROOT, "assets", "tripData.example.json"),
              encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def mock_regen(monkeypatch):
    """Replace the model call; capture what remove_city asked for."""
    calls = {}

    def fake(t, day_index, instruction, log_fn=None):
        calls["day_index"] = day_index
        calls["instruction"] = instruction
        return copy.deepcopy(_STITCHED)

    monkeypatch.setattr(planner, "_regenerate_day_with_instruction", fake)
    return calls


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """No network ever: weather returns nothing, geocoding returns nothing."""
    monkeypatch.setattr(planner, "_weather_forecast", lambda lat, lng: None)
    monkeypatch.setattr(planner, "geocode_near", lambda *a, **kw: None)
    monkeypatch.setattr(planner, "geocode", lambda *a, **kw: None)


class TestSpanValidation:
    def test_cannot_remove_first_day(self, trip, mock_regen):
        with pytest.raises(ValueError):
            remove_city(trip, 0, 0, "Las Vegas, NV")

    def test_cannot_remove_last_day(self, trip, mock_regen):
        last = len(trip["days"]) - 1
        with pytest.raises(ValueError):
            remove_city(trip, last, last, "Las Vegas, NV")

    def test_cannot_remove_span_reaching_last_day(self, trip, mock_regen):
        with pytest.raises(ValueError):
            remove_city(trip, 1, len(trip["days"]) - 1, "everything")

    def test_short_trip_rejected(self, trip, mock_regen):
        trip["days"] = trip["days"][:2]
        with pytest.raises(ValueError):
            remove_city(trip, 1, 1, "anywhere")


class TestRemoveMiddleCity:
    """Remove Bryce (day index 2): days 09/12..09/18 x7 -> x6, join day 3->2."""

    def _go(self, trip):
        return remove_city(trip, 2, 2, city_name="Bryce Canyon City, UT")

    def test_day_count_and_totals(self, trip, mock_regen):
        out = self._go(trip)
        assert out is trip
        assert len(out["days"]) == 6
        assert out["drivingDays"] == 6
        # 1180 + (stitched 200 - (85 Bryce arrival + 155 old join)) = 1140
        assert out["totalMiles"] == 1140

    def test_join_day_replaced_with_enforced_endpoints(self, trip, mock_regen):
        out = self._go(trip)
        join = out["days"][2]
        assert join["title"] == "STITCHED DAY"
        assert join["from"] == "Springdale, UT"       # previous overnight
        assert join["to"] == "Page, AZ"               # old join day's destination
        assert join["overnight"] == "Page, AZ"        # never the model's value

    def test_regen_was_asked_for_the_right_day(self, trip, mock_regen):
        self._go(trip)
        assert mock_regen["day_index"] == 3           # pre-splice index
        assert "Bryce Canyon City, UT" in mock_regen["instruction"]
        assert "DIRECTLY" in mock_regen["instruction"]

    def test_dates_resequenced_contiguously(self, trip, mock_regen):
        out = self._go(trip)
        assert [d["date"] for d in out["days"]] == [
            "09/12", "09/13", "09/14", "09/15", "09/16", "09/17"]
        assert out["dateRange"] == "2026-09-12 ~ 2026-09-17"

    def test_untouched_days_keep_content(self, trip, mock_regen):
        before = copy.deepcopy(trip["days"])
        out = self._go(trip)
        assert out["days"][0]["title"] == before[0]["title"]
        assert out["days"][1]["title"] == before[1]["title"]
        assert out["days"][3]["title"] == before[4]["title"]   # shifted, same content

    def test_lodging_and_countdown_dropped(self, trip, mock_regen):
        out = self._go(trip)
        assert all("bryce" not in (l.get("area", "") + l.get("name", "")).lower()
                   for l in out["lodging"])
        assert all("bryce" not in (b.get("item", "") + b.get("where", "")).lower()
                   for b in out["bookingCountdown"])


class TestFailureLeavesTripUntouched:
    def test_model_failure_no_mutation(self, trip, monkeypatch):
        def boom(t, day_index, instruction, log_fn=None):
            raise RuntimeError("api down")
        monkeypatch.setattr(planner, "_regenerate_day_with_instruction", boom)
        snapshot = copy.deepcopy(trip)
        with pytest.raises(RuntimeError):
            remove_city(trip, 2, 2, "Bryce Canyon City, UT")
        assert trip == snapshot


def _span_day(k):
    return {
        "date": "01/01", "title": "SPAN DAY %d" % (k + 1),
        "from": "model-from", "to": "model-to",
        "driveMiles": 999 if k == 0 else 12,   # 999 must be overwritten by enforcement
        "driveTime": "9h", "overnight": "model-overnight",
        "weather": {"icon": "cloudy", "high": 70, "low": 50},
        "stops": [{"name": "Span stop %d" % k, "type": "scenic",
                   "lat": 37.1 + k, "lng": -112.4, "note": ""}],
        "fuelCharging": [], "meal": {"name": "Cafe", "perPerson": 15}, "risks": [],
    }


@pytest.fixture
def mock_span_regen(monkeypatch):
    calls = {}

    def fake(t, day_start, day_end, out_count, instruction, log_fn=None):
        calls.update(span=(day_start, day_end), count=out_count, instruction=instruction)
        return [_span_day(k) for k in range(out_count)]

    monkeypatch.setattr(planner, "_regenerate_span_with_instruction", fake)
    return calls


class TestSetNights:
    def test_guards(self, trip, mock_span_regen):
        from scripts.planner import set_nights
        with pytest.raises(ValueError):   # unchanged count
            set_nights(trip, 2, 2, "Bryce Canyon City, UT", 1)
        with pytest.raises(ValueError):   # zero nights is remove, not resize
            set_nights(trip, 2, 2, "Bryce Canyon City, UT", 0)
        with pytest.raises(ValueError):   # above cap
            set_nights(trip, 2, 2, "Bryce Canyon City, UT", 8)
        with pytest.raises(ValueError):   # touches the final day
            set_nights(trip, 6, 6, "Las Vegas, NV", 2)

    def test_trip_length_cap(self, mock_span_regen):
        days = [{"date": "09/%02d" % (12 + i), "overnight": "X" if i < 16 else None,
                 "from": "A", "to": "B", "driveMiles": 10, "stops": []}
                for i in range(17)]
        trip = {"days": days, "dateRange": "2026-09-12 ~ 2026-09-28", "totalMiles": 200}
        from scripts.planner import set_nights
        with pytest.raises(ValueError):   # 17 - 1 + 7 = 23 > 21
            set_nights(trip, 3, 3, "X", 7)

    def test_grow_bryce_to_two_nights(self, trip, mock_span_regen):
        from scripts.planner import set_nights
        out = set_nights(trip, 2, 2, "Bryce Canyon City, UT", 2)
        assert out is trip
        assert len(out["days"]) == 8 and out["drivingDays"] == 8
        run = out["days"][2:4]
        # arrival leg preserved verbatim from the old arrival day (85 mi, not 999)
        assert run[0]["from"] == "Springdale, UT"
        assert run[0]["to"] == "Bryce Canyon City, UT"
        assert run[0]["driveMiles"] == 85
        # second day is local and anchored to the same overnight
        assert run[1]["from"] == "Bryce Canyon City, UT"
        assert run[1]["overnight"] == "Bryce Canyon City, UT"
        # dates resequenced: one extra day, range extends by one
        assert [d["date"] for d in out["days"]][:5] == \
            ["09/12", "09/13", "09/14", "09/15", "09/16"]
        assert out["dateRange"] == "2026-09-12 ~ 2026-09-19"
        # totals: old run 85 → new run 85 (enforced) + 12 = delta +12
        assert out["totalMiles"] == 1180 + 12
        # lodging night count follows the stay
        bryce = [l for l in out["lodging"] if "bryce" in l.get("area", "").lower()]
        assert bryce and bryce[0]["nights"] == 2
        # the mock was asked for exactly 2 days on the right span
        assert mock_span_regen["span"] == (2, 2) and mock_span_regen["count"] == 2

    def test_shrink_start_anchored_springdale(self, trip, mock_span_regen):
        """Runs touching Day 1 are editable here (unlike remove_city)."""
        from scripts.planner import set_nights
        out = set_nights(trip, 0, 1, "Springdale, UT", 1)
        assert len(out["days"]) == 6
        first = out["days"][0]
        assert first["from"] == "Las Vegas, NV"        # departure leg intact
        assert first["driveMiles"] == 165
        assert first["overnight"] == "Springdale, UT"
        assert out["dateRange"] == "2026-09-12 ~ 2026-09-17"
        spring = [l for l in out["lodging"] if "springdale" in l.get("area", "").lower()]
        assert spring and spring[0]["nights"] == 1

    def test_count_mismatch_raises_untouched(self, trip, monkeypatch):
        from scripts.planner import set_nights
        monkeypatch.setattr(planner, "_regenerate_span_with_instruction",
                            lambda *a, **kw: (_ for _ in ()).throw(
                                ValueError("model returned 1 day(s) for the run, expected 2")))
        snapshot = copy.deepcopy(trip)
        with pytest.raises(ValueError):
            set_nights(trip, 2, 2, "Bryce Canyon City, UT", 2)
        assert trip == snapshot

    def test_model_failure_untouched(self, trip, monkeypatch):
        from scripts.planner import set_nights
        def boom(*a, **kw):
            raise RuntimeError("api down")
        monkeypatch.setattr(planner, "_regenerate_span_with_instruction", boom)
        snapshot = copy.deepcopy(trip)
        with pytest.raises(RuntimeError):
            set_nights(trip, 0, 1, "Springdale, UT", 1)
        assert trip == snapshot


class TestWeatherRefresh:
    def _forecast_for(self, dates, icon="rain", high=50, low=30):
        return {"source": "nws", "units": "F",
                "days": [{"date": d, "icon": icon, "high": high, "low": low}
                         for d in dates]}

    def test_shifted_days_get_real_forecast(self, trip, mock_regen, monkeypatch):
        window = ["2026-09-%02d" % d for d in range(12, 19)]
        monkeypatch.setattr(planner, "_weather_forecast",
                            lambda lat, lng: self._forecast_for(window))
        out = remove_city(trip, 2, 2, "Bryce Canyon City, UT")
        # days before the edit keep the model's estimate
        assert out["days"][0]["weather"] == {"icon": "sunny", "high": 88, "low": 60}
        assert out["days"][1]["weather"] == {"icon": "sunny", "high": 90, "low": 62}
        # the stitched day and every shifted day get the real forecast
        for d in out["days"][2:]:
            if d.get("stops"):
                assert d["weather"]["icon"] == "rain"
                assert d["weather"]["high"] == 50

    def test_dates_beyond_window_keep_estimate(self, trip, mock_regen, monkeypatch):
        monkeypatch.setattr(planner, "_weather_forecast",
                            lambda lat, lng: self._forecast_for(["2026-09-14"]))
        out = remove_city(trip, 2, 2, "Bryce Canyon City, UT")
        assert out["days"][2]["weather"]["icon"] == "rain"        # 09/14 covered
        assert out["days"][3]["weather"]["icon"] != "rain"        # 09/15 not covered

    def test_fallback_source_never_overwrites(self, trip, mock_regen, monkeypatch):
        monkeypatch.setattr(planner, "_weather_forecast",
                            lambda lat, lng: {"source": "fallback"})
        before = copy.deepcopy(trip["days"][4]["weather"])
        out = remove_city(trip, 2, 2, "Bryce Canyon City, UT")
        assert out["days"][3]["weather"] == before                # shifted, unchanged
