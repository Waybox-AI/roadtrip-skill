"""Day badge contrast regression coverage."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_day_badge_uses_the_theme_contrast_color():
    template = (ROOT / "assets" / "template.html").read_text(encoding="utf-8")
    assert '.day-badge { background: var(--accent); color: var(--on-accent);' in template
    assert '--accent: #fffbbb; --on-accent: #12171d;' in template
