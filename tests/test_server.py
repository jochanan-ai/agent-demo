import json
import re
import threading
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer

import pytest
from dateutil import parser as dateutil_parser
from dateutil import tz as dateutil_tz

from app import VERSION
from app.server import Handler, route, utc_now_iso8601

ISO_8601_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def parse_iso8601_utc(text: str) -> datetime:
    # dateutil's isoparse() accepts the trailing "Z" on every supported Python version.
    return dateutil_parser.isoparse(text)


def assert_recent_utc(text: str) -> None:
    assert ISO_8601_UTC.match(text), text
    parsed = parse_iso8601_utc(text)
    assert parsed.tzinfo == dateutil_tz.UTC
    assert abs(parsed - datetime.now(timezone.utc)) < timedelta(seconds=5)


def test_dateutil_parses_utc_now_as_iso8601():
    text = utc_now_iso8601()
    parsed = dateutil_parser.isoparse(text)
    assert parsed.tzinfo == dateutil_tz.UTC
    assert parsed.utcoffset() == timedelta(0)
    # The canonical form round-trips: the same instant, written the same way.
    assert parsed.isoformat() == text.replace("Z", "+00:00")


def test_dateutil_agrees_with_stdlib_on_a_fixed_timestamp():
    parsed = dateutil_parser.isoparse("2024-01-02T03:04:05Z")
    assert parsed == datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    assert parsed.tzinfo == dateutil_tz.UTC


def test_iso8601_regex_and_dateutil_reject_different_things():
    # The regex checks only the shape, isoparse() checks the calendar, so both are used: shape
    # first, then the parser's agreement that the instant is UTC.
    assert ISO_8601_UTC.match("2024-01-02 03:04:05") is None
    assert dateutil_parser.isoparse("2024-01-02 03:04:05").tzinfo is None
    for wrong_shape in ("02/01/2024", "not a date"):
        assert ISO_8601_UTC.match(wrong_shape) is None
        with pytest.raises(ValueError):
            dateutil_parser.isoparse(wrong_shape)
    # A valid ISO 8601 value that is not in the app's UTC "Z" form.
    assert ISO_8601_UTC.match("2024-01-02T03:04:05+02:00") is None
    assert dateutil_parser.isoparse("2024-01-02T03:04:05+02:00").utcoffset() == timedelta(hours=2)
    # The regex accepts a calendar-invalid month, isoparse() is the one that rejects it.
    assert ISO_8601_UTC.match("2024-13-01T00:00:00Z") is not None
    with pytest.raises(ValueError):
        dateutil_parser.isoparse("2024-13-01T00:00:00Z")


def test_routes():
    assert route("/healthz") == (200, {"status": "ok"})
    assert route("/api/info") == (200, {"app": "agent-demo", "version": VERSION})
    assert route("/nope")[0] == 404


def test_utc_now_iso8601_format():
    assert_recent_utc(utc_now_iso8601())


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
