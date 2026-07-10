"""Tests for trip editing: planner.remove_city / set_nights and their
deterministic cascade.

The model call and the weather client are always mocked — the suite runs
offline with no keys (repo hard constraint). Fixture data is the bundled
Southwest sample (7 days, overnights: Springdale x2, Bryce, Page, Grand
Canyon x2, return); the property sweep additionally walks every bundled
sample trip.
"""

import copy
import datetime
import glob
import json
import os
import sys
import types

import pytest

from scripts import planner
from scripts.planner import remove_city, revise_stay, set_nights

_ROOT = os.path.join(os.path.dirname(__file__), "..")

# A canned "stitched day" the mocked model returns. Endpoint fields are wrong
# on purpose — remove_city must enforce from/to/overnight itself.
_STITCHED = {
    "date": "01/01", "title": "STITCHED DAY", "from": "model-from", "to": "model-to",
    "driveMiles": 200, "driveTime": "3h 30m", "overnight": "model-overnight",
    "weather": {"icon": "cloudy", "high": 70, "low": 50},
    "stops": [{"name": "Somewhere en route", "type": "scenic",
               "lat": 37.0, "lng": -112.5, "note": ""}],
    "fuelCharging": [], "meal": {"name": "Diner", "perPerson": 20}, "risks": [],
}


@pytest.fixture
def trip():
    with open(os.path.join(_ROOT, "assets", "tripData.example.json"),
              encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def mock_regen(monkeypatch):
    """Replace the model call; capture what remove_city asked for."""
    calls = {}

    def fake(t, day_index, instruction, log_fn=None):
        calls["day_index"] = day_index
        calls["instruction"] = instruction
        return copy.deepcopy(_STITCHED)

    monkeypatch.setattr(planner, "_regenerate_day_with_instruction", fake)
    return calls


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """No network ever: weather returns nothing, geocoding returns nothing."""
    monkeypatch.setattr(planner, "_weather_forecast", lambda lat, lng: None)
    monkeypatch.setattr(planner, "geocode_near", lambda *a, **kw: None)
    monkeypatch.setattr(planner, "geocode", lambda *a, **kw: None)


class TestSpanValidation:
    def test_cannot_remove_first_day(self, trip, mock_regen):
        with pytest.raises(ValueError):
            remove_city(trip, 0, 0, "Las Vegas, NV")

    def test_cannot_remove_last_day(self, trip, mock_regen):
        last = len(trip["days"]) - 1
        with pytest.raises(ValueError):
            remove_city(trip, last, last, "Las Vegas, NV")

    def test_cannot_remove_span_reaching_last_day(self, trip, mock_regen):
        with pytest.raises(ValueError):
            remove_city(trip, 1, len(trip["days"]) - 1, "everything")

    def test_short_trip_rejected(self, trip, mock_regen):
        trip["days"] = trip["days"][:2]
        with pytest.raises(ValueError):
            remove_city(trip, 1, 1, "anywhere")


class TestRemoveMiddleCity:
    """Remove Bryce (day index 2): days 09/12..09/18 x7 -> x6, join day 3->2."""

    def _go(self, trip):
        return remove_city(trip, 2, 2, city_name="Bryce Canyon City, UT")

    def test_day_count_and_totals(self, trip, mock_regen):
        out = self._go(trip)
        assert out is trip
        assert len(out["days"]) == 6
        assert out["drivingDays"] == 6
        # 1180 + (stitched 200 - (85 Bryce arrival + 155 old join)) = 1140
        assert out["totalMiles"] == 1140

    def test_join_day_replaced_with_enforced_endpoints(self, trip, mock_regen):
        out = self._go(trip)
        join = out["days"][2]
        assert join["title"] == "STITCHED DAY"
        assert join["from"] == "Springdale, UT"       # previous overnight
        assert join["to"] == "Page, AZ"               # old join day's destination
        assert join["overnight"] == "Page, AZ"        # never the model's value

    def test_regen_was_asked_for_the_right_day(self, trip, mock_regen):
        self._go(trip)
        assert mock_regen["day_index"] == 3           # pre-splice index
        assert "Bryce Canyon City, UT" in mock_regen["instruction"]
        assert "DIRECTLY" in mock_regen["instruction"]

    def test_dates_resequenced_contiguously(self, trip, mock_regen):
        out = self._go(trip)
        assert [d["date"] for d in out["days"]] == [
            "09/12", "09/13", "09/14", "09/15", "09/16", "09/17"]
        assert out["dateRange"] == "2026-09-12 ~ 2026-09-17"

    def test_untouched_days_keep_content(self, trip, mock_regen):
        before = copy.deepcopy(trip["days"])
        out = self._go(trip)
        assert out["days"][0]["title"] == before[0]["title"]
        assert out["days"][1]["title"] == before[1]["title"]
        assert out["days"][3]["title"] == before[4]["title"]   # shifted, same content

    def test_lodging_and_countdown_dropped(self, trip, mock_regen):
        out = self._go(trip)
        assert all("bryce" not in (l.get("area", "") + l.get("name", "")).lower()
                   for l in out["lodging"])
        assert all("bryce" not in (b.get("item", "") + b.get("where", "")).lower()
                   for b in out["bookingCountdown"])


class TestFailureLeavesTripUntouched:
    def test_model_failure_no_mutation(self, trip, monkeypatch):
        def boom(t, day_index, instruction, log_fn=None):
            raise RuntimeError("api down")
        monkeypatch.setattr(planner, "_regenerate_day_with_instruction", boom)
        snapshot = copy.deepcopy(trip)
        with pytest.raises(RuntimeError):
            remove_city(trip, 2, 2, "Bryce Canyon City, UT")
        assert trip == snapshot


def _span_day(k):
    return {
        "date": "01/01", "title": "SPAN DAY %d" % (k + 1),
        "from": "model-from", "to": "model-to",
        "driveMiles": 999 if k == 0 else 12,   # arrival mileage now comes from the model
        "driveTime": "9h", "overnight": "model-overnight",
        "weather": {"icon": "cloudy", "high": 70, "low": 50},
        "stops": [{"name": "Span stop %d" % k, "type": "scenic",
                   "lat": 37.1 + k, "lng": -112.4, "note": ""}],
        "fuelCharging": [], "meal": {"name": "Cafe", "perPerson": 15}, "risks": [],
    }


@pytest.fixture
def mock_span_regen(monkeypatch):
    """Stand in for the model call. `calls["reply"]` lets a test choose what
    trip-level extras the model proposes: (lodging, bookingCountdown)."""
    calls = {"reply": (None, None)}

    def fake(t, day_start, day_end, out_count, instruction, city_name="", log_fn=None):
        calls.update(span=(day_start, day_end), count=out_count,
                     instruction=instruction, city_name=city_name)
        lodging, bookings = calls["reply"]
        return [_span_day(k) for k in range(out_count)], lodging, bookings

    monkeypatch.setattr(planner, "_regenerate_span_with_instruction", fake)
    return calls


class TestSetNights:
    def test_guards(self, trip, mock_span_regen):
        from scripts.planner import set_nights
        with pytest.raises(ValueError):   # unchanged count
            set_nights(trip, 2, 2, "Bryce Canyon City, UT", 1)
        with pytest.raises(ValueError):   # zero nights is remove, not resize
            set_nights(trip, 2, 2, "Bryce Canyon City, UT", 0)
        with pytest.raises(ValueError):   # above cap
            set_nights(trip, 2, 2, "Bryce Canyon City, UT", 8)
        with pytest.raises(ValueError):   # touches the final day
            set_nights(trip, 6, 6, "Las Vegas, NV", 2)

    def test_trip_length_cap(self, mock_span_regen):
        days = [{"date": "09/%02d" % (12 + i), "overnight": "X" if i < 16 else None,
                 "from": "A", "to": "B", "driveMiles": 10, "stops": []}
                for i in range(17)]
        trip = {"days": days, "dateRange": "2026-09-12 ~ 2026-09-28", "totalMiles": 200}
        from scripts.planner import set_nights
        with pytest.raises(ValueError):   # 17 - 1 + 7 = 23 > 21
            set_nights(trip, 3, 3, "X", 7)

    def test_grow_bryce_to_two_nights(self, trip, mock_span_regen):
        from scripts.planner import set_nights
        out = set_nights(trip, 2, 2, "Bryce Canyon City, UT", 2)
        assert out is trip
        assert len(out["days"]) == 8 and out["drivingDays"] == 8
        run = out["days"][2:4]
        # arrival leg preserved verbatim from the old arrival day (85 mi, not 999)
        assert run[0]["from"] == "Springdale, UT"
        assert run[0]["to"] == "Bryce Canyon City, UT"
        assert run[0]["driveMiles"] == 999   # a detour may change the mileage
        # second day is local and anchored to the same overnight
        assert run[1]["from"] == "Bryce Canyon City, UT"
        assert run[1]["overnight"] == "Bryce Canyon City, UT"
        # dates resequenced: one extra day, range extends by one
        assert [d["date"] for d in out["days"]][:5] == \
            ["09/12", "09/13", "09/14", "09/15", "09/16"]
        assert out["dateRange"] == "2026-09-12 ~ 2026-09-19"
        # totals follow the model: old run 85 → new run 999 + 12
        assert out["totalMiles"] == 1180 + (999 + 12) - 85
        # lodging night count follows the stay
        bryce = [l for l in out["lodging"] if "bryce" in l.get("area", "").lower()]
        assert bryce and bryce[0]["nights"] == 2
        # the mock was asked for exactly 2 days on the right span
        assert mock_span_regen["span"] == (2, 2) and mock_span_regen["count"] == 2

    def test_shrink_start_anchored_springdale(self, trip, mock_span_regen):
        """Runs touching Day 1 are editable here (unlike remove_city)."""
        from scripts.planner import set_nights
        out = set_nights(trip, 0, 1, "Springdale, UT", 1)
        assert len(out["days"]) == 6
        first = out["days"][0]
        assert first["from"] == "Las Vegas, NV"        # departure endpoints intact
        assert first["to"] == "Springdale, UT"
        assert first["driveMiles"] == 999             # mileage may follow new sightseeing
        assert first["overnight"] == "Springdale, UT"
        assert out["dateRange"] == "2026-09-12 ~ 2026-09-17"
        spring = [l for l in out["lodging"] if "springdale" in l.get("area", "").lower()]
        assert spring and spring[0]["nights"] == 1

    def test_count_mismatch_raises_untouched(self, trip, monkeypatch):
        from scripts.planner import set_nights
        monkeypatch.setattr(planner, "_regenerate_span_with_instruction",
                            lambda *a, **kw: (_ for _ in ()).throw(
                                ValueError("model returned 1 day(s) for the run, expected 2")))
        snapshot = copy.deepcopy(trip)
        with pytest.raises(ValueError):
            set_nights(trip, 2, 2, "Bryce Canyon City, UT", 2)
        assert trip == snapshot

    def test_model_failure_untouched(self, trip, monkeypatch):
        from scripts.planner import set_nights
        def boom(*a, **kw):
            raise RuntimeError("api down")
        monkeypatch.setattr(planner, "_regenerate_span_with_instruction", boom)
        snapshot = copy.deepcopy(trip)
        with pytest.raises(RuntimeError):
            set_nights(trip, 0, 1, "Springdale, UT", 1)
        assert trip == snapshot


def _overnight_runs(days, allow_start_anchor):
    """Maximal same-overnight runs eligible for editing (mirrors the webapp's
    grouping): overnight truthy, run ends before the final day, and — for
    remove — the run may not touch Day 1."""
    runs, n, i = [], len(days), 0
    while i < n:
        o = days[i].get("overnight") or None
        j = i
        while j + 1 < n and (days[j + 1].get("overnight") or None) == o:
            j += 1
        if o and j <= n - 2 and (allow_start_anchor or i >= 1):
            runs.append((i, j, o))
        i = j + 1
    return runs


def _assert_dates_contiguous(trip):
    days = trip["days"]
    y0, m0, d0 = trip["dateRange"].split(" ~ ")[0].split("-")
    cur = datetime.date(int(y0), int(m0), int(d0))
    iso = []
    for d in days:
        assert d["date"] == cur.strftime("%m/%d")
        iso.append(cur.strftime("%Y-%m-%d"))
        cur += datetime.timedelta(days=1)
    assert trip["dateRange"] == "%s ~ %s" % (iso[0], iso[-1])


def _stable(day):
    """A day stripped of the fields the cascade may legitimately touch on
    UNCHANGED days: the date (resequencing) and stop coordinates
    (despread_stops re-runs trip-wide and nudges colliding pins)."""
    d = copy.deepcopy(day)
    d.pop("date", None)
    for s in d.get("stops") or []:
        s.pop("lat", None)
        s.pop("lng", None)
    return d


class TestPropertySweep:
    """Every bundled sample × every eligible run × several night targets —
    the invariants that must hold no matter what the (mocked) model returns."""

    def _samples(self):
        for f in sorted(glob.glob(os.path.join(_ROOT, "assets", "tripData.*.json"))):
            with open(f, encoding="utf-8") as fh:
                yield os.path.basename(f), json.load(fh)

    def test_set_nights_sweep(self, mock_span_regen):
        scenarios = 0
        for name, base in self._samples():
            n = len(base["days"])
            for (i, j, city) in _overnight_runs(base["days"], allow_start_anchor=True):
                cur = j - i + 1
                targets = sorted({1, cur - 1, cur + 1, cur + 2, 7})
                for target in targets:
                    if not (1 <= target <= 7) or target == cur or n - cur + target > 21:
                        continue
                    trip = copy.deepcopy(base)
                    orig = copy.deepcopy(base)
                    out = set_nights(trip, i, j, city, target)
                    scenarios += 1
                    ctx = "%s run[%d..%d] %d→%d" % (name, i, j, cur, target)
                    # shape
                    assert len(out["days"]) == n - cur + target, ctx
                    assert out["drivingDays"] == len(out["days"]), ctx
                    _assert_dates_contiguous(out)
                    # prefix untouched, suffix content-identical (dates may shift)
                    assert [_stable(d) for d in out["days"][:i]] == [_stable(d) for d in orig["days"][:i]], ctx
                    assert ([_stable(d) for d in out["days"][i + target:]]
                            == [_stable(d) for d in orig["days"][j + 1:]]), ctx
                    # anchors enforced on the rewritten run
                    arr_old, arr_new = orig["days"][i], out["days"][i]
                    for key in ("from", "to"):          # endpoints enforced
                        assert arr_new.get(key) == arr_old.get(key), ctx
                    for d in out["days"][i:i + target]:
                        assert d["overnight"] == arr_old.get("overnight"), ctx
                    for d in out["days"][i + 1:i + target]:
                        assert d["from"] == arr_old.get("overnight"), ctx
                    # totals arithmetic
                    if isinstance(orig.get("totalMiles"), (int, float)):
                        delta = (sum(planner._mi(d) for d in out["days"][i:i + target])
                                 - sum(planner._mi(d) for d in orig["days"][i:j + 1]))
                        assert out["totalMiles"] == max(0, int(orig["totalMiles"]) + delta), ctx
                    # lodging night counts follow; unrelated entries untouched
                    needle = city.split(",")[0].strip().lower()
                    for l_new, l_old in zip(out.get("lodging", []), orig.get("lodging", [])):
                        text = ("%s %s" % (l_old.get("name", ""), l_old.get("area", ""))).lower()
                        if needle and needle in text:
                            assert l_new["nights"] == target, ctx
                        else:
                            assert l_new == l_old, ctx
                    # countdown must survive a stay-length change
                    assert out.get("bookingCountdown") == orig.get("bookingCountdown"), ctx
        assert scenarios >= 20   # the sweep actually swept

    def test_remove_city_sweep(self, mock_regen):
        scenarios = 0
        for name, base in self._samples():
            n = len(base["days"])
            for (i, j, city) in _overnight_runs(base["days"], allow_start_anchor=False):
                if n - (j - i + 1) < 2:
                    continue
                trip = copy.deepcopy(base)
                orig = copy.deepcopy(base)
                out = remove_city(trip, i, j, city_name=city)
                scenarios += 1
                ctx = "%s remove run[%d..%d]" % (name, i, j)
                assert len(out["days"]) == n - (j - i + 1), ctx
                assert out["drivingDays"] == len(out["days"]), ctx
                _assert_dates_contiguous(out)
                assert [_stable(d) for d in out["days"][:i]] == [_stable(d) for d in orig["days"][:i]], ctx
                # stitched day endpoints enforced
                stitched = out["days"][i]
                assert stitched["from"] == (orig["days"][i - 1].get("overnight")
                                            or orig["days"][i - 1].get("to")), ctx
                assert stitched["to"] == orig["days"][j + 1].get("to"), ctx
                assert stitched["overnight"] == orig["days"][j + 1].get("overnight"), ctx
                # suffix after the stitched day content-identical
                assert ([_stable(d) for d in out["days"][i + 1:]]
                        == [_stable(d) for d in orig["days"][j + 2:]]), ctx
                # the removed city no longer referenced in lodging
                needle = city.split(",")[0].strip().lower()
                for l in out.get("lodging", []):
                    assert needle not in ("%s %s" % (l.get("name", ""),
                                                     l.get("area", ""))).lower(), ctx
        assert scenarios >= 4


class TestSpanRegenOffline:
    """Exercise _regenerate_span_with_instruction itself — prompt assembly,
    exact-count validation and the retry path — via a scripted fake anthropic."""

    def _install_fake(self, monkeypatch, script):
        calls = []

        class _Client:
            def __init__(self, *a, **kw):
                self.messages = self

            def create(self, **kw):
                calls.append(kw)
                blk = types.SimpleNamespace(type="text", text=script.pop(0))
                return types.SimpleNamespace(content=[blk], usage={"in": 1},
                                             stop_reason="end_turn")

        mod = types.ModuleType("anthropic")
        mod.Anthropic = _Client
        monkeypatch.setitem(sys.modules, "anthropic", mod)
        return calls

    def _payload(self, count):
        return json.dumps({"days": [_span_day(k) for k in range(count)]})

    def test_happy_path_prompt_and_result(self, trip, monkeypatch):
        calls = self._install_fake(monkeypatch, [self._payload(2)])
        got, lodging, bookings = planner._regenerate_span_with_instruction(
            trip, 2, 2, 2, "TEST-INSTRUCTION-MARKER")
        assert len(got) == 2 and got[0]["title"] == "SPAN DAY 1"
        assert lodging is None and bookings is None
        assert len(calls) == 1
        prompt = calls[0]["messages"][0]["content"]
        assert "TEST-INSTRUCTION-MARKER" in prompt
        assert "EXACTLY 2 day(s)" in prompt
        assert '"days"' in prompt
        assert "Bryce Canyon City" in prompt          # span JSON embedded
        assert calls[0]["max_tokens"] == 2500 + 2600 * 2

    def test_retry_on_garbage_then_success(self, trip, monkeypatch, capsys):
        calls = self._install_fake(
            monkeypatch, ["utter { garbage !!!", self._payload(1)])
        got, _, _ = planner._regenerate_span_with_instruction(trip, 2, 2, 1, "X")
        assert len(got) == 1
        assert len(calls) == 2
        assert calls[1]["messages"][0]["content"].endswith(
            planner._STRICT_JSON_NUDGE)
        assert "unparseable model JSON" in capsys.readouterr().err

    def test_count_mismatch_raises_without_retry(self, trip, monkeypatch):
        calls = self._install_fake(monkeypatch, [self._payload(1)])
        with pytest.raises(ValueError, match="expected 2"):
            planner._regenerate_span_with_instruction(trip, 2, 2, 2, "X")
        assert len(calls) == 1     # count mismatch is not a parse failure

    def test_log_fn_receives_usage_per_call(self, trip, monkeypatch):
        self._install_fake(monkeypatch, ["garbage", self._payload(1)])
        seen = []
        planner._regenerate_span_with_instruction(
            trip, 2, 2, 1, "X", log_fn=seen.append)
        assert len(seen) == 2      # both the failed and the retry call are billed


class TestDegenerateTrips:
    def test_missing_date_metadata_degrades_gracefully(self, mock_span_regen):
        trip = {"days": [
            {"date": "bogus", "overnight": "A", "from": "S", "to": "A",
             "driveMiles": 10, "stops": []},
            {"date": "bogus", "overnight": "A", "from": "A", "to": "A",
             "driveMiles": 0, "stops": []},
            {"date": "bogus", "overnight": None, "from": "A", "to": "S",
             "driveMiles": 10, "stops": []},
        ], "totalMiles": 20, "lodging": [], "bookingCountdown": []}
        out = set_nights(trip, 0, 1, "A", 1)     # no dateRange/generationDate
        assert len(out["days"]) == 2             # edit still lands
        assert "dateRange" not in out            # date cascade skipped, no crash

    def test_days_without_stops_survive_weather_refresh(self, mock_span_regen, monkeypatch):
        monkeypatch.setattr(planner, "_weather_forecast",
                            lambda lat, lng: {"source": "nws", "days": []})
        trip = {"days": [
            {"date": "09/12", "overnight": "A", "from": "S", "to": "A",
             "driveMiles": 10},                   # no stops key at all
            {"date": "09/13", "overnight": "A", "from": "A", "to": "A",
             "driveMiles": 0},
            {"date": "09/14", "overnight": None, "from": "A", "to": "S",
             "driveMiles": 10},
        ], "dateRange": "2026-09-12 ~ 2026-09-14", "totalMiles": 20}
        out = set_nights(trip, 0, 1, "A", 1)
        assert len(out["days"]) == 2


class TestReviseStay:
    def test_instruction_only_keeps_length_and_lodging(self, trip, mock_span_regen):
        before_lodging = copy.deepcopy(trip["lodging"])
        out = revise_stay(trip, 2, 2, "Bryce Canyon City, UT",
                          "不想住汽车旅馆，换家带早餐的")
        assert len(out["days"]) == 7                      # 长度不变
        assert out["drivingDays"] == 7
        assert mock_span_regen["count"] == 1              # 同长度重排
        assert "不想住汽车旅馆" in mock_span_regen["instruction"]
        assert "top priority" in mock_span_regen["instruction"]
        assert out["lodging"] == before_lodging           # 模型没提议换酒店 → 不动
        assert [d["date"] for d in out["days"]][:3] == ["09/12", "09/13", "09/14"]
        # 到达日端点仍被强制,里程交给模型
        assert out["days"][2]["from"] == "Springdale, UT"
        assert out["days"][2]["to"] == "Bryce Canyon City, UT"

    def test_instruction_with_resize_in_one_call(self, trip, mock_span_regen):
        out = revise_stay(trip, 2, 2, "Bryce Canyon City, UT",
                          "want a hoodoo sunrise hike", nights=2)
        assert len(out["days"]) == 8
        assert mock_span_regen["count"] == 2
        ins = mock_span_regen["instruction"]
        assert "from 1 to 2 night(s)" in ins
        assert "hoodoo sunrise hike" in ins
        bryce = [l for l in out["lodging"] if "bryce" in l.get("area", "").lower()]
        assert bryce and bryce[0]["nights"] == 2          # 改了晚数才同步住宿

    def test_nights_equal_current_is_allowed(self, trip, mock_span_regen):
        out = revise_stay(trip, 2, 2, "Bryce Canyon City, UT", "swap hotel", nights=1)
        assert len(out["days"]) == 7                      # 与 set_nights 不同:等长合法

    def test_empty_instruction_rejected(self, trip, mock_span_regen):
        with pytest.raises(ValueError):
            revise_stay(trip, 2, 2, "Bryce Canyon City, UT", "   ")

    def test_instruction_capped_at_500_chars(self, trip, mock_span_regen):
        revise_stay(trip, 2, 2, "Bryce Canyon City, UT", "A" * 505)
        ins = mock_span_regen["instruction"]
        assert "A" * 500 in ins and "A" * 501 not in ins

    def test_bad_nights_and_span_guards(self, trip, mock_span_regen):
        with pytest.raises(ValueError):
            revise_stay(trip, 2, 2, "Bryce", "x", nights=8)
        with pytest.raises(ValueError):
            revise_stay(trip, 6, 6, "Las Vegas, NV", "x")   # 碰到最后一天
        with pytest.raises(ValueError):
            revise_stay(trip, 2, 2, "Bryce", "x", nights="lots")

    def test_model_failure_untouched(self, trip, monkeypatch):
        def boom(*a, **kw):
            raise RuntimeError("api down")
        monkeypatch.setattr(planner, "_regenerate_span_with_instruction", boom)
        snapshot = copy.deepcopy(trip)
        with pytest.raises(RuntimeError):
            revise_stay(trip, 2, 2, "Bryce Canyon City, UT", "swap hotel")
        assert trip == snapshot


class TestStayContentUpdates:
    """The model may also replace the stay's hotel and its bookings."""

    def test_hotel_swapped_nights_and_booked_stay_ours(self, trip, mock_span_regen):
        mock_span_regen["reply"] = (
            {"name": "Bryce Budget Inn", "area": "Bryce Canyon City, UT",
             "pricePerNight": 95, "rating": "4.1", "nights": 99, "booked": True},
            None)
        before_len = len(trip["lodging"])
        out = revise_stay(trip, 2, 2, "Bryce Canyon City, UT",
                          "\u4e0d\u60f3\u4f4f\u8fd9\u5bb6\uff0c\u6362\u5bb6\u4fbf\u5b9c\u7684")
        lg = next(l for l in out["lodging"] if "bryce" in l["area"].lower())
        assert lg["name"] == "Bryce Budget Inn"
        assert lg["pricePerNight"] == 95 and lg["rating"] == "4.1"
        assert lg["nights"] == 1          # nights belong to the code, not the model
        assert lg["booked"] is False      # different property -> reset
        assert len(out["lodging"]) == before_len   # replaced, not appended

    def test_hotel_swap_with_resize_syncs_nights(self, trip, mock_span_regen):
        mock_span_regen["reply"] = ({"name": "Hoodoo Lodge", "pricePerNight": 150}, None)
        out = revise_stay(trip, 2, 2, "Bryce Canyon City, UT", "swap hotel", nights=3)
        lg = next(l for l in out["lodging"] if "bryce" in l["area"].lower())
        assert lg["name"] == "Hoodoo Lodge" and lg["nights"] == 3
        assert lg["area"] == "Bryce Canyon City, UT"   # model omitted area -> keep old

    def test_partial_hotel_keeps_old_price_and_rating(self, trip, mock_span_regen):
        before = next(l for l in trip["lodging"] if "bryce" in l["area"].lower())
        old_price, old_rating = before["pricePerNight"], before["rating"]
        mock_span_regen["reply"] = ({"name": "Only A Name"}, None)
        out = revise_stay(trip, 2, 2, "Bryce Canyon City, UT", "rename")
        lg = next(l for l in out["lodging"] if "bryce" in l["area"].lower())
        assert lg["pricePerNight"] == old_price and lg["rating"] == old_rating

    def test_bookings_replaced_only_for_this_stay(self, trip, mock_span_regen):
        stale = planner._stay_bookings(trip, "Page, AZ", trip["days"][3:4])
        assert stale                                   # matched via the Antelope Canyon stop
        others = [b for b in trip["bookingCountdown"] if b not in stale]
        mock_span_regen["reply"] = (None, [
            {"item": "Horseshoe Bend parking", "bookBy": "2026-09-01",
             "where": "City of Page", "priority": "low", "note": "$10 lot"}])
        out = revise_stay(trip, 3, 3, "Page, AZ", "no guided tour")
        items = [b["item"] for b in out["bookingCountdown"]]
        assert "Horseshoe Bend parking" in items
        for b in others:
            assert b in out["bookingCountdown"]

    def test_empty_booking_list_drops_this_stay_bookings(self, trip, mock_span_regen):
        stale = planner._stay_bookings(trip, "Page, AZ", trip["days"][3:4])
        assert stale
        mock_span_regen["reply"] = (None, [])
        out = revise_stay(trip, 3, 3, "Page, AZ", "book nothing")
        for b in stale:
            assert b not in out["bookingCountdown"]

    def test_no_extras_means_no_changes(self, trip, mock_span_regen):
        before_l = copy.deepcopy(trip["lodging"])
        before_b = copy.deepcopy(trip["bookingCountdown"])
        out = revise_stay(trip, 2, 2, "Bryce Canyon City, UT", "just tweak the hikes")
        assert out["lodging"] == before_l and out["bookingCountdown"] == before_b

    def test_bad_booking_entries_normalized(self, trip, mock_span_regen):
        mock_span_regen["reply"] = (None, [
            {"item": "X", "priority": "URGENT!!"}, {"item": "   "}])
        out = revise_stay(trip, 3, 3, "Page, AZ", "fix bookings")
        added = [b for b in out["bookingCountdown"] if b["item"] == "X"]
        assert added and added[0]["priority"] == "medium"
        assert all(b["item"].strip() for b in out["bookingCountdown"])

    def test_city_name_passed_to_regen(self, trip, mock_span_regen):
        revise_stay(trip, 2, 2, "Bryce Canyon City, UT", "x")
        assert mock_span_regen["city_name"] == "Bryce Canyon City, UT"

    def test_missing_drive_fields_fall_back_to_old(self, trip, monkeypatch):
        def fake(t, ds, de, n, ins, city_name="", log_fn=None):
            d = _span_day(0)
            d.pop("driveMiles")
            d["driveTime"] = ""
            return [d], None, None
        monkeypatch.setattr(planner, "_regenerate_span_with_instruction", fake)
        out = revise_stay(trip, 2, 2, "Bryce Canyon City, UT", "x")
        assert out["days"][2]["driveMiles"] == 85       # old value as fallback
        assert out["days"][2]["driveTime"] == "1h45m"


class TestNullAndTypeHardening:
    """The model may emit explicit nulls or stringified numbers — neither may
    leak into the trip data (PR review findings)."""

    def test_null_booking_fields_do_not_become_the_word_none(self, trip, mock_span_regen):
        mock_span_regen["reply"] = (None, [
            {"item": None, "bookBy": None, "where": None},          # wholly null -> skipped
            {"item": "Real thing", "bookBy": None, "where": None},  # partial -> empty strings
        ])
        out = revise_stay(trip, 3, 3, "Page, AZ", "fix bookings")
        added = [b for b in out["bookingCountdown"] if b["item"] == "Real thing"]
        assert len(added) == 1
        assert added[0]["bookBy"] == "" and added[0]["where"] == ""
        for b in out["bookingCountdown"]:
            assert "None" not in (b["item"] + b.get("bookBy", "") + b.get("where", ""))

    def test_null_hotel_fields_do_not_become_the_word_none(self, trip, mock_span_regen):
        mock_span_regen["reply"] = ({"name": "Quiet Inn", "area": None,
                                     "rating": None, "pricePerNight": None}, None)
        out = revise_stay(trip, 2, 2, "Bryce Canyon City, UT", "swap hotel")
        lg = next(l for l in out["lodging"] if "bryce" in l["area"].lower())
        assert lg["name"] == "Quiet Inn"
        assert "None" not in lg["area"] and lg.get("rating") != "None"
        assert lg["pricePerNight"] == 190          # null -> keep the old price

    def test_null_names_in_trip_data_do_not_pollute_matching(self):
        trip = {"lodging": [{"name": None, "area": None},
                            {"name": "Bryce Inn", "area": "Bryce Canyon City, UT"}],
                "bookingCountdown": [{"item": None, "where": None}]}
        assert planner._stay_lodging(trip, "none") is None      # never matches the null row
        assert planner._stay_lodging(trip, "Bryce Canyon City, UT")["name"] == "Bryce Inn"
        assert planner._stay_bookings(trip, "none") == []

    def test_stringified_mileage_is_parsed_not_clobbered(self, trip, monkeypatch):
        def fake(t, ds, de, n, ins, city_name="", log_fn=None):
            d = _span_day(0)
            d["driveMiles"] = "150 mi"          # model wrote a string
            return [d], None, None
        monkeypatch.setattr(planner, "_regenerate_span_with_instruction", fake)
        out = revise_stay(trip, 2, 2, "Bryce Canyon City, UT", "detour")
        assert out["days"][2]["driveMiles"] == 150      # parsed, not reverted to 85

    def test_boolean_mileage_is_rejected(self, trip, monkeypatch):
        def fake(t, ds, de, n, ins, city_name="", log_fn=None):
            d = _span_day(0)
            d["driveMiles"] = True              # isinstance(True, int) is True!
            return [d], None, None
        monkeypatch.setattr(planner, "_regenerate_span_with_instruction", fake)
        out = revise_stay(trip, 2, 2, "Bryce Canyon City, UT", "x")
        assert out["days"][2]["driveMiles"] == 85       # falls back, never 1 mile

    def test_blank_drive_time_falls_back(self, trip, monkeypatch):
        def fake(t, ds, de, n, ins, city_name="", log_fn=None):
            d = _span_day(0)
            d["driveTime"] = "   "
            return [d], None, None
        monkeypatch.setattr(planner, "_regenerate_span_with_instruction", fake)
        out = revise_stay(trip, 2, 2, "Bryce Canyon City, UT", "x")
        assert out["days"][2]["driveTime"] == "1h45m"

    def test_coerce_miles_unit(self):
        c = planner._coerce_miles
        assert c(150) == 150 and c(150.7) == 150 and c("150") == 150
        assert c("~1,50 mi") == 1                 # first number wins
        assert c(True) is None and c(False) is None
        assert c(None) is None and c("abc") is None

class TestBudgetFollowsEdits:
    """The budget must not keep quoting the old day/night/mile counts."""

    def test_set_nights_updates_budget(self, trip, mock_span_regen):
        before_total = trip["budget"]["total"]
        set_nights(trip, 2, 2, "Bryce Canyon City, UT", 3)   # 1 -> 3 nights (+2 days)
        b = trip["budget"]
        food = next(i for i in b["items"] if "food" in i["label"].lower())
        lodging = next(i for i in b["items"] if "lodging" in i["label"].lower())
        assert "9 days" in food["label"]                     # 7 -> 9 days
        assert lodging["amount"] == sum(
            l["pricePerNight"] * l["nights"] for l in trip["lodging"])
        assert b["total"] == sum(i["amount"] for i in b["items"]) != before_total
        assert b["perPerson"] == round(b["total"] / 2)

    def test_remove_city_updates_budget(self, trip, mock_regen):
        remove_city(trip, 2, 2, city_name="Bryce Canyon City, UT")
        b = trip["budget"]
        food = next(i for i in b["items"] if "food" in i["label"].lower())
        assert "6 days" in food["label"]                     # 7 -> 6 days
        assert b["total"] == sum(i["amount"] for i in b["items"])

    def test_hotel_swap_updates_lodging_cost(self, trip, mock_span_regen):
        mock_span_regen["reply"] = ({"name": "Cheap Inn", "pricePerNight": 60}, None)
        revise_stay(trip, 2, 2, "Bryce Canyon City, UT", "cheaper hotel please")
        lodging = next(i for i in trip["budget"]["items"]
                       if "lodging" in i["label"].lower())
        assert lodging["amount"] == sum(
            l["pricePerNight"] * l["nights"] for l in trip["lodging"])


class TestWeatherRefresh:
    def _forecast_for(self, dates, icon="rain", high=50, low=30):
        return {"source": "nws", "units": "F",
                "days": [{"date": d, "icon": icon, "high": high, "low": low}
                         for d in dates]}

    def test_shifted_days_get_real_forecast(self, trip, mock_regen, monkeypatch):
        window = ["2026-09-%02d" % d for d in range(12, 19)]
        monkeypatch.setattr(planner, "_weather_forecast",
                            lambda lat, lng: self._forecast_for(window))
        out = remove_city(trip, 2, 2, "Bryce Canyon City, UT")
        # days before the edit keep the model's estimate
        assert out["days"][0]["weather"] == {"icon": "sunny", "high": 88, "low": 60}
        assert out["days"][1]["weather"] == {"icon": "sunny", "high": 90, "low": 62}
        # the stitched day and every shifted day get the real forecast
        for d in out["days"][2:]:
            if d.get("stops"):
                assert d["weather"]["icon"] == "rain"
                assert d["weather"]["high"] == 50

    def test_dates_beyond_window_keep_estimate(self, trip, mock_regen, monkeypatch):
        monkeypatch.setattr(planner, "_weather_forecast",
                            lambda lat, lng: self._forecast_for(["2026-09-14"]))
        out = remove_city(trip, 2, 2, "Bryce Canyon City, UT")
        assert out["days"][2]["weather"]["icon"] == "rain"        # 09/14 covered
        assert out["days"][3]["weather"]["icon"] != "rain"        # 09/15 not covered

    def test_fallback_source_never_overwrites(self, trip, mock_regen, monkeypatch):
        monkeypatch.setattr(planner, "_weather_forecast",
                            lambda lat, lng: {"source": "fallback"})
        before = copy.deepcopy(trip["days"][4]["weather"])
        out = remove_city(trip, 2, 2, "Bryce Canyon City, UT")
        assert out["days"][3]["weather"] == before                # shifted, unchanged
