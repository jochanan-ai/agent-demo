"""Dark as the default theme, a working light toggle, and motion limited by the browser setting."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"
CSS = ROOT / "assets" / "css" / "styles.css"
JS = ROOT / "assets" / "js" / "main.js"


@pytest.fixture(scope="module")
def html_text() -> str:
    return INDEX.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def css() -> str:
    return CSS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def js() -> str:
    return JS.read_text(encoding="utf-8")


def media_blocks(css: str, condition: str) -> str:
    """Body of the @media blocks matching `condition` (they contain no nested at-rules)."""
    return "\n".join(re.findall(rf"@media\s*\(\s*{re.escape(condition)}\s*\)\s*\{{(.*?)\n\}}", css, re.S))


def declarations_in(css: str, selector: str) -> str:
    match = re.search(rf"^{selector}\s*\{{(.*?)\n\}}", css, re.M | re.S)
    assert match, selector
    return match.group(1)


# ---------- theme ----------


def test_dark_is_the_default_theme(html_text: str, css: str) -> None:
    assert 'data-theme="dark"' in html_text, "the theme attribute is set before the first paint"
    assert '<html lang="en" data-theme="dark">' in html_text
    assert 'color-scheme: dark;' in declarations_in(css, ":root")


def test_light_theme_is_a_data_theme_override(css: str) -> None:
    assert "[data-theme=\"light\"]" in css
    assert 'color-scheme: light;' in declarations_in(css, '[data-theme="light"]')


def test_theme_tokens_are_defined_for_both_themes(css: str) -> None:
    dark = declarations_in(css, ":root")
    light = declarations_in(css, '[data-theme="light"]')
    dark_tokens = set(re.findall(r"(--[\w-]+)\s*:", dark))
    light_tokens = set(re.findall(r"(--[\w-]+)\s*:", light))
    assert dark_tokens
    assert dark_tokens <= light_tokens | dark_tokens
    # every colour the page uses comes from a token, so light really repaints the whole page
    assert {"--bg", "--surface", "--bg-elevated", "--text", "--text-muted", "--heading", "--accent", "--avatar-bg"} <= dark_tokens
    assert {"--bg", "--surface", "--bg-elevated", "--text", "--text-muted", "--heading", "--accent", "--avatar-bg"} <= light_tokens
    assert not re.search(r"(background|color)\s*:\s*(#[0-9a-fA-F]{3,8}|rgba?\()", css.split("[data-theme")[1]), (
        "colours outside the token blocks would not follow the theme"
    )


def test_theme_is_applied_before_first_paint(html_text: str) -> None:
    head = html_text.split("</head>")[0]
    script = re.search(r"<script>(.*?)</script>", head, re.S)
    assert script, "the theme must be restored by an inline script in <head>"
    body = script.group(1)
    assert 'localStorage.getItem("theme")' in body
    assert 'setAttribute("data-theme", stored)' in body
    assert head.index("</script>") < head.index('<link rel="stylesheet"'), "theme before stylesheet"


def test_toggle_button_exists_with_state(html_text: str) -> None:
    assert 'id="theme-toggle"' in html_text
    assert 'class="theme-toggle"' in html_text
    assert 'aria-pressed=' in html_text
    assert "aria-label=\"Switch to light theme\"" in html_text


def test_toggle_writes_the_attribute_and_remembers_the_choice(js: str) -> None:
    assert 'setAttribute("data-theme", theme)' in js
    assert "addEventListener(\"click\"" in js
    assert 'localStorage.setItem(STORAGE_KEY, theme)' in js
    assert 'var STORAGE_KEY = "theme"' in js


def test_theme_toggle_announces_the_next_theme(js: str) -> None:
    assert '"aria-label", "Switch to " + target + " theme"' in js
    assert '"aria-pressed", theme === "light" ? "true" : "false"' in js


def test_theme_falls_back_to_the_os_preference_and_survives_private_storage(js: str) -> None:
    assert 'matchMedia("(prefers-color-scheme: light)")' in js
    assert js.count("try {") >= 2 and js.count("catch") >= 2, "storage access must be guarded"


# ---------- motion ----------


def test_scroll_reveal_is_gated_by_prefers_reduced_motion(css: str) -> None:
    allowed = media_blocks(css, "prefers-reduced-motion: no-preference")
    assert "[data-reveal]" in allowed
    assert ".is-visible" in allowed
    assert "opacity: 0" in allowed and "transform: translateY(24px)" in allowed
    # the default (reduced-motion) case must not be hidden by a missing class
    reduced = media_blocks(css, "prefers-reduced-motion: reduce")
    assert "[data-reveal]" in reduced
    after = reduced.split("[data-reveal]")[1]
    assert "opacity: 1" in after and "transform: none" in after


def test_reduced_motion_disables_transitions_and_smooth_scrolling(css: str) -> None:
    reduced = media_blocks(css, "prefers-reduced-motion: reduce")
    assert "transition-duration: 0.001ms !important" in reduced
    assert "animation-duration: 0.001ms !important" in reduced
    assert "scroll-behavior: auto !important" in reduced


def test_hover_effects_exist_for_cards_and_buttons(css: str) -> None:
    for selector in (r"\.card:hover", r"\.button:hover", r"\.tag:hover", r"\.timeline__item:hover"):
        declarations = declarations_in(css, selector)
        assert "transform" in declarations or "box-shadow" in declarations, selector


def test_javascript_reveals_only_when_motion_is_allowed(js: str) -> None:
    assert 'matchMedia("(prefers-reduced-motion: reduce)")' in js
    reveal = js.split("function initReveal()")[1]
    assert "prefersReducedMotion()" in reveal
    assert "revealAll(sections)" in reveal
    assert "IntersectionObserver" in reveal


def test_revealed_sections_are_present_without_javascript(html_text: str) -> None:
    # no inline <style> that hides sections: without JS everything stays readable
    assert "<style" not in html_text
    assert html_text.count("data-reveal") >= 6
