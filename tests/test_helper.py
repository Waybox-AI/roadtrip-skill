import pytest
from scripts.helper import (
    detect_days,
    detect_vehicle,
    detect_mode,
    detect_region,
    detect_start,
    detect_date,
    detect_party,
    drive_intensity,
    compare_routes,
)


class TestDetectDays:
    def test_days_word(self):
        assert detect_days("7 days in Utah") == 7

    def test_day_singular(self):
        assert detect_days("a 1 day drive") == 1

    def test_hyphenated(self):
        assert detect_days("10-day road trip") == 10

    def test_chinese(self):
        assert detect_days("我想去旅行7天") == 7

    def test_none(self):
        assert detect_days("drive from Vegas") is None


class TestDetectVehicle:
    def test_tesla_is_ev(self):
        assert detect_vehicle("I have a Tesla") == "EV"

    def test_electric_keyword(self):
        assert detect_vehicle("planning an electric car trip") == "EV"

    def test_rv(self):
        assert detect_vehicle("we have an RV") == "RV"

    def test_suv_is_gas(self):
        assert detect_vehicle("driving my SUV") == "gas"

    def test_none(self):
        assert detect_vehicle("road trip next month") is None


class TestDetectMode:
    def test_light_no_clues(self):
        assert detect_mode("I want to drive from Vegas to Zion") == "light"

    def test_heavy_via_multiple_day_markers(self):
        assert detect_mode("Day 1: Vegas. Day 2: Zion. Day 3: Bryce.") == "heavy"

    def test_heavy_via_keyword_plus_day_marker(self):
        assert detect_mode("here is my itinerary: Day 1 Vegas Day 2 Zion") == "heavy"


class TestDetectRegion:
    def test_desert(self):
        assert detect_region("southwest Utah and Nevada") == "desert"

    def test_coast(self):
        assert detect_region("Pacific Coast Highway Big Sur") == "coast"

    def test_forest(self):
        assert detect_region("Pacific Northwest Washington Olympic") == "forest"

    def test_mountain(self):
        assert detect_region("Rocky Mountain Colorado") == "mountain"

    def test_no_match_returns_none(self):
        assert detect_region("a nice trip") is None


class TestDetectStart:
    def test_from_city_state(self):
        assert detect_start("from Las Vegas, NV to Zion") == "Las Vegas, NV"

    def test_starting_in(self):
        assert detect_start("starting in Denver") == "Denver"

    def test_state_fallback(self):
        # Falls back to first US state name found
        result = detect_start("exploring utah")
        assert result == "Utah"

    def test_none(self):
        assert detect_start("a 7 day trip") is None


class TestDetectDate:
    def test_iso_date(self):
        assert detect_date("departing 2026-07-04") == "2026-07-04"

    def test_month_name_only(self):
        assert detect_date("heading out in July") == "July"

    def test_month_with_day(self):
        assert detect_date("leaving August 15") == "August 15"

    def test_slash_date(self):
        assert detect_date("trip on 2026/09/01") == "2026/09/01"

    def test_none(self):
        assert detect_date("no date mentioned") is None


class TestDetectParty:
    def test_adults(self):
        assert "2 adults" in detect_party("2 adults")

    def test_adults_and_kids(self):
        result = detect_party("2 adults and 3 kids")
        assert "adults" in result
        assert "kids" in result

    def test_family(self):
        assert "family" in detect_party("family road trip")

    def test_couple(self):
        assert "couple" in detect_party("a couple's trip")

    def test_none(self):
        assert detect_party("solo drive") is None


class TestDriveIntensity:
    def test_relaxed(self):
        # 100 mi / 5 days = 20 mi/day → ~0.36 h/day → relaxed
        assert drive_intensity(100, 5).startswith("relaxed")

    def test_intense(self):
        # 700 mi / 2 days = 350 mi/day → ~6.4 h/day → intense
        assert drive_intensity(700, 2).startswith("intense")

    def test_soft_party_lowers_cap(self):
        # family party lowers cap from 5h to 4h
        # 350 mi / 2 days = 175 mi/day → 3.18 h/day
        # 60% of 4h cap = 2.4h → moderate (not relaxed)
        result = drive_intensity(350, 2, party="family trip")
        assert result.startswith("moderate") or result.startswith("intense")

    def test_zero_days_returns_unknown(self):
        assert drive_intensity(500, 0) == "unknown"

    def test_none_days_returns_unknown(self):
        assert drive_intensity(500, None) == "unknown"


class TestCompareRoutes:
    def test_fills_drive_intensity(self):
        options = [{"name": "Route A", "miles": 200, "days": 3}]
        result = compare_routes(options)
        assert "routeOptions" in result
        assert "driveIntensity" in result["routeOptions"][0]

    def test_preserves_existing_drive_intensity(self):
        options = [{"name": "Route A", "miles": 200, "days": 3,
                    "driveIntensity": "custom label"}]
        result = compare_routes(options)
        assert result["routeOptions"][0]["driveIntensity"] == "custom label"

    def test_multiple_options_all_returned(self):
        options = [
            {"name": "A", "miles": 100, "days": 2},
            {"name": "B", "miles": 300, "days": 2},
        ]
        result = compare_routes(options)
        assert len(result["routeOptions"]) == 2
