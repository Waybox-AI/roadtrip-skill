"""Categorized booking-tab regression coverage."""

import json
from pathlib import Path

from assets.generate import build_html
from scripts import planner
from tools.parks_client import countdown


ROOT = Path(__file__).resolve().parents[1]


def _template():
    return (ROOT / "assets" / "template.html").read_text(encoding="utf-8")


def test_booking_tabs_use_timeline_layout_in_requested_order():
    template = _template()
    attraction = template.index('{ id: "attraction", icon: "◇"')
    restaurant = template.index('{ id: "restaurant", icon: "⌁"')
    hotel = template.index('{ id: "hotel", icon: "▣"')
    assert attraction < restaurant < hotel
    assert 'class="booking-timeline"' in template
    assert 'Reservation countdown — book these before they sell out' not in template


def test_booking_tabs_are_accessible_and_keyboard_operable():
    template = _template()
    assert 'role="tablist"' in template
    assert 'role="tab"' in template
    assert 'role="tabpanel"' in template
    assert 'aria-controls="booking-panel-' in template
    assert 'event.key === "ArrowRight"' in template
    assert 'event.key === "ArrowLeft"' in template
    assert 'event.key === "Home"' in template
    assert 'event.key === "End"' in template


def test_example_renders_explicit_categories_and_legacy_fallback():
    trip = json.loads(
        (ROOT / "assets" / "tripData.example.json").read_text(encoding="utf-8")
    )
    template = _template()
    html = build_html(trip, template)
    assert '"category": "attraction"' in html
    assert '"category": "restaurant"' in html
    assert '"category": "hotel"' in html
    assert 'function bookingCategory(item)' in html
    assert 'return "attraction";' in html


def test_parks_countdown_assigns_categories():
    items = countdown("2030-09-12")["bookingCountdown"]
    assert [item["category"] for item in items] == ["hotel", "attraction", "hotel"]


def test_stay_edit_preserves_valid_category_and_drops_invalid_category():
    trip = {"bookingCountdown": []}
    planner._apply_stay_bookings(trip, [], [
        {"item": "Dinner", "bookBy": "2030-08-12", "where": "Cafe",
         "category": "restaurant", "priority": "medium"},
        {"item": "Permit", "bookBy": "2030-08-13", "where": "Park",
         "category": "other", "priority": "high"},
    ])
    assert trip["bookingCountdown"][0]["category"] == "restaurant"
    assert "category" not in trip["bookingCountdown"][1]
