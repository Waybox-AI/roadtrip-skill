import pytest
from tools.routing_client import haversine_miles

# Great-circle (straight-line) distances between well-known city pairs.
# Expected values are the true haversine distances (not driving distances).
# Tolerance is ±5% as specified.
CITY_PAIRS = [
    # (point_a, point_b, expected_miles, label)
    (
        (36.1699, -115.1398),  # Las Vegas, NV
        (37.2982, -113.0263),  # Zion NP entrance, UT
        141,
        "Las Vegas to Zion NP",
    ),
    (
        (34.0522, -118.2437),  # Los Angeles, CA
        (37.7749, -122.4194),  # San Francisco, CA
        348,
        "LA to San Francisco",
    ),
    (
        (47.6062, -122.3321),  # Seattle, WA
        (45.5051, -122.6750),  # Portland, OR
        146,
        "Seattle to Portland",
    ),
    (
        (40.7128, -74.0060),   # New York City, NY
        (42.3601, -71.0589),   # Boston, MA
        190,
        "NYC to Boston",
    ),
]


class TestHaversineMiles:
    @pytest.mark.parametrize("a,b,expected,label", CITY_PAIRS)
    def test_known_city_pair(self, a, b, expected, label):
        result = haversine_miles(a, b)
        assert abs(result - expected) / expected <= 0.05, (
            f"{label}: got {result:.1f} mi, expected ~{expected} mi (±5%)"
        )

    def test_same_point_is_zero(self):
        assert haversine_miles((36.0, -115.0), (36.0, -115.0)) == pytest.approx(0.0)

    def test_symmetric(self):
        a = (36.1699, -115.1398)
        b = (37.2982, -113.0263)
        assert haversine_miles(a, b) == pytest.approx(haversine_miles(b, a))

    def test_result_is_positive(self):
        a = (34.0522, -118.2437)
        b = (37.7749, -122.4194)
        assert haversine_miles(a, b) > 0
