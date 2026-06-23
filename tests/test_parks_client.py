import datetime as dt
import pytest
from tools.parks_client import book_by, countdown, RELEASE_RULES


class TestBookBy:
    def test_future_campground_date(self):
        # arrival 2027-01-01, today well before the 180-day release window
        today = dt.date(2026, 1, 1)
        expected = (dt.date(2027, 1, 1) - dt.timedelta(days=180)).isoformat()
        assert book_by("2027-01-01", "campground", today=today) == expected

    def test_past_deadline_clamps_to_today(self):
        # release date already passed → clamp to today, not a date in the past
        today = dt.date(2026, 6, 20)
        result = book_by("2026-06-25", "campground", today=today)
        assert result == today.isoformat()

    def test_arrival_same_day_as_today_clamps_to_today(self):
        today = dt.date(2026, 6, 23)
        result = book_by("2026-06-23", "campground", today=today)
        assert result == today.isoformat()

    def test_timed_entry_future_date(self):
        # arrival 2026-06-20, timed-entry = 7 days → release 2026-06-13
        today = dt.date(2026, 6, 1)
        expected = (dt.date(2026, 6, 20) - dt.timedelta(days=7)).isoformat()
        assert book_by("2026-06-20", "timed-entry", today=today) == expected

    def test_in_park_lodge_future_date(self):
        # today 2025-01-01, arrival 2027-07-01; 395-day window opens 2026-06-01
        today = dt.date(2025, 1, 1)
        expected = (dt.date(2027, 7, 1) - dt.timedelta(days=395)).isoformat()
        assert book_by("2027-07-01", "in-park-lodge", today=today) == expected

    def test_unknown_rule_returns_none(self):
        assert book_by("2027-01-01", "nonexistent-rule") is None

    def test_result_never_before_today(self):
        today = dt.date(2026, 6, 23)
        for rule in RELEASE_RULES:
            result = book_by("2026-07-01", rule, today=today)
            if result is not None:
                assert result >= today.isoformat(), (
                    f"rule '{rule}' returned a past date: {result}"
                )


class TestCountdown:
    def test_returns_expected_keys(self):
        result = countdown("2027-06-01")
        assert result["source"] == "rules"
        assert "bookingCountdown" in result
        assert "disclaimer" in result

    def test_default_three_items(self):
        result = countdown("2027-06-01")
        assert len(result["bookingCountdown"]) == 3

    def test_each_item_has_required_fields(self):
        result = countdown("2027-06-01")
        for item in result["bookingCountdown"]:
            assert "item" in item
            assert "bookBy" in item
            assert "where" in item
            assert "priority" in item
            assert "note" in item

    def test_custom_items(self):
        items = [("My Campsite", "campground", "Recreation.gov")]
        result = countdown("2027-06-01", items=items)
        assert len(result["bookingCountdown"]) == 1
        assert result["bookingCountdown"][0]["item"] == "My Campsite"

    def test_past_arrival_book_by_equals_arrival(self):
        # When arrival is in the past, book_by clamps to min(today, arrival) = arrival.
        # The countdown should reflect that date, not a future date.
        arrival = "2020-01-01"
        result = countdown(arrival)
        for item in result["bookingCountdown"]:
            assert item["bookBy"] == arrival
