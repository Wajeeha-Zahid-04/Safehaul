"""Shared HTTP helper for third-party APIs: 10 s timeout, one retry on transient failures."""

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

TIMEOUT_S = 10
ATTEMPTS = 2  # first try + 1 retry
# Public OSM-based services (e.g. Photon) reject generic client user agents.
USER_AGENT = "SafeHaul/1.0 (+https://github.com/Wajeeha-Zahid-04/Safehaul)"
LOG_BODY_CHARS = 200
KEEP_BODY_CHARS = 1000
TOO_MANY_REQUESTS = 429


class UpstreamError(Exception):
    """A third-party API failed or returned an unusable response."""

    def __init__(self, message: str, status: int | None = None, body: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.body = body


class RateLimitedError(UpstreamError):
    """A third-party API rejected the call with 429 (e.g. Open-Meteo free-tier quota)."""


def _log_failure(url: str, detail: str) -> None:
    # Log host + path only: query strings can carry API keys (ORS geocode uses ?api_key=).
    logger.warning("Upstream %s failed: %s", url.split("?", 1)[0], detail)


def request_json(
    method: str, url: str, headers: dict[str, str] | None = None, **kwargs: Any
) -> Any:
    headers = {"User-Agent": USER_AGENT, **(headers or {})}
    last_error: Exception | None = None
    for _ in range(ATTEMPTS):
        try:
            response = requests.request(method, url, headers=headers, timeout=TIMEOUT_S, **kwargs)
        except (requests.ConnectionError, requests.Timeout) as exc:
            _log_failure(url, type(exc).__name__)
            last_error = exc
            continue
        if not response.ok:
            status, body = response.status_code, response.text[:KEEP_BODY_CHARS]
            _log_failure(url, f"HTTP {status} {body[:LOG_BODY_CHARS]}")
            if status >= 500:
                last_error = UpstreamError(f"{url} returned {status}", status, body)
                continue
            error_class = RateLimitedError if status == TOO_MANY_REQUESTS else UpstreamError
            raise error_class(f"{url} returned {status}", status, body)
        try:
            return response.json()
        except ValueError as exc:
            raise UpstreamError(f"{url} returned invalid JSON") from exc
    raise UpstreamError(f"{url} failed after {ATTEMPTS} attempts") from last_error
