"""places_client: the Step-1 place-name existence gate. A fabricated name
("ABC") must come back no-match, real places (however obscure) must match,
near-misses become did-you-mean, and offline degrades to the fallback shape —
never to a false "fake". All network calls are stubbed — the suite is offline.
"""

from tools import places_client as pc


def _feat(name, key, value, cc, lng, lat, state=None, country=None):
    props = {"name": name, "osm_key": key, "osm_value": value, "countrycode": cc}
    if state:
        props["state"] = state
    if country:
        props["country"] = country
    return {"type": "Feature", "properties": props,
            "geometry": {"type": "Point", "coordinates": [lng, lat]}}


def _serve(monkeypatch, features):
    monkeypatch.setattr(pc, "_get_json",
                        lambda url, timeout: {"features": features})


class TestMatch:
    def test_real_city_matches(self, monkeypatch):
        _serve(monkeypatch, [_feat("Las Vegas", "place", "city", "US",
                                   -115.1398, 36.1699,
                                   state="Nevada", country="United States")])
        v = pc.validate_place("Las Vegas")
        assert v["verdict"] == "match"
        assert v["canonical"] == "Las Vegas, Nevada, United States"
        assert (v["lat"], v["lng"]) == (36.1699, -115.1398)
        assert v["countryCode"] == "US" and v["outsideNA"] is False

    def test_state_qualifier_still_matches(self, monkeypatch):
        _serve(monkeypatch, [_feat("Springdale", "place", "town", "US",
                                   -112.9989, 37.1889, state="Utah")])
        assert pc.validate_place("Springdale, UT")["verdict"] == "match"

    def test_unqualified_state_suffix_matches(self, monkeypatch):
        # "Springdale Utah" (no comma) must not be demoted by the extra word.
        _serve(monkeypatch, [_feat("Springdale", "place", "town", "US",
                                   -112.9989, 37.1889, state="Utah")])
        assert pc.validate_place("Springdale Utah")["verdict"] == "match"

    def test_obscure_but_real_place_matches(self, monkeypatch):
        _serve(monkeypatch, [_feat("Zzyzx", "place", "locality", "US",
                                   -116.1039, 35.1436, state="California")])
        v = pc.validate_place("Zzyzx, CA")
        assert v["verdict"] == "match"

    def test_outside_na_is_flagged_not_rejected(self, monkeypatch):
        _serve(monkeypatch, [_feat("Sydney", "place", "city", "AU",
                                   151.2093, -33.8688, country="Australia")])
        v = pc.validate_place("Sydney")
        assert v["verdict"] == "match" and v["outsideNA"] is True

    def test_na_bias_prefers_north_america(self, monkeypatch):
        features = [
            _feat("Paris", "place", "city", "FR", 2.3522, 48.8566,
                  country="France"),
            _feat("Paris", "place", "city", "US", -95.5555, 33.6609,
                  state="Texas", country="United States"),
        ]
        _serve(monkeypatch, features)
        v = pc.validate_place("Paris")
        assert v["verdict"] == "match" and v["countryCode"] == "US"
        assert v["outsideNA"] is False
        assert any("France" in a["canonical"] for a in v["alternates"])
        # neutral pick keeps the geocoder's own order (France first here)
        assert pc.validate_place("Paris", na_bias=False)["outsideNA"] is True


class TestRejection:
    def test_fabricated_name_is_no_match(self, monkeypatch):
        # A same-named shop must not make "ABC" a real place.
        _serve(monkeypatch, [
            _feat("ABC Store", "shop", "convenience", "US", -113.0, 37.0),
            _feat("Springdale", "place", "town", "US", -112.9989, 37.1889),
        ])
        v = pc.validate_place("ABC")
        assert v["verdict"] == "no-match"
        assert "lat" not in v
        assert "ask the user" in v["note"]

    def test_near_miss_is_did_you_mean(self, monkeypatch):
        _serve(monkeypatch, [_feat("Zion", "place", "town", "US",
                                   -113.0263, 37.2982, state="Utah")])
        v = pc.validate_place("Zyon")            # 0.60 <= score < 0.85
        assert v["verdict"] == "did-you-mean"
        assert v["suggestions"][0]["canonical"].startswith("Zion")

    def test_empty_name_is_error(self):
        assert pc.validate_place("")["source"] == "error"
        assert pc.validate_place("   ")["source"] == "error"


class TestDegradation:
    def test_offline_is_unverified_fallback_not_fake(self, monkeypatch):
        def _boom(url, timeout):
            raise OSError("network unreachable")
        monkeypatch.setattr(pc, "_get_json", _boom)
        v = pc.validate_place("Las Vegas")
        assert v["verdict"] == "unverified"
        assert v["source"] == "fallback"
        assert v["searchQueries"] and v["query"] == "Las Vegas"

    def test_broken_geometry_is_skipped_without_crashing(self, monkeypatch):
        broken = {"type": "Feature",
                  "properties": {"name": "Ghost", "osm_key": "place",
                                 "osm_value": "town", "countrycode": "US"},
                  "geometry": None}
        _serve(monkeypatch, [broken])
        assert pc.validate_place("Ghost")["verdict"] == "no-match"
