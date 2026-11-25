"""Structural checks of the page: sections, meta data, language, placeholders, assets."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from page_model import collect, parse_tree, text_of, walk

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"

SECTION_IDS = ["about", "experience", "skills", "projects", "contact"]
PLACEHOLDER_TOKENS = [
    "[Name]",
    "[Job title from the CV]",
    "[Role from the CV]",
    "[Company from the CV]",
    "[Project name]",
    "[Skill]",
    "[e-mail — to be provided by the owner]",
    "[LinkedIn profile — link to be provided by the owner]",
]
FORBIDDEN_WORDS = ["lorem", "ipsum", "xxx", "todo:", "tbd,"]
PLACEHOLDER_IMAGE = "assets/img/avatar-placeholder.svg"


@pytest.fixture(scope="module")
def html_text() -> str:
    return INDEX.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def page(html_text: str) -> Any:
    return collect(html_text)


@pytest.fixture(scope="module")
def tree(html_text: str) -> dict[str, Any]:
    return parse_tree(html_text)


def tags_of(page: Any, tag: str) -> list[dict[str, str | None]]:
    return [attrs for name, attrs in page.tags if name == tag]


def ids_of(page: Any) -> list[str]:
    return [str(attrs["id"]) for _, attrs in page.tags if attrs.get("id")]


def meta_of(page: Any) -> dict[str, str | None]:
    """<meta> content keyed by name or property (og:* and twitter:* use property)."""
    meta: dict[str, str | None] = {}
    for attrs in tags_of(page, "meta"):
        key = attrs.get("name") or attrs.get("property")
        if key:
            meta[str(key)] = attrs.get("content")
    return meta


def visible_text(page: Any) -> str:
    return " ".join(page.text)


# ---------- document basics ----------


def test_page_is_valid_english_html5(html_text: str, page: Any) -> None:
    assert html_text.lstrip().lower().startswith("<!doctype html>")
    html = next(attrs for tag, attrs in page.tags if tag == "html")
    assert html.get("lang") == "en"
    assert {"head", "main", "footer"} <= {tag for tag, _ in page.tags}


def test_every_visible_text_is_english(html_text: str, page: Any) -> None:
    lowered = visible_text(page).lower()
    for word in FORBIDDEN_WORDS:
        assert word not in lowered, word
    assert "zástupný" not in lowered and "komentářem" not in lowered


def test_page_loads_nothing_from_a_cdn(page: Any) -> None:
    # no CDN, no external scripts or styles: the page must work offline from file://
    assert not [attrs for tag, attrs in page.tags if tag == "script" and str(attrs.get("src", "")).startswith("http")]
    for attrs in tags_of(page, "link"):
        href = str(attrs.get("href") or "")
        assert not href.startswith(("http:", "//")), href


def test_page_uses_no_framework_and_no_build_output(page: Any) -> None:
    # plain HTML/CSS/JS: no bundler output, no framework runtime, nothing to compile
    for attrs in tags_of(page, "script"):
        assert not str(attrs.get("src", "")).endswith(".min.js"), attrs
        assert str(attrs.get("type", "")).lower() not in ("module", "text/jsx", "text/babel"), attrs
    for attrs in tags_of(page, "link"):
        assert not str(attrs.get("href", "")).endswith(".min.css"), attrs


# ---------- meta data for deployment ----------


def test_meta_data_present(page: Any) -> None:
    meta = meta_of(page)
    assert meta.get("viewport") == "width=device-width, initial-scale=1"
    assert meta.get("description")
    assert meta.get("author")
    assert meta.get("color-scheme") == "dark light"
    assert meta.get("twitter:card") == "summary"
    assert meta.get("og:type") == "website"
    assert meta.get("og:title")
    assert meta.get("og:description")
    themes = [attrs for attrs in tags_of(page, "meta") if attrs.get("name") == "theme-color"]
    assert len(themes) == 2
    assert {attrs.get("media") for attrs in themes} == {
        "(prefers-color-scheme: dark)",
        "(prefers-color-scheme: light)",
    }


def test_title_names_the_owner_and_the_role(html_text: str) -> None:
    title = re.search(r"<title>(.*?)</title>", html_text, re.S)
    assert title and "[Name]" in title.group(1)
    assert "engineer" in title.group(1).lower()


def test_favicon_is_linked_and_exists(page: Any) -> None:
    icons = [attrs for attrs in tags_of(page, "link") if attrs.get("rel") in ("icon", "apple-touch-icon")]
    assert icons, "no favicon"
    assert any(attrs.get("type") == "image/svg+xml" for attrs in icons)
    for attrs in icons:
        assert (ROOT / str(attrs["href"])).is_file(), attrs["href"]


def test_manifest_is_linked_and_exists(page: Any) -> None:
    manifests = [attrs for attrs in tags_of(page, "link") if attrs.get("rel") == "manifest"]
    assert len(manifests) == 1
    path = ROOT / str(manifests[0]["href"])
    assert path.is_file()
    assert path.name == "site.webmanifest"


def test_stylesheet_and_script_are_linked_local_files(page: Any) -> None:
    styles = [str(attrs["href"]) for attrs in tags_of(page, "link") if attrs.get("rel") == "stylesheet"]
    assert styles and all((ROOT / path).is_file() for path in styles)
    scripts = [str(attrs["src"]) for attrs in tags_of(page, "script") if attrs.get("src")]
    assert scripts and all((ROOT / path).is_file() for path in scripts)


# ---------- sections ----------


def test_sections_in_the_usual_personal_site_order(page: Any) -> None:
    sections = [attrs for tag, attrs in page.tags if tag == "section"]
    order = [str(attrs["id"]) for attrs in sections if attrs.get("id")]
    assert order == ["top"] + SECTION_IDS


def test_each_section_holds_its_own_heading(tree: dict[str, Any]) -> None:
    # the section id is the anchor the navigation uses, so the heading must not repeat it; what
    # matters is that every section carries a non-empty heading nested inside itself
    sections = [node for node in walk(tree) if node["tag"] == "section" and node["attributes"].get("id") in SECTION_IDS]
    assert len(sections) == len(SECTION_IDS)
    for section in sections:
        headings = [node for node in walk(section) if node["tag"] in ("h2", "h3")]
        assert headings, f'section {section["attributes"]["id"]} has no heading'
        assert text_of(headings[0]), f'section {section["attributes"]["id"]} has an empty heading'


def test_heading_levels_are_ordered(page: Any) -> None:
    levels = [tag for tag, _ in page.tags if tag in ("h1", "h2")]
    assert levels[0] == "h1" and levels.count("h1") == 1, levels
    assert set(levels[1:]) == {"h2"}, levels


def test_hero_carries_name_subtitle_and_summary(page: Any) -> None:
    assert len([tag for tag, _ in page.tags if tag == "h1"]) == 1
    hero = visible_text(page)
    assert "[Name]" in hero
    assert "[Job title from the CV]" in hero
    assert "[One or two sentence summary from the CV.]" in hero


def test_experience_skills_and_projects_have_placeholder_entries(page: Any) -> None:
    text = visible_text(page)
    for token in PLACEHOLDER_TOKENS:
        assert token in text, token
    assert text.count("[Role from the CV]") >= 2, "expected more than one experience entry"
    assert text.count("[Project name]") >= 3, "expected at least three projects"


def test_navigation_links_resolve_to_existing_ids(page: Any) -> None:
    anchors = [str(attrs["href"]) for tag, attrs in page.tags if tag == "a" and str(attrs.get("href", "")).startswith("#")]
    assert anchors, "the page has no internal navigation"
    existing = set(ids_of(page))
    for href in anchors:
        assert href[1:] in existing, href
    for section_id in SECTION_IDS:
        assert f"#{section_id}" in anchors, section_id


def test_ids_are_unique(page: Any) -> None:
    ids = ids_of(page)
    duplicates = {value for value in ids if ids.count(value) > 1}
    assert not duplicates, duplicates


def test_every_linked_asset_exists(page: Any) -> None:
    references = [str(attrs["src"]) for tag, attrs in page.tags if tag in ("img", "script") and attrs.get("src")]
    references += [str(attrs["href"]) for tag, attrs in page.tags if tag == "link" and attrs.get("href")]
    for reference in references:
        assert not reference.startswith("#"), reference
        assert (ROOT / reference).is_file(), reference


def test_images_have_dimensions_and_alternative_text(page: Any) -> None:
    images = tags_of(page, "img")
    assert images
    for attrs in images:
        assert attrs.get("alt"), "images need alt text"
        assert attrs.get("width") and attrs.get("height"), "images need width/height to avoid layout shift"


# ---------- profile photo ----------


def test_owner_photo_is_referenced_with_a_placeholder_fallback(page: Any) -> None:
    avatar = next(attrs for attrs in tags_of(page, "img") if "avatar" in str(attrs.get("class", "")))
    assert str(avatar["src"]).endswith(".svg")
    assert (ROOT / str(avatar["src"])).is_file()
    fallback = str(avatar["data-photo-fallback"])
    assert (ROOT / fallback).is_file()
    js = (ROOT / "assets" / "js" / "main.js").read_text(encoding="utf-8")
    assert "assets/img/profile.jpg" in js, "the real photo must be picked up automatically"


def test_avatar_crop_is_theme_independent(page: Any) -> None:
    # the crop must read the same in dark and light: fixed square box, cover, circle, and every
    # colour of the frame taken from a theme token
    css = (ROOT / "assets" / "css" / "styles.css").read_text(encoding="utf-8")
    block = re.search(r"^\.avatar__img\s*\{(.*?)\n\}", css, re.M | re.S)
    assert block, ".avatar__img has no base rule"
    declarations = block.group(1)
    for rule in ("aspect-ratio: 1 / 1", "object-fit: cover", "border-radius: 50%"):
        assert rule in declarations, rule
    for token in ("var(--avatar-bg)", "var(--ring)", "var(--border)"):
        assert token in declarations, token
    assert ".avatar__img" not in css.split("[data-theme=\"light\"]")[1], "the crop must not be redefined per theme"


# ---------- contact ----------


def test_contact_section_has_no_form_and_no_links(page: Any) -> None:
    assert not [tag for tag, _ in page.tags if tag == "form"], "the page must have no contact form"
    assert not [tag for tag, _ in page.tags if tag == "input"], "the page must have no form fields"
    for tag, attrs in page.tags:
        href = str(attrs.get("href") or "")
        assert "mailto:" not in href
        assert not href.startswith(("http:", "https:", "//")), f"unexpected external link: {href}"


def test_contact_placeholders_present(page: Any) -> None:
    rows = [attrs for tag, attrs in page.tags if "contact__row" in str(attrs.get("class", ""))]
    assert len(rows) == 2
    terms = [item.lower() for item in page.text]
    assert any("e-mail" in item for item in terms)
    assert any("linkedin" in item for item in terms)
    assert any("to be provided by the owner" in item for item in terms)


def test_the_placeholder_image_is_used_by_the_avatar_only(page: Any) -> None:
    # the avatar is the one deliberate placeholder image; anywhere else it would be a forgotten stub
    users = [
        str(attrs.get("src") or attrs.get("href"))
        for tag, attrs in page.tags
        if tag in ("img", "source") and PLACEHOLDER_IMAGE in str(attrs.get("src") or attrs.get("href"))
    ]
    assert len(users) == 1, users
