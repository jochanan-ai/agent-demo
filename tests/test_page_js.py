"""Behaviour tests of the page's own script: assets/js/main.js runs under node against index.html.

The element tree handed to node is parsed here from the real index.html (html.parser), so main.js
never runs against invented markup. tests/js/run.mjs exits with the number of failed checks.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"
RUNNER = ROOT / "tests" / "js" / "run.mjs"

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


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


def page_tree() -> dict[str, Any]:
    builder = TreeBuilder()
    builder.feed(INDEX.read_text(encoding="utf-8"))
    builder.close()
    assert builder.html is not None, "index.html has no <html> element"
    assert not builder.stack, f"unclosed tags: {[node['tag'] for node in builder.stack]}"
    return builder.html


def node_binary() -> str:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed: the page script behaviour tests cannot run")
    return node


@pytest.fixture(scope="module")
def tree() -> dict[str, Any]:
    return page_tree()


def run_page_script(tmp_path: Path, tree: dict[str, Any], *args: str) -> subprocess.CompletedProcess[str]:
    tree_file = tmp_path / "page-tree.json"
    tree_file.write_text(json.dumps(tree, ensure_ascii=False), encoding="utf-8")
    return subprocess.run(
        [node_binary(), str(RUNNER), str(tree_file), *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=120,
        env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)},
    )


def test_index_html_parses_into_a_tree_with_the_page_sections(tree: dict[str, Any]) -> None:
    # the harness is only as real as this tree: without it the behaviour tests would prove nothing
    assert tree["attributes"].get("lang") == "en"
    tags = [child["tag"] for child in tree["children"]]
    assert tags == ["head", "body"]
    body = tree["children"][1]
    sections = [n for n in _walk(body) if n["tag"] == "section"]
    assert {n["attributes"].get("id") for n in sections} >= {
        "top",
        "about",
        "experience",
        "skills",
        "projects",
        "contact",
    }
    assert [n for n in _walk(body) if n["attributes"].get("id") == "theme-toggle"]
    assert any(n["tag"] == "script" and n["attributes"].get("src") == "assets/js/main.js" for n in _walk(body))


def test_inline_head_script_is_carried_into_the_tree(tree: dict[str, Any]) -> None:
    head = tree["children"][0]
    inline = [n for n in _walk(head) if n["tag"] == "script" and not n["attributes"].get("src")]
    assert len(inline) == 1, "the theme script of <head> must reach the harness"
    text = "".join(child["text"] for child in inline[0]["children"] if "text" in child)
    assert 'localStorage.getItem("theme")' in text


def test_the_page_script_passes_every_behaviour_check(tmp_path: Path, tree: dict[str, Any]) -> None:
    result = run_page_script(tmp_path, tree)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "all checks passed" in output, output
    assert output.count("ok ") >= 20, output


def _walk(node: dict[str, Any]):
    for child in node.get("children", []):
        if "tag" in child:
            yield child
            yield from _walk(child)


if __name__ == "__main__":  # convenience: python tests/test_page_js.py [index.html]
    if len(sys.argv) > 2:  # pragma: no cover - manual debugging only
        INDEX = Path(sys.argv[2])
    print(json.dumps(page_tree(), indent=1))  # noqa: T201
