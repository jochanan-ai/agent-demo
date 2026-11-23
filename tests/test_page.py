"""Structural checks of the page: sections, meta data, language, placeholders, assets."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

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


class Collector(HTMLParser):
    """Flat record of the tags, attributes and text of the page."""

    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict[str, str | None]]] = []
        self.text: list[str] = []
        self.stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, dict(attrs)))
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in self.VOID:
            return
        assert tag in self.stack, f"closing tag </{tag}> without an opening tag"
        while self.stack:
            if self.stack.pop() == tag:
                break

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.text.append(data.strip())

    def close(self) -> None:
        super().close()
        assert not self.stack, f"unclosed tags: {self.stack}"


@pytest.fixture(scope="module")
def html_text() -> str:
    return INDEX.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def page(html_text: str) -> Collector:
    collector = Collector()
    collector.feed(html_text)
    collector.close()
    return collector


def tags_of(page: Collector, tag: str) -> list[dict[str, str | None]]:
    return [attrs for name, attrs in page.tags if name == tag]


def ids_of(page: Collector) -> list[str]:
    return [str(attrs["id"]) for attrs in page.tags if attrs.get("id")]


def visible_text(page: Collector) -> str:
    return " ".join(page.text)


# ---------- document basics ----------


def test_page_is_valid_english_html5(html_text: str, page: Collector) -> None:
    assert html_text.lstrip().lower().startswith("<!doctype html>")
    html = next(attrs for tag, attrs in page.tags if tag == "html")
    assert html.get("lang") == "en"
    assert {"head", "main", "footer"} <= {tag for tag, _ in page.tags}


def test_every_visible_text_is_english(html_text: str, page: Collector) -> None:
    lowered = visible_text(page).lower()
    for word in FORBIDDEN_WORDS:
        assert word not in lowered, word
    assert "zástupný" not in lowered and "komentářem" not in lowered


def test_page_loads_nothing_from_a_cdn(page: Collector) -> None:
    # no CDN, no external scripts or styles: the page must work offline from file://
    assert not [attrs for tag, attrs in page.tags if tag == "script" and str(attrs.get("src", "")).startswith("http")]
    for attrs in tags_of(page, "link"):
        href = str(attrs.get("href") or "")
        assert not href.startswith(("http:", "//")), href


# ---------- meta data for deployment ----------


def test_meta_data_present(page: Collector) -> None:
    meta = {attrs.get("name"): attrs.get("content") for attrs in tags_of(page, "meta")}
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


def test_favicon_is_linked_and_exists(page: Collector) -> None:
    icons = [attrs for attrs in tags_of(page, "link") if attrs.get("rel") in ("icon", "apple-touch-icon")]
    assert icons, "no favicon"
    assert any(attrs.get("type") == "image/svg+xml" for attrs in icons)
    for attrs in icons:
        assert (ROOT / str(attrs["href"])).is_file(), attrs["href"]


def test_manifest_is_linked_and_exists(page: Collector) -> None:
    manifests = [attrs for attrs in tags_of(page, "link") if attrs.get("rel") == "manifest"]
    assert len(manifests) == 1
    assert (ROOT / str(manifests[0]["href"])).is_file()


def test_stylesheet_and_script_are_linked_local_files(page: Collector) -> None:
    styles = [str(attrs["href"]) for attrs in tags_of(page, "link") if attrs.get("rel") == "stylesheet"]
    assert styles and all((ROOT / path).is_file() for path in styles)
    scripts = [str(attrs["src"]) for attrs in tags_of(page, "script") if attrs.get("src")]
    assert scripts and all((ROOT / path).is_file() for path in scripts)


# ---------- sections ----------


def test_sections_in_the_usual_personal_site_order(page: Collector) -> None:
    sections = [attrs for tag, attrs in page.tags if tag == "section"]
    order = [str(attrs["id"]) for attrs in sections if attrs.get("id")]
    assert order == ["top"] + SECTION_IDS


def test_each_section_has_a_heading(page: Collector) -> None:
    headings = [str(attrs["id"]) for tag, attrs in page.tags if tag in ("h1", "h2") and attrs.get("id")]
    for section_id in SECTION_IDS:
        assert section_id in headings, section_id


def test_hero_carries_name_subtitle_and_summary(page: Collector) -> None:
    assert len([tag for tag, _ in page.tags if tag == "h1"]) == 1
    hero = visible_text(page)
    assert "[Name]" in hero
    assert "[Job title from the CV]" in hero
    assert "[One or two sentence summary from the CV.]" in hero


def test_experience_skills_and_projects_have_placeholder_entries(page: Collector) -> None:
    text = visible_text(page)
    for token in PLACEHOLDER_TOKENS:
        assert token in text, token
    assert text.count("[Role from the CV]") >= 2, "expected more than one experience entry"
    assert text.count("[Project name]") >= 3, "expected at least three projects"


def test_navigation_links_resolve_to_existing_ids(page: Collector) -> None:
    anchors = [str(attrs["href"]) for tag, attrs in page.tags if tag == "a" and str(attrs.get("href", "")).startswith("#")]
    assert anchors, "the page has no internal navigation"
    existing = set(ids_of(page))
    for href in anchors:
        assert href[1:] in existing, href
    for section_id in SECTION_IDS:
        assert f"#{section_id}" in anchors, section_id


def test_every_linked_asset_exists(page: Collector) -> None:
    references = [str(attrs["src"]) for tag, attrs in page.tags if tag in ("img", "script") and attrs.get("src")]
    references += [str(attrs["href"]) for tag, attrs in page.tags if tag == "link" and attrs.get("href")]
    for reference in references:
        assert not reference.startswith("#"), reference
        assert (ROOT / reference).is_file(), reference


def test_images_have_dimensions_and_alternative_text(page: Collector) -> None:
    images = tags_of(page, "img")
    assert images
    for attrs in images:
        assert attrs.get("alt"), "images need alt text"
        assert attrs.get("width") and attrs.get("height"), "images need width/height to avoid layout shift"


# ---------- profile photo ----------


def test_owner_photo_is_referenced_with_a_placeholder_fallback(page: Collector) -> None:
    avatar = next(attrs for attrs in tags_of(page, "img") if "avatar" in str(attrs.get("class", "")))
    assert str(avatar["src"]).endswith(".svg")
    assert (ROOT / str(avatar["src"])).is_file()
    fallback = str(avatar["data-photo-fallback"])
    assert (ROOT / fallback).is_file()
    js = (ROOT / "assets" / "js" / "main.js").read_text(encoding="utf-8")
    assert "assets/img/profile.jpg" in js, "the real photo must be picked up automatically"


# ---------- contact ----------


def test_contact_section_has_no_form_and_no_links(page: Collector) -> None:
    assert not [tag for tag, _ in page.tags if tag == "form"], "the page must have no contact form"
    for tag, attrs in page.tags:
        href = str(attrs.get("href") or "")
        assert "mailto:" not in href
        assert not href.startswith(("http:", "https:", "//")), f"unexpected external link: {href}"


def test_contact_placeholders_present(page: Collector) -> None:
    rows = [attrs for tag, attrs in page.tags if "contact__row" in str(attrs.get("class", ""))]
    assert len(rows) == 2
    terms = [item.lower() for item in page.text]
    assert any("e-mail" in item for item in terms)
    assert any("linkedin" in item for item in terms)
    assert any("to be provided by the owner" in item for item in terms)
