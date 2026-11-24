"""Checks of the optional local server: what it serves, what it refuses, and how it is started.

Every check drives the real handler over a real socket (no stubs of the serving code), so a
regression in the guard or in the MIME types fails here.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from http.client import HTTPConnection

import pytest
import site_serve
from site_serve import (
    DEFAULT_PORT,
    HOST,
    Handler,
    ROOT,
    build_server,
    is_served,
    main,
    parse_args,
    resolve_request_target,
)


@pytest.fixture()
def live_server():
    """The real server on an ephemeral port, stopped after the test."""
    server = build_server(HOST, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def fetch(port: int, path: str) -> tuple[int, bytes, str]:
    url = f"http://{HOST}:{port}{path}"
    try:
        with urllib.request.urlopen(url) as response:  # noqa: S310 (localhost URL built here)
            return response.status, response.read(), response.headers.get_content_type()
    except urllib.error.HTTPError as error:
        return error.code, error.read(), error.headers.get_content_type()


# ---------- the path guard ----------


def test_page_and_assets_are_inside_the_served_root() -> None:
    for path in ("/", "/index.html", "/assets/css/styles.css", "/assets/js/main.js", "/site.webmanifest"):
        assert resolve_request_target(path) is not None, path


def test_query_and_fragment_are_stripped_before_resolving() -> None:
    assert resolve_request_target("/index.html?v=2#about") == (ROOT / "index.html").resolve()


def test_escaping_cannot_escape_the_served_directory() -> None:
    for path in ("/../prompt.md", "/%2e%2e/prompt.md", "/%252e%252e/prompt.md", "/assets/../../prompt.md"):
        assert resolve_request_target(path) is None, path


def test_paths_outside_the_site_stay_unreachable(tmp_path) -> None:
    # a request is always resolved inside ROOT, so no request can name a file outside the site
    outside = tmp_path / "outside.txt"
    resolved = resolve_request_target(f"/{outside}")
    assert resolved is None or str(resolved).startswith(str(ROOT)), resolved
    assert resolve_request_target("/no-file-anywhere.html") == (ROOT / "no-file-anywhere.html").resolve()


def test_is_served_accepts_the_root_and_its_children() -> None:
    assert is_served(ROOT)
    assert is_served(ROOT / "assets" / "img" / "favicon.svg")
    assert not is_served(ROOT.parent / "prompt.md")


def test_argument_defaults_and_overrides(monkeypatch) -> None:
    monkeypatch.delenv("PORT", raising=False)
    args = parse_args([])
    assert (args.host, args.port) == (HOST, DEFAULT_PORT)
    monkeypatch.setenv("PORT", "9005")
    assert parse_args([]).port == 9005
    assert parse_args(["--port", "9001", "--host", "0.0.0.0"]).host == "0.0.0.0"


# ---------- serving ----------


def test_index_is_served_as_html(live_server: int) -> None:
    status, body, mime = fetch(live_server, "/")
    assert status == 200
    assert mime.startswith("text/html")
    assert body.lstrip().lower().startswith(b"<!doctype html>")


@pytest.mark.parametrize(
    ("path", "mime_start"),
    [
        ("/assets/css/styles.css", "text/css"),
        ("/assets/js/main.js", "text/javascript"),
        ("/assets/img/favicon.svg", "image/svg+xml"),
        ("/site.webmanifest", "application/manifest+json"),
    ],
)
def test_assets_keep_their_mime_types(live_server: int, path: str, mime_start: str) -> None:
    status, body, mime = fetch(live_server, path)
    assert status == 200, path
    assert mime.startswith(mime_start), (path, mime)
    assert body, path


def test_manifest_is_valid_json(live_server: int) -> None:
    status, body, _ = fetch(live_server, "/site.webmanifest")
    assert status == 200
    assert json.loads(body)["start_url"] == "./index.html"


def test_missing_file_is_a_404(live_server: int) -> None:
    assert fetch(live_server, "/no-such-page.html")[0] == 404


def test_traversal_is_a_404_and_leaks_nothing(live_server: int) -> None:
    for path in ("/../prompt.md", "/%2e%2e/prompt.md", "/assets/../../prompt.md"):
        status, body, _ = fetch(live_server, path)
        assert status == 404, path
        assert b"spec-sha256" not in body, path


def test_head_is_answered_without_a_body(live_server: int) -> None:
    connection = HTTPConnection(HOST, live_server, timeout=5)
    try:
        connection.request("HEAD", "/index.html")
        response = connection.getresponse()
        body = response.read()
    finally:
        connection.close()
    assert response.status == 200
    assert body == b""
    assert int(response.getheader("Content-Length", "0")) > 0


def test_head_of_a_traversal_is_a_404(live_server: int) -> None:
    connection = HTTPConnection(HOST, live_server, timeout=5)
    try:
        connection.request("HEAD", "/%2e%2e/prompt.md")
        response = connection.getresponse()
        response.read()
    finally:
        connection.close()
    assert response.status == 404


def test_the_server_stays_quiet_and_identifies_itself() -> None:
    assert Handler.server_version == "personal-site"
    assert "log_message" in Handler.__dict__
    assert Handler.log_message(object(), "%s %s", "GET", "/") is None


def test_a_busy_port_fails_loudly() -> None:
    # no silent port hopping: the visitor starts the server by hand and expects the announced port
    blocker = build_server(HOST, 0)
    try:
        with pytest.raises(OSError):
            build_server(HOST, blocker.server_address[1])
    finally:
        blocker.server_close()


def test_main_starts_serves_and_stops(monkeypatch, capsys) -> None:
    # the real server is kept; the subclass only records the instance so the test can shut it down
    created: list[site_serve.ThreadingHTTPServer] = []

    class RecordingServer(site_serve.ThreadingHTTPServer):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, **kwargs)  # type: ignore[arg-type]
            created.append(self)

    monkeypatch.setattr(site_serve, "ThreadingHTTPServer", RecordingServer)
    result: list[int] = []
    thread = threading.Thread(target=lambda: result.append(main(["--port", "0"])), daemon=True)
    thread.start()
    for _ in range(200):
        if created:
            break
        threading.Event().wait(0.05)
    assert created, "main() did not start a server"
    port = created[0].server_address[1]
    try:
        assert f"http://{HOST}:{port}/" in capsys.readouterr().out
        status, body, _ = fetch(port, "/index.html")
        assert status == 200 and body.lstrip().lower().startswith(b"<!doctype html>")
    finally:
        created[0].shutdown()
    thread.join(timeout=5)
    assert result == [0]
    assert created[0].server_close is not None


def test_main_survives_a_keyboard_interrupt(monkeypatch) -> None:
    # Ctrl-C in the terminal must end the run cleanly (server socket closed, exit code 0)
    class Interrupted(site_serve.ThreadingHTTPServer):
        def serve_forever(self, *args: object, **kwargs: object) -> None:
            raise KeyboardInterrupt

    monkeypatch.setattr(site_serve, "ThreadingHTTPServer", Interrupted)
    assert main(["--port", "0"]) == 0


def test_module_runs_as_a_program() -> None:
    # `python -m site_serve --port ...` is how the README starts it
    with socket.socket() as probe:
        probe.bind((HOST, 0))
        port = probe.getsockname()[1]
    process = subprocess.Popen(
        [sys.executable, "-m", "site_serve", "--port", str(port)],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        assert f"http://{HOST}:{port}/" in process.stdout.readline()
        status, body, _ = fetch(port, "/index.html")
        assert status == 200 and body.lstrip().lower().startswith(b"<!doctype html>")
    finally:
        process.terminate()
        process.wait(timeout=10)
