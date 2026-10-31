import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

from app import VERSION
from app.server import Handler, route


def test_routes():
    assert route("/healthz") == (200, {"status": "ok"})
    assert route("/api/info") == (200, {"app": "agent-demo", "version": VERSION})
    assert route("/nope")[0] == 404


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
