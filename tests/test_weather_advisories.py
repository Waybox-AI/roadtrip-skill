"""Weather advisory engine (PR②): planner.weather_advisories — deterministic,
no model call. Verifies condition detection, activity-aware severity, the
forecast-vs-climatology voice, the provenance gate, and i18n."""

from scripts.planner import weather_advisories


def _trip(weather, stops=None, lang="en"):
    return {"lang": lang, "days": [
        {"date": "09/12", "weather": weather, "stops": stops or []}]}


def _one(weather, **kw):
    return weather_advisories(_trip(weather, **kw))[0]


class TestProvenanceGate:
    def test_untagged_estimate_never_warns(self):
        # storm, but it's the model's own guess (no source) -> silence
        assert _one({"icon": "storm", "high": 70}) is None

    def test_forecast_storm_warns(self):
        a = _one({"icon": "storm", "high": 70, "source": "forecast"})
        assert a and a["condition"] == "storm" and a["source"] == "forecast"

    def test_climatology_storm_warns(self):
        a = _one({"icon": "storm", "high": 70, "source": "climatology"})
        assert a and a["source"] == "climatology"


class TestConditionDetection:
    def test_heat_from_high(self):
        a = _one({"icon": "sunny", "high": 104, "source": "forecast"})
        assert a["condition"] == "heat"

    def test_cold_from_low(self):
        a = _one({"icon": "partly-cloudy", "low": 18, "source": "forecast"})
        assert a["condition"] == "cold"

    def test_wind_from_windmph(self):
        a = _one({"icon": "cloudy", "high": 60, "windMph": 40, "source": "forecast"})
        assert a["condition"] == "wind"

    def test_rain_from_precip_probability(self):
        a = _one({"icon": "cloudy", "high": 60, "precipProb": 75, "source": "forecast"})
        assert a["condition"] == "rain"

    def test_mild_day_is_none(self):
        assert _one({"icon": "sunny", "high": 78, "low": 55, "source": "forecast"}) is None

    def test_storm_beats_heat_priority(self):
        a = _one({"icon": "storm", "high": 104, "source": "forecast"})
        assert a["condition"] == "storm"


class TestActivityAwareSeverity:
    _W = {"icon": "storm", "high": 70, "source": "forecast"}

    def test_outdoor_day_is_high_severity(self):
        a = _one(self._W, stops=[{"type": "hike"}])
        assert a["severity"] == "high"
        assert "moving the hike" in a["message"] or "morning" in a["message"]

    def test_indoor_or_drive_day_is_info(self):
        a = _one(self._W, stops=[{"type": "city"}])
        assert a["severity"] == "info"
        assert "the drive" in a["message"]

    def test_park_counts_as_outdoor(self):
        a = _one(self._W, stops=[{"type": "park"}])
        assert a["severity"] == "high"


class TestVoiceBySource:
    def test_forecast_speaks_future_and_asks_to_verify(self):
        a = _one({"icon": "rain", "high": 60, "source": "forecast"})
        assert "likely" in a["message"].lower()
        assert "Re-check" in a["message"]           # verify nudge only for forecasts

    def test_climatology_speaks_in_tendencies_no_verify(self):
        a = _one({"icon": "rain", "high": 60, "source": "climatology"})
        assert "typically" in a["message"] or "often" in a["message"]
        assert "Re-check" not in a["message"]       # no "check the day before" for a season avg


class TestI18nAndShape:
    def test_zh_messages(self):
        a = _one({"icon": "storm", "high": 70, "source": "forecast"},
                 stops=[{"type": "hike"}], lang="zh")
        assert "雷暴" in a["message"] and "徒步" in a["message"]

    def test_list_aligns_with_days(self):
        trip = {"lang": "en", "days": [
            {"weather": {"icon": "sunny", "high": 78, "source": "forecast"}, "stops": []},
            {"weather": {"icon": "storm", "high": 70, "source": "forecast"},
             "stops": [{"type": "hike"}]},
            {"weather": {"icon": "snow", "low": 20}, "stops": []},   # untagged -> None
        ]}
        out = weather_advisories(trip)
        assert len(out) == 3
        assert out[0] is None                        # mild
        assert out[1]["condition"] == "storm"
        assert out[2] is None                        # untagged estimate

    def test_no_weather_key_is_none(self):
        assert weather_advisories({"days": [{"stops": []}]})[0] is None

    def test_empty_trip(self):
        assert weather_advisories({}) == []
