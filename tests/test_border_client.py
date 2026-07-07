from tools.border_client import crossing, trip_section


class TestCrossingIntoCanada:
    def test_basic_shape(self):
        r = crossing("US", "CA")
        assert r["source"] == "rules"
        assert (r["from"], r["to"]) == ("US", "CA")
        assert r["docs"] and r["vehicleDocs"] and r["customsNotes"]
        assert r["insuranceNote"] and r["waitTimes"] and r["estWaitNote"]
        assert r["disclaimer"]

    def test_units_switch_to_metric_cad(self):
        u = crossing("US", "CA")["unitsAfter"]
        assert (u["distance"], u["temp"], u["currency"], u["fuel"]) == \
            ("km", "C", "CAD", "litre")

    def test_us_insurance_generally_valid_in_canada(self):
        assert "generally valid" in crossing("US", "CA")["insuranceNote"]

    def test_rental_adds_authorization_letter_requirement(self):
        base   = crossing("US", "CA")["vehicleDocs"]
        rental = crossing("US", "CA", rental=True)["vehicleDocs"]
        assert len(rental) == len(base) + 1
        assert any("authorization letter" in d for d in rental)

    def test_cannabis_warned_in_both_directions(self):
        assert any("Cannabis" in n for n in crossing("US", "CA")["customsNotes"])


class TestCrossingIntoMexico:
    def test_insurance_is_the_critical_asymmetry(self):
        # US insurance works in Canada but NEVER in Mexico — the key rule
        # SKILL.md calls out; a regression here is a real-money mistake.
        assert "NOT valid" in crossing("US", "MX")["insuranceNote"]

    def test_fmm_and_tip_requirements(self):
        r = crossing("US", "MX")
        assert any("FMM" in d for d in r["docs"])
        assert any("TIP" in d for d in r["vehicleDocs"])

    def test_rental_warns_most_contracts_prohibit_mexico(self):
        r = crossing("US", "MX", rental=True)
        assert any("PROHIBIT" in d for d in r["vehicleDocs"])

    def test_units_switch_to_mxn(self):
        u = crossing("US", "MX")["unitsAfter"]
        assert (u["distance"], u["currency"]) == ("km", "MXN")


class TestCrossingBackIntoUS:
    def test_units_back_to_imperial_usd(self):
        u = crossing("CA", "US")["unitsAfter"]
        assert (u["distance"], u["temp"], u["currency"], u["fuel"]) == \
            ("mi", "F", "USD", "gallon")

    def test_rental_line_present_only_with_flag(self):
        assert not any("Rental" in d for d in crossing("CA", "US")["vehicleDocs"])
        assert any("Rental" in d
                   for d in crossing("CA", "US", rental=True)["vehicleDocs"])

    def test_case_insensitive_country_codes(self):
        r = crossing("ca", "us")
        assert (r["from"], r["to"]) == ("CA", "US")


class TestErrorsAndTripSection:
    def test_unsupported_destination_is_error(self):
        assert crossing("US", "XX")["source"] == "error"

    def test_trip_section_aggregates_and_summarizes(self):
        s = trip_section([("US", "CA", False), ("CA", "US", False)])
        assert len(s["crossings"]) == 2
        assert s["summary"] == "US→CA · CA→US"

    def test_trip_section_summary_skips_error_crossings(self):
        s = trip_section([("US", "CA", False), ("US", "XX", False)])
        assert len(s["crossings"]) == 2   # the error entry stays in the list
        assert s["summary"] == "US→CA"    # ...but is excluded from the summary
