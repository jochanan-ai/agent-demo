"""Shared parsing of index.html for the tests: a flat tag record and an element tree.

Both are built from the real page, so a test never works with invented markup: Collector answers
"which tags and attributes are on the page", TreeBuilder answers "which element contains which"
(the tree is also what tests/js/ receives as JSON).
"""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from typing import Any

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class Collector(HTMLParser):
    """Flat record of the tags, attributes and text of the page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict[str, str | None]]] = []
        self.text: list[str] = []
        self.stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, dict(attrs)))
        if tag not in VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in VOID:
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


class TreeBuilder(HTMLParser):
    """index.html -> the plain-object tree tests/js/dom.mjs expects."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.html: dict[str, Any] | None = None
        self.stack: list[dict[str, Any]] = []

    def _push(self, node: dict[str, Any]) -> None:
        if self.stack:
            self.stack[-1]["children"].append(node)
        elif node["tag"] == "html":
            self.html = node

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = {"tag": tag, "attributes": {k: (v if v is not None else "") for k, v in attrs}, "children": []}
        self._push(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._push({"tag": tag, "attributes": {k: (v if v is not None else "") for k, v in attrs}, "children": []})

    def handle_endtag(self, tag: str) -> None:
        if tag in VOID:
            return
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]["tag"] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data: str) -> None:
        if self.stack and (data.strip() or self.stack[-1]["tag"] == "script"):
            self.stack[-1]["children"].append({"text": data})


def collect(html_text: str) -> Collector:
    collector = Collector()
    collector.feed(html_text)
    collector.close()
    return collector


def parse_tree(html_text: str) -> dict[str, Any]:
    builder = TreeBuilder()
    builder.feed(html_text)
    builder.close()
    assert builder.html is not None, "index.html has no <html> element"
    assert not builder.stack, f"unclosed tags: {[node['tag'] for node in builder.stack]}"
    return builder.html


def walk(node: dict[str, Any]):
    """Every element node below `node`, depth first."""
    for child in node.get("children", []):
        if "tag" in child:
            yield child
            yield from walk(child)


def text_of(node: dict[str, Any]) -> str:
    """Text content of a subtree, whitespace collapsed."""
    parts = [child["text"] for child in node.get("children", []) if "text" in child]
    parts += [text_of(child) for child in node.get("children", []) if "tag" in child]
    return " ".join(" ".join(parts).split())


def find_by_id(tree: dict[str, Any], element_id: str) -> dict[str, Any] | None:
    return next((node for node in walk(tree) if node["attributes"].get("id") == element_id), None)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")
