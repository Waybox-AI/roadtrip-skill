"""Deterministic budget recomputation after a trip edit (no model call)."""

import copy
import json
import os

import pytest

from scripts import planner
from scripts.planner import _recompute_budget, _travelers_count

_ROOT = os.path.join(os.path.dirname(__file__), "..")


@pytest.fixture
def trip():
    with open(os.path.join(_ROOT, "assets", "tripData.example.json"),
              encoding="utf-8") as f:
        return json.load(f)


def _item(trip, needle):
    return next(i for i in trip["budget"]["items"] if needle in i["label"].lower())


class TestTravelers:
    def test_simple(self):
        assert _travelers_count({"travelers": "2 adults"}) == 2

    def test_multi_group(self):
        assert _travelers_count({"travelers": "2 adults + 1 kid"}) == 3

    def test_missing_defaults_to_one(self):
        assert _travelers_count({}) == 1


class TestRecompute:
    def test_lodging_from_the_lodging_list(self, trip):
        for l in trip["lodging"]:
            if "bryce" in l["area"].lower():
                l["pricePerNight"], l["nights"] = 95, 2
        _recompute_budget(trip, 7, trip["totalMiles"])
        expect = sum(l["pricePerNight"] * l["nights"] for l in trip["lodging"])
        lodging = _item(trip, "lodging")
        assert lodging["amount"] == expect
        assert "7 nights" in lodging["label"]        # 2+1+1+... label rewritten

    def test_fuel_scales_with_miles(self, trip):
        before = _item(trip, "fuel")["amount"]
        trip["totalMiles"] = 2360                    # exactly doubled
        _recompute_budget(trip, 7, 1180)
        fuel = _item(trip, "fuel")
        assert fuel["amount"] == before * 2
        assert "2,360 mi" in fuel["label"]           # thousands separator kept

    def test_per_day_items_scale_with_days(self, trip):
        food_before = _item(trip, "food")["amount"]
        car_before = _item(trip, "rental")["amount"]
        trip["days"].append(dict(trip["days"][-1]))  # 7 -> 8 days
        _recompute_budget(trip, 7, trip["totalMiles"])
        assert _item(trip, "food")["amount"] == round(food_before * 8 / 7)
        assert _item(trip, "rental")["amount"] == round(car_before * 8 / 7)
        assert "8 days" in _item(trip, "food")["label"]
        assert "8 days" in _item(trip, "rental")["label"]

    def test_fixed_items_untouched(self, trip):
        park = copy.deepcopy(_item(trip, "national park"))
        tour = copy.deepcopy(_item(trip, "antelope"))
        misc = copy.deepcopy(_item(trip, "misc"))
        trip["days"].append(dict(trip["days"][-1]))
        trip["totalMiles"] = 2000
        _recompute_budget(trip, 7, 1180)
        assert _item(trip, "national park") == park
        assert _item(trip, "antelope") == tour
        assert _item(trip, "misc") == misc

    def test_total_and_per_person_always_consistent(self, trip):
        trip["days"].append(dict(trip["days"][-1]))
        trip["totalMiles"] = 1300
        _recompute_budget(trip, 7, 1180)
        items = sum(i["amount"] for i in trip["budget"]["items"])
        assert trip["budget"]["total"] == items
        assert trip["budget"]["perPerson"] == round(items / 2)

    def test_reliability_grades_preserved(self, trip):
        grades = [i["reliability"] for i in trip["budget"]["items"]]
        trip["totalMiles"] = 1500
        _recompute_budget(trip, 7, 1180)
        assert [i["reliability"] for i in trip["budget"]["items"]] == grades

    def test_no_day_change_leaves_day_items_alone(self, trip):
        food = copy.deepcopy(_item(trip, "food"))
        _recompute_budget(trip, 7, trip["totalMiles"])   # same days, same miles
        assert _item(trip, "food") == food

    def test_zero_old_miles_does_not_divide(self, trip):
        fuel = copy.deepcopy(_item(trip, "fuel"))
        _recompute_budget(trip, 7, 0)
        assert _item(trip, "fuel") == fuel

    def test_missing_budget_is_noop(self):
        t = {"days": [{}], "lodging": []}
        _recompute_budget(t, 1, 10)          # must not raise
        assert "budget" not in t

    def test_garbage_amounts_skipped(self, trip):
        trip["budget"]["items"][0]["amount"] = "lots"
        trip["totalMiles"] = 2000
        _recompute_budget(trip, 7, 1180)
        assert trip["budget"]["items"][0]["amount"] == "lots"
        assert isinstance(trip["budget"]["total"], int)


class TestChineseLabels:
    def test_zh_lodging_fuel_and_days(self):
        trip = {
            "travelers": "2 adults",
            "days": [{}] * 8,
            "totalMiles": 1300,
            "lodging": [{"pricePerNight": 100, "nights": 7, "area": "X"}],
            "budget": {"currency": "USD", "items": [
                {"label": "住宿（6 晚）", "amount": 900, "reliability": "reference"},
                {"label": "燃油（约 1,180 英里）", "amount": 186, "reliability": "estimate"},
                {"label": "餐饮（7 天，2 人）", "amount": 700, "reliability": "estimate"},
            ], "total": 1786, "perPerson": 893},
        }
        _recompute_budget(trip, 7, 1180)
        items = {i["label"]: i["amount"] for i in trip["budget"]["items"]}
        assert any("住宿（7 晚）" in k and v == 700 for k, v in items.items())
        assert any("1,300 英里" in k for k in items)
        assert any("8 天" in k and v == 800 for k, v in items.items())
        assert trip["budget"]["total"] == sum(items.values())
