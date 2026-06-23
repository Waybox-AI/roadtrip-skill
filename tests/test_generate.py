import pytest
from assets.generate import validate, build_html

MINIMAL_VALID = {
    "title": "My Trip",
    "days": [
        {
            "date": "2026-07-01",
            "title": "Day 1",
            "stops": [{"lat": 36.1, "lng": -112.1}],
        }
    ],
    "disclaimer": "Check all info before travelling.",
}

TEMPLATE = "<html><script>var x = __TRIP_DATA__;</script></html>"


class TestValidate:
    def test_valid_trip_no_critical_warnings(self):
        warnings = validate(MINIMAL_VALID)
        assert not any("missing top-level" in w for w in warnings)

    def test_missing_title(self):
        trip = {k: v for k, v in MINIMAL_VALID.items() if k != "title"}
        assert any("title" in w for w in validate(trip))

    def test_missing_days_key(self):
        trip = {k: v for k, v in MINIMAL_VALID.items() if k != "days"}
        assert any("days" in w for w in validate(trip))

    def test_empty_days_list(self):
        trip = {**MINIMAL_VALID, "days": []}
        assert any("days" in w for w in validate(trip))

    def test_day_missing_date(self):
        trip = {**MINIMAL_VALID, "days": [{"title": "Day 1"}]}
        assert any("date" in w for w in validate(trip))

    def test_day_missing_title(self):
        trip = {**MINIMAL_VALID, "days": [{"date": "2026-07-01"}]}
        assert any("title" in w for w in validate(trip))

    def test_no_coords_warning(self):
        trip = {
            **MINIMAL_VALID,
            "days": [{"date": "2026-07-01", "title": "D1",
                      "stops": [{"name": "somewhere"}]}],
        }
        assert any("lat/lng" in w for w in validate(trip))

    def test_budget_mismatch_warning(self):
        trip = {
            **MINIMAL_VALID,
            "budget": {"total": 1000, "items": [{"amount": 400}, {"amount": 400}]},
        }
        assert any("budget" in w for w in validate(trip))

    def test_budget_balanced_no_warning(self):
        trip = {
            **MINIMAL_VALID,
            "budget": {"total": 800, "items": [{"amount": 400}, {"amount": 400}]},
        }
        assert not any("budget" in w for w in validate(trip))

    def test_no_disclaimer_warning(self):
        trip = {k: v for k, v in MINIMAL_VALID.items() if k != "disclaimer"}
        assert any("disclaimer" in w for w in validate(trip))


class TestBuildHtml:
    def test_token_replaced(self):
        trip = {"title": "T", "days": []}
        html = build_html(trip, TEMPLATE)
        assert "__TRIP_DATA__" not in html
        assert '"title"' in html

    def test_script_closing_tag_escaped(self):
        trip = {"note": "</script>", "days": []}
        html = build_html(trip, TEMPLATE)
        assert "<\\/script>" in html
        # The raw </script> must not appear inside the payload section
        payload_section = html.split("<script>")[1]
        assert "</script>" not in payload_section.split("</script>")[0]

    def test_html_comment_escaped(self):
        trip = {"note": "<!-- inject -->", "days": []}
        html = build_html(trip, TEMPLATE)
        assert "<\\!--" in html

    def test_missing_token_raises_value_error(self):
        with pytest.raises(ValueError, match="missing"):
            build_html({"days": []}, "<html>no token here</html>")


