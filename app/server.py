"""HTTP server of agent-demo (standard library only): GET /healthz and GET /api/info."""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import VERSION


def route(path: str) -> tuple[int, dict[str, object]]:
    if path == "/healthz":
        return 200, {"status": "ok"}
    if path == "/api/info":
        return 200, {"app": "agent-demo", "version": VERSION}
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
