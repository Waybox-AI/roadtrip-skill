"""Itinerary theme regression coverage."""

import json
from pathlib import Path

from assets.generate import build_html


ROOT = Path(__file__).resolve().parents[1]


def _render():
    trip = json.loads(
        (ROOT / "assets" / "tripData.example.json").read_text(encoding="utf-8")
    )
    template = (ROOT / "assets" / "template.html").read_text(encoding="utf-8")
    return build_html(trip, template)


def test_itinerary_defaults_to_webapp_dark_theme_with_light_option():
    html = _render()
    assert '--bg: #12171d' in html
    assert '--accent: #fffbbb' in html
    assert 'html[data-theme="light"]' in html
    assert 'localStorage.getItem("rtn_theme")' in html
    assert 'themeColor.setAttribute("content", theme === "light"' in html
    assert ':root, html[data-theme="light"]' in html
    assert '--bg: #fff; --card: #fff; --card-2: #f5f5f3' in html


def test_itinerary_renders_an_accessible_theme_toggle():
    html = _render()
    assert 'id="themeToggle"' in html
    assert 'Switch to day mode' in html
    assert '切换到日间模式' in html
