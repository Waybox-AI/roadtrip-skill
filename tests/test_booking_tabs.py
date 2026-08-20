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
    assert '"amount": 90' in html
    assert '"unit": "person"' in html
    assert 'function bookingPriceMarkup(item)' in html
    assert 'Check price' in html


def test_lodging_table_is_removed_but_budget_rendering_remains():
    template = _template()
    assert 'id="lodging"' not in template
    assert 'function renderLodging()' not in template
    assert '🛏️ Lodging' not in template
    assert 'id="budget"' in template
    assert 'renderBudget(); renderTips(); renderShare();' in template


def test_hotel_tab_merges_every_lodging_with_matching_deadlines():
    trip = json.loads(
        (ROOT / "assets" / "tripData.example.json").read_text(encoding="utf-8")
    )
    hotel_deadlines = [
        item for item in trip["bookingCountdown"] if item.get("category") == "hotel"
    ]
    assert len(trip["lodging"]) == 4
    assert len(hotel_deadlines) == 2

    template = _template()
    assert "function hotelBookingItems(list)" in template
    assert "var hotels = Array.isArray(T.lodging)" in template
    assert 'groups.hotel = hotelBookingItems(list);' in template
    assert 'stayArea: hotel.area || ""' in template
    assert "nights: hotel.nights" in template
    assert 'item.nights + " night"' in template


def test_lodging_alone_still_renders_booking_tabs():
    template = _template()
    assert "if (!list.length && !lodging.length)" in template
    assert "if (!hotels.length) return deadlines;" in template


def test_parks_countdown_assigns_categories():
    items = countdown("2030-09-12")["bookingCountdown"]
    assert [item["category"] for item in items] == ["hotel", "attraction", "hotel"]


def test_stay_edit_preserves_valid_category_and_drops_invalid_category():
    trip = {"bookingCountdown": []}
    planner._apply_stay_bookings(trip, [], [
        {"item": "Dinner", "bookBy": "2030-08-12", "where": "Cafe",
         "category": "restaurant", "priority": "medium",
         "price": {"amount": 45.5, "currency": "usd", "unit": "person",
                   "reliability": "estimate"}},
        {"item": "Permit", "bookBy": "2030-08-13", "where": "Park",
         "category": "other", "priority": "high",
         "price": {"amount": -1, "currency": "USD", "unit": "person"}},
    ])
    assert trip["bookingCountdown"][0]["category"] == "restaurant"
    assert trip["bookingCountdown"][0]["price"] == {
        "amount": 45.5,
        "currency": "USD",
        "unit": "person",
        "reliability": "estimate",
    }
    assert "category" not in trip["bookingCountdown"][1]
    assert "price" not in trip["bookingCountdown"][1]
