"""JSON GET of agent-demo built on requests (the only third-party dependency of the app)."""

from __future__ import annotations

from typing import Any

import requests

DEFAULT_TIMEOUT_SECONDS = 10.0


def fetch_json(url: str, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> Any:
    """GET url and return the decoded JSON body; a non-2xx response raises requests.HTTPError."""
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return response.json()
