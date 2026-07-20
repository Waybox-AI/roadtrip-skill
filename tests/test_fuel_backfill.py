"""Deterministic fuel/EV backfill after generation (no model call).

refresh_trip_fuel / refresh_trip_ev_corridor replace the model's guessed
energy economics with tools/fuel_client + tools/charging_client math, so the
webapp's single-shot path and the agent workflow share one source of truth.
"""

import copy

import pytest

from scripts.planner import refresh_trip_fuel, refresh_trip_ev_corridor
from tools import fuel_client


@pytest.fixture
def gas_trip():
    return {
        "lang": "en",
        "travelers": "2 adults",
        "totalMiles": 1180,
        "region": "desert",
        "vehicle": {"type": "gas", "model": "SUV", "mpg": 26, "rangeMiles": None},
        "budget": {
            "currency": "USD",
            "items": [
                {"label": "Fuel (~1180 mi at $5.55/gal)", "amount": 999,
                 "reliability": "estimate"},
                {"label": "Lodging (6 nights)", "amount": 900,
                 "reliability": "reference"},
            ],
            "total": 1899, "perPerson": 950,
        },
    }


@pytest.fixture
def ev_trip():
    return {
        "lang": "en",
        "travelers": "2 adults",
        "totalMiles": 900,
        "region": "coast",
        "vehicle": {"type": "EV", "model": "Model Y", "mpg": None, "rangeMiles": 280},
        "budget": {
            "currency": "USD",
            "items": [{"label": "Charging (public DC)", "amount": 777,
                       "reliability": "estimate"}],
            "total": 777, "perPerson": 389,
        },
        "days": [
            {"title": "Day 1", "to": "Monterey, CA", "driveMiles": 120,
             "fuelCharging": [{"name": "Supercharger", "type": "charge",
                               "powerKW": 250}]},
            {"title": "Day 2", "to": "Big Sur, CA", "driveMiles": 90,
             "fuelCharging": []},
            {"title": "Day 3 — layover", "to": "Big Sur, CA", "driveMiles": 0},
            {"title": "Day 4", "to": "Los Angeles, CA", "driveMiles": 210,
             "fuelCharging": [{"name": "Electrify America", "type": "charge",
                               "powerKW": 150},
                              {"name": "Shell", "type": "gas"}]},
        ],
    }


class TestFuelBackfill:
    def test_gas_line_comes_from_fuel_client(self, gas_trip):
        refresh_trip_fuel(gas_trip)
        item = gas_trip["budget"]["items"][0]
        expect = fuel_client.gas_cost(1180, 26, region="southwest")
        assert item["amount"] == int(round(expect["cost"]))
        assert item["label"] == expect["label"]
        assert item["reliability"] == "estimate"
        assert item["source"] == "fuel_client"

    def test_totals_recomputed(self, gas_trip):
        refresh_trip_fuel(gas_trip)
        b = gas_trip["budget"]
        assert b["total"] == sum(i["amount"] for i in b["items"])
        assert b["perPerson"] == int(round(b["total"] / 2))

    def test_non_usd_budget_is_left_alone(self, gas_trip):
        # fuel_client's price priors are US-only — a CNY budget must keep the
        # model's local-currency estimate instead of getting a USD line.
        gas_trip["budget"]["currency"] = "CNY"
        before = copy.deepcopy(gas_trip["budget"])
        refresh_trip_fuel(gas_trip)
        assert gas_trip["budget"] == before

    def test_units_currency_fallback_also_guards(self, gas_trip):
        del gas_trip["budget"]["currency"]
        gas_trip["units"] = {"distance": "km", "temp": "C", "currency": "CNY"}
        before = copy.deepcopy(gas_trip["budget"])
        refresh_trip_fuel(gas_trip)
        assert gas_trip["budget"] == before

    def test_efficiency_overrides_vehicle_mpg(self, gas_trip):
        refresh_trip_fuel(gas_trip, efficiency="30")
        expect = fuel_client.gas_cost(1180, 30.0, region="southwest")
        assert gas_trip["budget"]["items"][0]["amount"] == int(round(expect["cost"]))

    def test_ev_line_uses_ev_cost(self, ev_trip):
        refresh_trip_fuel(ev_trip)
        item = ev_trip["budget"]["items"][0]
        expect = fuel_client.ev_cost(900)
        assert item["amount"] == int(round(expect["cost"]))
        assert item["source"] == "fuel_client"

    def test_zh_label(self, gas_trip):
        gas_trip["lang"] = "zh"
        refresh_trip_fuel(gas_trip)
        label = gas_trip["budget"]["items"][0]["label"]
        assert "燃油" in label and "英里" in label

    def test_appends_when_no_fuel_line(self, gas_trip):
        gas_trip["budget"]["items"] = [{"label": "Lodging (6 nights)",
                                        "amount": 900, "reliability": "reference"}]
        refresh_trip_fuel(gas_trip)
        items = gas_trip["budget"]["items"]
        assert len(items) == 2
        assert items[-1]["source"] == "fuel_client"

    def test_other_lines_untouched(self, gas_trip):
        before = copy.deepcopy(gas_trip["budget"]["items"][1])
        refresh_trip_fuel(gas_trip)
        assert gas_trip["budget"]["items"][1] == before

    def test_missing_miles_is_a_noop(self, gas_trip):
        del gas_trip["totalMiles"]
        before = copy.deepcopy(gas_trip)
        refresh_trip_fuel(gas_trip)
        assert gas_trip == before

    def test_missing_budget_never_raises(self):
        trip = {"totalMiles": 500, "vehicle": {"type": "gas"}}
        assert refresh_trip_fuel(trip) is trip


class TestEvCorridorBackfill:
    def test_fills_evplan_from_days(self, ev_trip):
        refresh_trip_ev_corridor(ev_trip)
        ev = ev_trip["evPlan"]
        # the 0-mile layover day is not a driving leg
        assert [l["to"] for l in ev["legs"]] == \
            ["Monterey, CA", "Big Sur, CA", "Los Angeles, CA"]
        assert ev["usableRange"] == 280
        leg1 = ev["legs"][0]
        assert leg1["charger"] is True and leg1["chargerKW"] == 250
        assert ev["legs"][1]["charger"] is False
        # gas-only entries don't count as chargers; kW is the max charge stop
        assert ev["legs"][2]["chargerKW"] == 150

    def test_soc_math_matches_charging_client(self, ev_trip):
        from tools import charging_client
        refresh_trip_ev_corridor(ev_trip)
        legs = [{"to": "Monterey, CA", "miles": 120.0, "charger": True,
                 "chargerKW": 250},
                {"to": "Big Sur, CA", "miles": 90.0, "charger": False,
                 "chargerKW": None},
                {"to": "Los Angeles, CA", "miles": 210.0, "charger": True,
                 "chargerKW": 150}]
        assert ev_trip["evPlan"] == charging_client.corridor(legs, 280)

    def test_existing_evplan_preserved(self, ev_trip):
        ev_trip["evPlan"] = {"source": "model", "legs": [{"to": "X"}]}
        refresh_trip_ev_corridor(ev_trip)
        assert ev_trip["evPlan"]["legs"] == [{"to": "X"}]

    def test_gas_trip_gets_no_evplan(self, gas_trip):
        refresh_trip_ev_corridor(gas_trip)
        assert "evPlan" not in gas_trip

    def test_missing_range_is_a_noop(self, ev_trip):
        ev_trip["vehicle"]["rangeMiles"] = None
        refresh_trip_ev_corridor(ev_trip)
        assert "evPlan" not in ev_trip
