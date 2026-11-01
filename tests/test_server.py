import json
import re
import threading
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer

import pytest
from dateutil.parser import isoparse

from app import VERSION
from app.server import Handler, route, utc_now_iso8601

ISO_8601_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def parse_iso8601_utc(text: str) -> datetime:
    # dateutil isoparse() accepts the "Z" suffix; the regex above keeps the format strict
    # (isoparse() alone would also accept a space separator).
    parsed = isoparse(text)
    assert parsed.utcoffset() == timedelta(0), text
    return parsed


def assert_recent_utc(text: str) -> None:
    assert ISO_8601_UTC.match(text), text
    parsed = parse_iso8601_utc(text)
    assert abs(parsed - datetime.now(timezone.utc)) < timedelta(seconds=5)


def test_routes():
    assert route("/healthz") == (200, {"status": "ok"})
    assert route("/api/info") == (200, {"app": "agent-demo", "version": VERSION})
    assert route("/nope")[0] == 404


def test_utc_now_iso8601_format():
    assert_recent_utc(utc_now_iso8601())


def test_isoparse_accepts_iso8601_utc_forms():
    expected = datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    assert parse_iso8601_utc("2024-01-02T03:04:05Z") == expected
    assert parse_iso8601_utc("2024-01-02T03:04:05+00:00") == expected


def test_parse_iso8601_utc_rejects_non_utc_offset():
    with pytest.raises(AssertionError):
        parse_iso8601_utc("2024-01-02T03:04:05+02:00")


def test_parse_iso8601_utc_rejects_invalid_input():
    with pytest.raises(ValueError):
        parse_iso8601_utc("not a timestamp")
    with pytest.raises(AssertionError):
        assert_recent_utc("2024-01-02 03:04:05Z")  # a space instead of "T" is not the expected format


def test_time_route():
    status, body = route("/api/time")
    assert status == 200
    assert set(body) == {"time"}
    assert_recent_utc(str(body["time"]))


def test_server_answers_json():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        url = f"http://127.0.0.1:{srv.server_address[1]}/healthz?x=1"
        with urllib.request.urlopen(url, timeout=5) as resp:
            assert resp.status == 200 and json.loads(resp.read()) == {"status": "ok"}
    finally:
        srv.shutdown()
        srv.server_close()


def test_server_serves_time_json():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        url = f"http://127.0.0.1:{srv.server_address[1]}/api/time"
        with urllib.request.urlopen(url, timeout=5) as resp:
            body = json.loads(resp.read())
            assert resp.status == 200
            assert resp.headers["Content-Type"] == "application/json"
            assert set(body) == {"time"}
            assert_recent_utc(body["time"])
    finally:
        srv.shutdown()
        srv.server_close()
