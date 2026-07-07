from tools.customs_client import personal_exemption


class TestUSExemption:
    def test_standard_800_at_48h(self):
        # 48h is the threshold itself → standard tier applies
        r = personal_exemption("US", 48)
        assert r["source"] == "rules"
        assert (r["amount"], r["currency"], r["tier"]) == (800, "USD", "standard")

    def test_reduced_200_under_48h(self):
        r = personal_exemption("US", 47.9)
        assert (r["amount"], r["tier"]) == (200, "reduced")

    def test_reduced_200_when_800_used_within_30_days(self):
        r = personal_exemption("US", 72, used_within_30_days=True)
        assert (r["amount"], r["tier"]) == (200, "reduced")
        assert "30 days" in r["note"]

    def test_standard_mentions_30_day_limit(self):
        r = personal_exemption("US", 72)
        assert "30 days" in r["note"]


class TestCAExemption:
    def test_none_under_24h(self):
        r = personal_exemption("CA", 23.9)
        assert (r["amount"], r["tier"]) == (0, "none")

    def test_200_at_24h_threshold(self):
        r = personal_exemption("CA", 24)
        assert (r["amount"], r["currency"], r["tier"]) == (200, "CAD", "reduced")

    def test_800_at_48h_threshold(self):
        r = personal_exemption("CA", 48)
        assert (r["amount"], r["tier"]) == (800, "standard")

    def test_reduced_tier_excludes_alcohol_tobacco(self):
        # CBSA quirk: the 24-48h tier covers no alcohol/tobacco and
        # exceeding it duties the FULL value, not just the excess.
        r = personal_exemption("CA", 30)
        assert any("NOT" in c for c in r["conditions"])
        assert any("FULL" in c for c in r["conditions"])


class TestMXAndErrors:
    def test_mx_land_300_usd(self):
        r = personal_exemption("MX", 50)
        assert (r["amount"], r["currency"], r["tier"]) == (300, "USD", "standard")

    def test_unsupported_residence_is_error(self):
        r = personal_exemption("XX", 50)
        assert r["source"] == "error"

    def test_residence_is_case_insensitive(self):
        assert personal_exemption("us", 72)["amount"] == 800


class TestResultShape:
    CASES = (("US", 72), ("US", 12), ("CA", 12), ("CA", 30), ("CA", 60), ("MX", 50))

    def test_bilingual_fields_present_everywhere(self):
        for res, h in self.CASES:
            r = personal_exemption(res, h)
            assert r["note"] and r["noteZh"]
            assert r["disclaimer"] and r["disclaimerZh"]
            assert len(r["conditions"]) == len(r["conditionsZh"])

    def test_verify_source_and_hours_echoed(self):
        for res, h in self.CASES:
            r = personal_exemption(res, h)
            assert r["verify"]
            assert r["hoursAbroad"] == h
