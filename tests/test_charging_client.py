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
