import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests

from app.http_client import DEFAULT_TIMEOUT_SECONDS, fetch_json

RESPONSES: dict[str, tuple[int, bytes, str]] = {}
STUB = {"sleep": 0.0}


class StubHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
        if STUB["sleep"]:
            time.sleep(STUB["sleep"])
        status, body, content_type = RESPONSES.get(self.path, (404, b'{"error": "not found"}', "application/json"))
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


@pytest.fixture
def base_url():
    RESPONSES.clear()
    STUB["sleep"] = 0.0
    srv = ThreadingHTTPServer(("127.0.0.1", 0), StubHandler)
    srv.daemon_threads = True
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}"
    finally:
        srv.shutdown()
        srv.server_close()
        RESPONSES.clear()
        STUB["sleep"] = 0.0


def test_fetch_json_decodes_the_json_body(base_url):
    RESPONSES["/api/info"] = (200, json.dumps({"app": "agent-demo"}).encode(), "application/json")
    assert fetch_json(f"{base_url}/api/info") == {"app": "agent-demo"}


def test_fetch_json_accepts_any_json_document(base_url):
    RESPONSES["/api/time"] = (200, b'["time", 1]', "application/json")
    assert fetch_json(f"{base_url}/api/time") == ["time", 1]


def test_fetch_json_raises_on_http_error(base_url):
    with pytest.raises(requests.HTTPError) as excinfo:
        fetch_json(f"{base_url}/nope")
    assert excinfo.value.response.status_code == 404


def test_fetch_json_raises_on_a_server_error(base_url):
    RESPONSES["/api/boom"] = (500, b"boom", "text/plain")
    with pytest.raises(requests.HTTPError) as excinfo:
        fetch_json(f"{base_url}/api/boom")
    assert excinfo.value.response.status_code == 500


def test_fetch_json_raises_on_a_body_that_is_not_json(base_url):
    RESPONSES["/api/html"] = (200, b"<html>nope</html>", "text/html")
    with pytest.raises(requests.exceptions.JSONDecodeError):
        fetch_json(f"{base_url}/api/html")


def test_fetch_json_times_out(base_url):
    STUB["sleep"] = 1.0
    RESPONSES["/api/slow"] = (200, b"{}", "application/json")
    with pytest.raises(requests.exceptions.Timeout):
        fetch_json(f"{base_url}/api/slow", timeout=0.2)


def test_default_timeout_is_finite():
    assert 0 < DEFAULT_TIMEOUT_SECONDS <= 60
