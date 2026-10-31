import json
import threading
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer

from app import VERSION
from app.server import Handler, route, utc_now_iso8601


def test_routes():
    assert route("/healthz") == (200, {"status": "ok"})
    assert route("/api/info") == (200, {"app": "agent-demo", "version": VERSION})
    assert route("/nope")[0] == 404


def test_utc_now_iso8601_format():
    text = utc_now_iso8601()
    assert text.endswith("Z")
    parsed = datetime.fromisoformat(text)
    assert parsed.tzinfo == timezone.utc
    assert abs(parsed - datetime.now(timezone.utc)) < timedelta(seconds=5)


def test_time_route():
    status, body = route("/api/time")
    assert status == 200
    assert set(body) == {"time"}
    parsed = datetime.fromisoformat(str(body["time"]))
    assert parsed.tzinfo == timezone.utc
    assert abs(parsed - datetime.now(timezone.utc)) < timedelta(seconds=5)


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
        url = f"http://127.0.0.1:{srv.server_address[1]}/api/time?x=1"
        with urllib.request.urlopen(url, timeout=5) as resp:
            body = json.loads(resp.read())
            assert resp.status == 200
            assert resp.headers["Content-Type"] == "application/json"
            assert datetime.fromisoformat(body["time"]).tzinfo == timezone.utc
    finally:
        srv.shutdown()
        srv.server_close()
