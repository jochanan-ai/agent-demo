"""Local static server for the one-page site: `python -m site_serve` (or `make run`).

The page itself needs no server — opening index.html in a browser works. This module only gives a
convenience URL (http://127.0.0.1:8080/) with the correct MIME types, and it serves nothing but
the files of this directory.
"""

from __future__ import annotations

import argparse
import os
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DEFAULT_PORT = 8080
HOST = "127.0.0.1"
ROOT = Path(__file__).resolve().parent


def is_served(target: Path) -> bool:
    """True when target stays inside ROOT (no traversal above the served directory)."""
    resolved = target.resolve()
    return resolved == ROOT or ROOT in resolved.parents


def resolve_request_target(url_path: str) -> Path | None:
    """File a request path maps to, or None when it escapes ROOT."""
    clean = url_path.split("?", 1)[0].split("#", 1)[0]
    decoded = urllib.parse.unquote(urllib.parse.unquote(clean))
    candidate = (ROOT / decoded.lstrip("/")).resolve()
    return candidate if is_served(candidate) else None


class Handler(SimpleHTTPRequestHandler):
    server_version = "personal-site"

    def __init__(self, *args, **kwargs) -> None:
        kwargs["directory"] = str(ROOT)
        super().__init__(*args, **kwargs)

    def _guard(self) -> bool:
        if resolve_request_target(self.path) is None:
            self.send_error(404, "not found")
            return False
        return True

    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
        if self._guard():
            super().do_GET()

    def do_HEAD(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
        if self._guard():
            super().do_HEAD()

    def log_message(self, format: str, *args: object) -> None:
        return


def build_server(host: str = HOST, port: int = DEFAULT_PORT) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), Handler)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve the static site from this directory.")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", DEFAULT_PORT)),
        help="TCP port to listen on (default: %(default)s)",
    )
    parser.add_argument("--host", default=HOST, help="address to bind (default: %(default)s)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    server = build_server(args.host, args.port)
    print(f"serving {ROOT} on http://{args.host}:{server.server_address[1]}/")  # noqa: T201
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
