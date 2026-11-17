"""HTTP server of agent-demo (standard library only): GET /healthz, GET /api/info, GET /api/time,
GET /api/version, GET /api/uptime."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import VERSION

# Uptime reference point: the module is imported when the server process starts (`python -m
# app.server`), so this is the start of the server serving the routes below.
SERVER_START_MONOTONIC = time.monotonic()


def utc_now_iso8601() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def uptime_seconds(now: float | None = None) -> int:
    """Whole seconds since the server started. The monotonic clock is the reference, so a wall
    clock jump (NTP, DST) cannot make the uptime negative."""
    return max(0, int((time.monotonic() if now is None else now) - SERVER_START_MONOTONIC))


def route(path: str) -> tuple[int, dict[str, object]]:
    if path == "/healthz":
        return 200, {"status": "ok"}
    if path == "/api/info":
        return 200, {"app": "agent-demo", "version": VERSION}
    if path == "/api/time":
        return 200, {"time": utc_now_iso8601()}
    if path == "/api/version":
        return 200, {"version": VERSION}
    if path == "/api/uptime":
        return 200, {"uptime_seconds": uptime_seconds()}
    return 404, {"error": "not found"}


class Handler(BaseHTTPRequestHandler):
    server_version = "agent-demo"

    def do_GET(self) -> None:
        status, body = route(self.path.split("?", 1)[0])
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> None:
    port = int(os.environ.get("PORT", "8080"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()  # noqa: S104 (inside the container)


if __name__ == "__main__":
    main()
