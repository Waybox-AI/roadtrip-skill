import json
import sys
import types

import pytest

from scripts.planner import (
    build_user,
    despread_stops,
    fix_endpoints,
    generate_trip,
    plan_demo,
    regenerate_day,
)


class TestBuildUserRules:
    def _payload(self, **kw):
        base = {"start": "Las Vegas, NV", "destination": "Zion NP", "days": 5}
        base.update(kw)
        return base

    def test_round_trip_sets_loop_rule(self):
        prompt = build_user(self._payload(tripType="round"), "desert")
        assert "TRIP SHAPE: ROUND TRIP" in prompt

    def test_one_way_sets_one_way_rule(self):
        prompt = build_user(self._payload(tripType="one-way"), "desert")
        assert "TRIP SHAPE: ONE WAY" in prompt

    def test_ev_uses_kwh_energy_rule(self):
        prompt = build_user(self._payload(vehicle="EV", efficiency="3.5"), "desert")
        assert "miles per kWh" in prompt
        assert "3.5" in prompt

    def test_gas_uses_mpg_energy_rule(self):
        prompt = build_user(self._payload(vehicle="gas", efficiency="30"), "desert")
        assert "MPG" in prompt
        assert "30" in prompt

    def test_chinese_lang_adds_lang_rule(self):
        prompt = build_user(self._payload(lang="zh"), "desert")
        assert "Simplified Chinese" in prompt

    def test_chosen_route_pins_waypoints(self):
        payload = self._payload(route={
            "label": "Scenic route",
            "waypoints": [
                {"name": "Las Vegas", "lat": 36.17, "lng": -115.14},
                {"name": "Zion", "lat": 37.30, "lng": -113.03},
            ],
        })
        prompt = build_user(payload, "desert")
        assert "Scenic route" in prompt
        assert "Las Vegas" in prompt and "Zion" in prompt


class TestFixEndpoints:
    def test_snaps_first_and_last_stop(self, monkeypatch):
        monkeypatch.setattr(
            "scripts.planner.geocode",
            lambda q, timeout=3.0: {"lat": 1.0, "lng": 2.0} if "Vegas" in q else {"lat": 3.0, "lng": 4.0},
        )
        trip = {"days": [
            {"stops": [{"lat": 0, "lng": 0}]},
            {"stops": [{"lat": 0, "lng": 0}]},
        ]}
        fix_endpoints(trip, "Las Vegas, NV", "Zion NP")
        assert trip["days"][0]["stops"][0] == {"lat": 1.0, "lng": 2.0}
        assert trip["days"][-1]["stops"][-1] == {"lat": 3.0, "lng": 4.0}

    def test_swallows_geocode_failure(self, monkeypatch):
        def boom(q, timeout=3.0):
            raise RuntimeError("network down")
        monkeypatch.setattr("scripts.planner.geocode", boom)
        trip = {"days": [{"stops": [{"lat": 0, "lng": 0}]}]}
        fix_endpoints(trip, "Nowhere", "Nowhere")  # must not raise


class TestDespreadStops:
    def test_leaves_distinct_stops_untouched(self):
        trip = {"days": [{"stops": [
            {"name": "A", "lat": 36.0, "lng": -114.0},
            {"name": "B", "lat": 37.0, "lng": -113.0},
        ]}]}
        despread_stops(trip)
        assert trip["days"][0]["stops"][0] == {"name": "A", "lat": 36.0, "lng": -114.0}
        assert trip["days"][0]["stops"][1] == {"name": "B", "lat": 37.0, "lng": -113.0}

    def test_nudges_colliding_stop_when_regeocode_unavailable(self, monkeypatch):
        monkeypatch.setattr("scripts.planner.geocode_near", lambda *a, **kw: None)
        trip = {"days": [{"stops": [
            {"name": "A", "lat": 36.0, "lng": -114.0},
            {"name": "B", "lat": 36.0, "lng": -114.0},  # collides with A
        ]}]}
        despread_stops(trip)
        a, b = trip["days"][0]["stops"]
        assert (a["lat"], a["lng"]) != (b["lat"], b["lng"])

    def test_no_usable_coordinates_is_a_noop(self):
        trip = {"days": [{"stops": [{"name": "A"}]}]}
        despread_stops(trip)  # must not raise
        assert trip["days"][0]["stops"] == [{"name": "A"}]


class TestPlanDemo:
    def test_matches_tahoe_keyword(self):
        trip = plan_demo({"start": "Sacramento, CA", "destination": "Lake Tahoe"}, "mountain")
        assert "Tahoe" in trip.get("title", "") or "tahoe" in json.dumps(trip).lower()

    def test_falls_back_to_default_sample(self):
        trip = plan_demo({"start": "Nowhereville", "destination": "Somewhere Else"}, "desert")
        assert trip.get("_demoNote", "").startswith("Demo mode")


class TestGenerateTripDemo:
    def test_sets_schema_defaults(self):
        trip = generate_trip({"start": "Las Vegas, NV", "destination": "Zion NP", "days": 3}, live=False)
        assert trip["lang"] == "en"
        assert trip.get("generationDate")
        assert trip.get("disclaimer")

    def test_chinese_lang_flag(self):
        trip = generate_trip({"lang": "zh-CN"}, live=False)
        assert trip["lang"] == "zh"
        assert "AI" not in trip["disclaimer"][:2]  # Chinese disclaimer, not the English one

    def test_step_cb_is_invoked(self):
        seen = []
        generate_trip({"start": "Las Vegas, NV"}, live=False, step_cb=seen.append)
        assert seen  # demo mode walks steps 1-4


def _fake_anthropic_module(response_text):
    """Build a minimal fake `anthropic` module good enough for regenerate_day."""
    usage = types.SimpleNamespace(input_tokens=10, output_tokens=5,
                                   cache_creation_input_tokens=0, cache_read_input_tokens=0)
    block = types.SimpleNamespace(type="text", text=response_text)
    message = types.SimpleNamespace(content=[block], usage=usage)

    class FakeMessages:
        def create(self, **kwargs):
            return message

    class FakeAnthropic:
        def __init__(self, *a, **kw):
            self.messages = FakeMessages()

    mod = types.ModuleType("anthropic")
    mod.Anthropic = FakeAnthropic
    return mod


class TestRegenerateDay:
    def test_preserves_original_date(self, monkeypatch):
        new_day_json = json.dumps({
            "date": "some-model-guessed-date", "title": "Updated Day",
            "from": "A", "to": "B", "driveMiles": 100, "driveTime": "2h",
            "stops": [], "fuelCharging": [], "meal": {"name": "Diner", "perPerson": 20}, "risks": [],
        })
        monkeypatch.setitem(sys.modules, "anthropic", _fake_anthropic_module(new_day_json))
        trip = {"title": "My Trip", "days": [
            {"date": "07/01", "title": "Day 1", "from": "A", "to": "B"},
            {"date": "07/02", "title": "Day 2", "from": "B", "to": "C"},
        ]}
        logged = []
        new_day = regenerate_day(trip, 1, "add more hiking", log_fn=logged.append)
        assert new_day["title"] == "Updated Day"
        assert new_day["date"] == "07/02"  # original date preserved, not the model's guess
        assert logged  # usage was reported
