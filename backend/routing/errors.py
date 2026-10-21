"""User-facing routing failures (bad trip, not a broken upstream), mapped to HTTP 422."""

import json

from upstream import RateLimitedError, UpstreamError

NOT_FOUND = "No truck route could be found between these places."
TOO_LONG_FALLBACK = (
    "This trip is too long for the free routing service: origin and destination must be "
    "within about 930 miles (1,500 km) in a straight line. Try a shorter trip."
)
TOO_LONG_ORS = "This trip exceeds the routing service's distance limit. Try a shorter trip."

VALHALLA_DISTANCE_LIMIT = 154  # "Path distance exceeds the max distance limit"
ORS_LIMIT_EXCEEDED = 2004  # parameter (e.g. route distance) exceeds the allowed limit
ORS_ROUTE_ERRORS = {2009, 2010}  # route not found / point not routable


class RouteNotFoundError(Exception):
    """The router understood the request but cannot route this trip."""


def _error_code(error: UpstreamError, *path: str) -> int | None:
    try:
        node = json.loads(error.body)
        for key in path:
            node = node[key]
        return int(node)
    except (ValueError, KeyError, TypeError):
        return None


def from_valhalla(error: UpstreamError) -> Exception:
    """Valhalla 4xx -> RouteNotFoundError; anything else (incl. 429) stays an upstream failure."""
    if isinstance(error, RateLimitedError) or error.status is None or not 400 <= error.status < 500:
        return error
    if _error_code(error, "error_code") == VALHALLA_DISTANCE_LIMIT:
        return RouteNotFoundError(TOO_LONG_FALLBACK)
    return RouteNotFoundError(NOT_FOUND)


def from_ors(error: UpstreamError) -> Exception:
    code = _error_code(error, "error", "code")
    if code == ORS_LIMIT_EXCEEDED:
        return RouteNotFoundError(TOO_LONG_ORS)
    if code in ORS_ROUTE_ERRORS:
        return RouteNotFoundError(NOT_FOUND)
    return error
