"""Share-button regression coverage."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_share_button_is_rendered_after_tips():
    template = (ROOT / "assets" / "template.html").read_text(encoding="utf-8")
    assert template.index('id="tips"') < template.index('id="share"')
    assert 'id="shareButton"' in template
    assert 'navigator.share' in template
    assert 'navigator.clipboard.writeText' in template
    assert 'aria-live="polite"' in template


def test_share_change_keeps_budget_after_lodging_section_removal():
    template = (ROOT / "assets" / "template.html").read_text(encoding="utf-8")
    assert 'id="lodging"' not in template
    assert 'id="budget"' in template
    assert 'renderBudget(); renderTips(); renderShare();' in template
