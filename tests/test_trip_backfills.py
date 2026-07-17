"""Deterministic post-generation backfills: routing, booking countdown,
lodging links, cross-border rules and the route-comparison table.

Each refresh_trip_* replaces a hard number the single-shot model path had to
guess with the same tools/ client the agent workflow uses.
"""

import copy
import datetime

import pytest

from scripts.planner import (refresh_trip_routing, refresh_trip_countdown,
                             refresh_trip_lodging_links, refresh_trip_border,
                             refresh_trip_route_options)
from tools import routing_client, parks_client


@pytest.fixture
def trip():
    return {
        "lang": "en",
        "travelers": "2 adults",
        "totalMiles": 500,
        "dateRange": "2026-09-12 ~ 2026-09-14",
        "generationDate": "2026-07-14",
        "budget": {"currency": "USD",
                   "items": [{"label": "Fuel (~500 mi)", "amount": 80,
                              "reliability": "estimate"}],
                   "total": 80, "perPerson": 40},
        "days": [
            {"date": "09/12", "title": "Day 1", "driveMiles": 160,
             "driveTime": "3h00m",
             "stops": [{"name": "Las Vegas", "lat": 36.17, "lng": -115.14},
                       {"name": "Zion", "lat": 37.30, "lng": -113.03}]},
            {"date": "09/13", "title": "Day 2 — layover", "driveMiles": 0,
             "stops": [{"name": "Zion again", "lat": None, "lng": None}]},
            {"date": "09/14", "title": "Day 3", "driveMiles": 340,
             "driveTime": "5h00m",
             "stops": [{"name": "Bryce", "lat": 37.59, "lng": -112.19}]},
        ],
        "lodging": [{"name": "Cliffrose Lodge", "area": "Springdale, UT",
                     "nights": 2, "pricePerNight": 250, "rating": "4.5",
                     "booked": False}],
        "bookingCountdown": [
            {"item": "Watchman Campground", "bookBy": "2026-01-01",
             "where": "Recreation.gov", "priority": "high"},
            {"item": "Angels Landing timed permit", "bookBy": "2026-01-01",
             "where": "Recreation.gov", "priority": "high"},
            {"item": "Some unclassifiable thing", "bookBy": "2026-05-05",
             "where": "somewhere", "priority": "low"},
        ],
    }


class TestRoutingBackfill:
    def test_osrm_result_applied_and_chained(self, trip, monkeypatch):
        calls = []

        def fake_route(wps, timeout=8):
            calls.append(wps)
            return {"source": "osrm", "miles": 100.0 * len(calls),
                    "driveTime": "%dh00m" % len(calls), "hours": float(len(calls))}

        monkeypatch.setattr(routing_client, "route", fake_route)
        refresh_trip_routing(trip)
        # day 1 routed within its own stops; the layover day (no coords) is
        # skipped; day 3 starts from day 1's last stop (overnights chain)
        assert calls[0] == [(36.17, -115.14), (37.30, -113.03)]
        assert calls[1] == [(37.30, -113.03), (37.59, -112.19)]
        assert trip["days"][0]["driveMiles"] == 100
        assert trip["days"][0]["driveSource"] == "osrm"
        assert "driveSource" not in trip["days"][1]
        assert trip["days"][2]["driveMiles"] == 200
        assert trip["totalMiles"] == 300  # 100 + 0 + 200

    def test_fallback_leaves_trip_untouched(self, trip, monkeypatch):
        monkeypatch.setattr(routing_client, "route",
                            lambda wps, timeout=8: {"source": "fallback",
                                                    "miles": 1.0,
                                                    "driveTime": "0h01m"})
        before = copy.deepcopy(trip)
        refresh_trip_routing(trip)
        assert trip == before

    def test_exception_never_raises(self, trip, monkeypatch):
        def boom(wps, timeout=8):
            raise RuntimeError("network down")
        monkeypatch.setattr(routing_client, "route", boom)
        before = copy.deepcopy(trip)
        assert refresh_trip_routing(trip) is trip
        assert trip == before


class TestCountdownBackfill:
    TODAY = datetime.date(2026, 7, 14)

    def test_rule_dates_from_parks_client(self, trip):
        refresh_trip_countdown(trip, today=self.TODAY)
        camp, permit, other = trip["bookingCountdown"]
        assert camp["bookBy"] == parks_client.book_by("2026-09-12", "campground",
                                                      self.TODAY)
        assert camp["source"] == "parks_client"
        assert permit["bookBy"] == parks_client.book_by("2026-09-12", "timed-entry",
                                                        self.TODAY)
        # unmatched labels keep the model's date, untagged
        assert other["bookBy"] == "2026-05-05" and "source" not in other

    def test_never_before_today(self, trip):
        refresh_trip_countdown(trip, today=self.TODAY)
        for item in trip["bookingCountdown"][:2]:
            assert item["bookBy"] >= self.TODAY.isoformat()

    def test_no_start_date_is_a_noop(self, trip):
        del trip["days"][0]["date"]
        before = copy.deepcopy(trip)
        refresh_trip_countdown(trip, today=self.TODAY)
        assert trip == before


class TestLodgingLinks:
    def test_links_attached(self, trip):
        refresh_trip_lodging_links(trip)
        links = trip["lodging"][0]["links"]
        assert "Cliffrose+Lodge%2C+Springdale%2C+UT" in links["booking"]
        assert set(links) >= {"booking", "airbnb", "google_hotels"}

    def test_existing_links_kept(self, trip):
        trip["lodging"][0]["links"] = {"booking": "https://example.com"}
        refresh_trip_lodging_links(trip)
        assert trip["lodging"][0]["links"] == {"booking": "https://example.com"}


class TestBorderBackfill:
    def test_cross_border_trip(self, trip):
        trip["crossings"] = [{"from": "US", "to": "CA", "day": 2},
                             {"from": "CA", "to": "US", "day": 5}]
        refresh_trip_border(trip)
        cb = trip["crossBorder"]
        assert cb["summary"] == "US→CA · CA→US"
        assert [c["to"] for c in cb["crossings"]] == ["CA", "US"]
        assert cb["crossings"][0]["unitsAfter"]["distance"] == "km"
        # 3 days abroad = 72h ≥ 48h → standard USD 800 exemption
        df = cb["dutyFree"]
        assert (df["amount"], df["currency"], df["tier"]) == (800, "USD", "standard")

    def test_short_hop_reduced_exemption(self, trip):
        trip["crossings"] = [{"from": "US", "to": "CA", "day": 3},
                             {"from": "CA", "to": "US", "day": 4}]
        refresh_trip_border(trip)
        assert trip["crossBorder"]["dutyFree"]["tier"] == "reduced"

    def test_domestic_trip_untouched(self, trip):
        before = copy.deepcopy(trip)
        refresh_trip_border(trip)
        assert trip == before

    def test_bad_countries_ignored(self, trip):
        trip["crossings"] = [{"from": "US", "to": "FR", "day": 2}]
        refresh_trip_border(trip)
        assert "crossBorder" not in trip


class TestRouteOptions:
    PAYLOAD = {
        "party": "2 adults",
        "route": {"label": "Grand Circle"},
        "routes": [
            {"label": "Grand Circle", "totalMiles": 1180, "drivingDays": 7,
             "waypoints": [{"name": "Zion"}, {"name": "Bryce"},
                           {"name": "Arches"}, {"name": "Monument Valley"},
                           {"name": "Grand Canyon"}]},
            {"label": "Fast Loop", "totalMiles": 820, "drivingDays": 7,
             "waypoints": [{"name": "Zion"}, {"name": "Grand Canyon"}]},
        ],
    }

    def test_comparison_built_with_intensity(self, trip):
        refresh_trip_route_options(trip, self.PAYLOAD)
        opts = trip["routeOptions"]
        assert len(opts) == 2
        assert all("h/day" in o["driveIntensity"] for o in opts)
        chosen = next(o for o in opts if o["chosen"])
        assert chosen["name"] == "Grand Circle"
        # chosen row carries the trip's own routed miles + computed budget
        assert chosen["miles"] == 500 and chosen["estCost"] == 80
        other = next(o for o in opts if not o["chosen"])
        assert other["miles"] == 820
        assert other["highlights"] == "Zion, Grand Canyon"

    def test_single_candidate_skipped(self, trip):
        refresh_trip_route_options(trip, {"routes": [self.PAYLOAD["routes"][0]]})
        assert "routeOptions" not in trip
