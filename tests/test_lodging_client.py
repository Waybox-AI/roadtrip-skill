"""lodging_client: deep links for every platform, date pre-fill on the
Booking link, the coarse reference price by tier, and the China-only Ctrip
city deep link (city resolved via tools/ctrip_city_ids.py — keyword-only
Ctrip URLs silently fall back to Shanghai, so no city match means no link).
Pure URL building — the suite is offline.
"""

from urllib.parse import quote, quote_plus

from tools import lodging_client as lc

PLATFORMS = {"booking", "airbnb", "google_hotels", "koa", "hipcamp", "recreation_gov"}


class TestSearchLinks:
    def test_us_place_gets_global_platforms_and_no_ctrip(self):
        assert set(lc.search_links("Springdale, UT")) == PLATFORMS

    def test_place_encoded_into_keyword_links(self):
        assert quote_plus("Las Vegas") in lc.search_links("Las Vegas")["booking"]

    def test_booking_dates_prefilled_only_when_both_given(self):
        links = lc.search_links("Springdale, UT", "2026-09-12", "2026-09-14")
        assert "checkin=2026-09-12" in links["booking"]
        assert "checkout=2026-09-14" in links["booking"]
        assert "checkin" not in lc.search_links("Springdale, UT", "2026-09-12")["booking"]


class TestCtripLink:
    def test_china_hotel_resolves_city_and_prefills_keyword(self):
        links = lc.search_links("成都博舍, 成都·太古里")
        assert links["ctrip"] == "https://hotels.ctrip.com/hotel/chengdu28/k1" + quote("博舍")

    def test_county_level_city_resolved_from_area(self):
        url = lc.ctrip_link("青城山六善酒店, 都江堰·青城山")
        assert url == "https://hotels.ctrip.com/hotel/dujiangyan94/k1" + quote("青城山六善酒店")

    def test_prefecture_alias_resolves(self):
        url = lc.ctrip_link("洱海边的民宿, 大理")
        assert url == ("https://hotels.ctrip.com/hotel/dalibaizuzizhizhou669326/k1"
                       + quote("洱海边的民宿"))

    def test_city_only_place_links_city_page_without_keyword(self):
        assert lc.ctrip_link("都江堰") == "https://hotels.ctrip.com/hotel/dujiangyan94/"

    def test_dates_forwarded_as_start_end(self):
        url = lc.ctrip_link("成都博舍, 成都·太古里", "2026-10-01", "2026-10-03")
        assert url.endswith("/k1" + quote("博舍") + "?startDate=2026-10-01&endDate=2026-10-03")
        links = lc.search_links("成都博舍, 成都·太古里", "2026-10-01", "2026-10-03")
        assert "startDate=2026-10-01" in links["ctrip"]

    def test_unknown_chinese_place_gets_no_link(self):
        assert lc.ctrip_link("幽灵客栈, 蟹蟹星球") is None
        assert "ctrip" not in lc.search_links("幽灵客栈, 蟹蟹星球")

    def test_non_chinese_place_gets_no_link(self):
        assert lc.ctrip_link("Cable Mountain Lodge, Springdale, UT (Zion)") is None


class TestQuote:
    def test_quote_carries_links_and_reference_price(self):
        q = lc.quote("Springdale, UT", tier="budget")
        assert set(q["links"]) == PLATFORMS
        assert q["pricePerNight"] == lc.TIER_PRICE["budget"]
        assert q["reliability"] == "reference"

    def test_unknown_tier_falls_back_to_midrange(self):
        assert lc.reference_price("penthouse")["pricePerNight"] == lc.TIER_PRICE["midrange"]
