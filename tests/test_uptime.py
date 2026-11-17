import json
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from http.server import ThreadingHTTPServer

import pytest

from app import server
from app.server import Handler, route, uptime_seconds


@pytest.fixture
def base_url() -> Iterator[str]:
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}"
    finally:
        srv.shutdown()
        srv.server_close()


def get_json(base_url: str, path: str) -> tuple[int, dict[str, object]]:
    with urllib.request.urlopen(f"{base_url}{path}", timeout=5) as resp:
        assert resp.headers["Content-Type"] == "application/json"
        return resp.status, json.loads(resp.read())


def test_uptime_route_answers_uptime_seconds():
    status, body = route("/api/uptime")
    assert status == 200
    assert set(body) == {"uptime_seconds"}
    value = body["uptime_seconds"]
    assert isinstance(value, int) and not isinstance(value, bool)
    assert value >= 0


def test_uptime_route_is_not_matched_by_a_similar_path():
    assert route("/api/uptime/")[0] == 404
    assert route("/uptime")[0] == 404
    assert route("/api/uptimex")[0] == 404


def test_uptime_seconds_counts_whole_seconds_since_the_server_started(monkeypatch):
    start = time.monotonic() - 123
    monkeypatch.setattr(server, "SERVER_START_MONOTONIC", start)
    assert uptime_seconds(now=start + 123) == 123
    assert uptime_seconds(now=start + 123.999) == 123
    # the real clock: the value is the whole seconds elapsed since the reference point
    before = int(time.monotonic() - start)
    value = uptime_seconds()
    after = int(time.monotonic() - start)
    assert before >= 123
    assert before <= value <= after


def test_uptime_seconds_uses_the_reference_point_given(monkeypatch):
    monkeypatch.setattr(server, "SERVER_START_MONOTONIC", 1_000.0)
    assert uptime_seconds(now=1_000.0) == 0
    assert uptime_seconds(now=1_007.9) == 7
    assert uptime_seconds(now=1_010.0) == 10


def test_uptime_seconds_never_negative_on_a_clock_jump_back(monkeypatch):
    # the monotonic clock is the reference, an earlier `now` than the start still clamps to zero
    monkeypatch.setattr(server, "SERVER_START_MONOTONIC", 1_000.0)
    assert uptime_seconds(now=900.0) == 0
    assert uptime_seconds(now=999.999) == 0


def test_uptime_seconds_never_decreases(monkeypatch):
    monkeypatch.setattr(server, "SERVER_START_MONOTONIC", time.monotonic() - 5)
    assert uptime_seconds() <= uptime_seconds()


def test_server_serves_uptime_json(base_url):
    status, body = get_json(base_url, "/api/uptime")
    assert status == 200
    assert set(body) == {"uptime_seconds"}
    assert body["uptime_seconds"] >= 0


def test_server_strips_the_query_string_before_matching(base_url):
    # Handler strips the query string (self.path.split("?", 1)[0]) before calling route()
    status, body = get_json(base_url, "/api/uptime?x=1&y=2")
    assert status == 200
    assert set(body) == {"uptime_seconds"}


def test_server_returns_the_reference_uptime(base_url, monkeypatch):
    start = time.monotonic() - 42
    monkeypatch.setattr(server, "SERVER_START_MONOTONIC", start)
    status, body = get_json(base_url, "/api/uptime")
    assert status == 200
    assert set(body) == {"uptime_seconds"}
    value = body["uptime_seconds"]
    assert 42 <= value <= int(time.monotonic() - start)


def test_server_answers_uptime_from_every_worker_thread(base_url):
    # ThreadingHTTPServer: the route is answered from every worker thread, never 404/405
    for _ in range(3):
        status, body = get_json(base_url, "/api/uptime")
        assert status == 200 and body["uptime_seconds"] >= 0


def test_other_routes_are_untouched(base_url):
    assert get_json(base_url, "/healthz") == (200, {"status": "ok"})
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        urllib.request.urlopen(f"{base_url}/nope", timeout=5)
    assert excinfo.value.code == 404
