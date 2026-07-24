import pytest
from tools.charging_client import leg_ok, corridor


class TestLegOk:
    def test_ok_leg(self):
        # 100 mi, 200 mi range → limit = 140. 100 ≤ 140 → ok
        result = leg_ok(100, 200)
        assert result["ok"] is True
        assert result["safeLegLimit"] == 140.0
        assert result["legMiles"] == 100
        assert result["usableRange"] == 200

    def test_not_ok_leg(self):
        # 150 mi, 200 mi range → limit = 140. 150 > 140 → not ok
        result = leg_ok(150, 200)
        assert result["ok"] is False
        assert "charging stop" in result["advice"]

    def test_exactly_at_limit_is_ok(self):
        # 140 mi, 200 mi range → limit = 140.0. 140 ≤ 140 → ok
        result = leg_ok(140, 200)
        assert result["ok"] is True

    def test_one_mile_over_limit_not_ok(self):
        result = leg_ok(141, 200)
        assert result["ok"] is False

    def test_custom_safe_fraction(self):
        result = leg_ok(80, 100, safe_fraction=0.8)
        assert result["ok"] is True
        assert result["safeLegLimit"] == 80.0

    def test_custom_fraction_not_ok(self):
        result = leg_ok(81, 100, safe_fraction=0.8)
        assert result["ok"] is False


class TestCorridor:
    LEGS = [
        {"to": "Stop A", "miles": 60, "charger": True, "chargerKW": 150},
        {"to": "Stop B", "miles": 80, "charger": True, "chargerKW": 250},
        {"to": "Stop C", "miles": 50, "charger": False, "chargerKW": None},
    ]

    def test_basic_simulation_structure(self):
        result = corridor(self.LEGS, 280)
        assert result["source"] == "model"
        assert len(result["legs"]) == len(self.LEGS)
        assert result["usableRange"] == 280
        assert "warnings" in result

    def test_depart_soc_matches_start(self):
        result = corridor(self.LEGS, 280, start_soc=90)
        assert result["legs"][0]["departSoC"] == 90

    def test_arrive_soc_decreases_from_depart(self):
        result = corridor(self.LEGS, 280, start_soc=90)
        for leg in result["legs"]:
            assert leg["arriveSoC"] <= leg["departSoC"]

    def test_winter_derate_reduces_effective_range(self):
        result = corridor(self.LEGS, 280, winter_derate=0.25)
        assert result["effectiveRange"] == pytest.approx(280 * 0.75)

    def test_winter_derate_annotation_on_warning(self):
        # A leg that barely fails without derate should mention winter derate
        legs = [{"to": "Far", "miles": 240, "charger": False, "chargerKW": None}]
        result = corridor(legs, 280, start_soc=90, winter_derate=0.25)
        # eff_range = 210; need = 240/210*100 = 114.3%; arrive = 90 - 114.3 = -24.3 < 10
        assert len(result["warnings"]) > 0
        assert any("winter derate" in w for w in result["warnings"])

    def test_missing_charger_generates_warning(self):
        # Stop B has no charger but next leg needs a top-up
        legs = [
            {"to": "A", "miles": 60,  "charger": True,  "chargerKW": 150},
            {"to": "B", "miles": 200, "charger": False, "chargerKW": None},
            {"to": "C", "miles": 50,  "charger": True,  "chargerKW": 150},
        ]
        result = corridor(legs, 280, start_soc=90)
        assert any("No charger" in w or "charger" in w.lower() for w in result["warnings"])

    def test_non_positive_range_returns_error(self):
        result = corridor(self.LEGS, 0)
        assert result["source"] == "error"


class TestCorridorMidLegStops:
    def test_stop_splits_leg_into_sublegs(self):
        legs = [{"to": "Far City", "miles": 400, "charger": True, "chargerKW": 120,
                 "dayIndex": 2,
                 "stops": [{"name": "Midway SC", "powerKW": 250, "frac": 0.5}]}]
        out = corridor(legs, 280, start_soc=90)["legs"]
        assert len(out) == 2
        assert out[0]["to"] == "Midway SC" and out[0]["midLeg"] is True
        assert out[0]["miles"] == 200 and out[1]["miles"] == 200
        assert out[0]["charger"] is True and out[0]["chargerKW"] == 250
        assert out[1]["to"] == "Far City" and "midLeg" not in out[1]
        assert out[0]["dayIndex"] == 2 and out[1]["dayIndex"] == 2

    def test_split_makes_long_leg_feasible(self):
        base = {"to": "Far City", "miles": 400, "charger": True, "chargerKW": 120}
        unsplit = corridor([dict(base)], 280, start_soc=90)
        assert unsplit["legs"][0]["ok"] is False
        split = corridor(
            [dict(base, stops=[{"name": "Mid", "powerKW": 250, "frac": 0.5}])],
            280, start_soc=90)
        assert all(l["ok"] for l in split["legs"])
        assert split["warnings"] == []

    def test_missing_fracs_space_evenly(self):
        legs = [{"to": "End", "miles": 300, "charger": True,
                 "stops": [{"name": "S1", "powerKW": 150},
                           {"name": "S2", "powerKW": 150}]}]
        out = corridor(legs, 280)["legs"]
        assert [round(l["miles"]) for l in out] == [100, 100, 100]

    def test_unsorted_fracs_fall_back_to_even(self):
        legs = [{"to": "End", "miles": 300, "charger": True,
                 "stops": [{"name": "S1", "powerKW": 150, "frac": 0.9},
                           {"name": "S2", "powerKW": 150, "frac": 0.2}]}]
        out = corridor(legs, 280)["legs"]
        assert [round(l["miles"]) for l in out] == [100, 100, 100]

    def test_infeasible_leg_reports_shortfall_and_stops_needed(self):
        legs = [{"to": "Far", "miles": 500, "charger": False}]
        out = corridor(legs, 280, start_soc=90)["legs"][0]
        assert out["ok"] is False
        assert out["shortByMiles"] == 276
        assert out["stopsNeeded"] == 2

    def test_charge_target_pct_field(self):
        legs = [
            {"to": "A", "miles": 60, "charger": True, "chargerKW": 150},
            {"to": "B", "miles": 200, "charger": False},
        ]
        out = corridor(legs, 280, start_soc=90)["legs"]
        assert out[0]["chargeTargetPct"] == out[0]["chargeTo"]

    def test_legs_without_stops_unchanged(self):
        legs = [{"to": "A", "miles": 60, "charger": True, "chargerKW": 150}]
        out = corridor(legs, 280)["legs"]
        assert len(out) == 1 and "midLeg" not in out[0]

    def test_day_end_charges_overnight_to_max(self):
        # A day-end stop is an overnight charge: fill to the max target, not
        # merely enough for the next morning's short hop.
        legs = [
            {"to": "A", "miles": 60, "charger": True, "chargerKW": 7},
            {"to": "B", "miles": 30, "charger": True, "chargerKW": 150},
            {"to": "C", "miles": 30, "charger": False},
        ]
        out = corridor(legs, 280, start_soc=90)["legs"]
        assert out[0]["chargeTo"] == 90

    def test_mid_leg_stop_charges_just_enough(self):
        # A mid-leg fast stop still charges only what the next hop needs.
        legs = [{"to": "End", "miles": 200, "charger": True,
                 "stops": [{"name": "Mid", "powerKW": 250, "frac": 0.5}]}]
        out = corridor(legs, 280, start_soc=90)["legs"]
        # next hop is 100 mi = 35.7% + 20% floor/buffer ≈ 56%
        assert out[0]["midLeg"] is True and out[0]["chargeTo"] == 56
