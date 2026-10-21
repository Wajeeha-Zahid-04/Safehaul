"""Shared HTTP helper for third-party APIs: 10 s timeout, one retry on transient failures."""

from typing import Any

import requests

TIMEOUT_S = 10
ATTEMPTS = 2  # first try + 1 retry
# Public OSM-based services (e.g. Photon) reject generic client user agents.
USER_AGENT = "SafeHaul/1.0 (+https://github.com/Wajeeha-Zahid-04/Safehaul)"


class UpstreamError(Exception):
    """A third-party API failed or returned an unusable response."""


def request_json(
    method: str, url: str, headers: dict[str, str] | None = None, **kwargs: Any
) -> Any:
    headers = {"User-Agent": USER_AGENT, **(headers or {})}
    last_error: Exception | None = None
    for _ in range(ATTEMPTS):
        try:
            response = requests.request(method, url, headers=headers, timeout=TIMEOUT_S, **kwargs)
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_error = exc
            continue
        if response.status_code >= 500:
            last_error = UpstreamError(f"{url} returned {response.status_code}")
            continue
        if not response.ok:
            raise UpstreamError(f"{url} returned {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise UpstreamError(f"{url} returned invalid JSON") from exc
    raise UpstreamError(f"{url} failed after {ATTEMPTS} attempts") from last_error
