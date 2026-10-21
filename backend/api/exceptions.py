"""Maps domain/upstream failures to HTTP responses for every API view (no stack traces leak)."""

from typing import Any

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

from routing.errors import RouteNotFoundError
from upstream import RateLimitedError, UpstreamError

UPSTREAM_ERROR = "Upstream service unavailable. Please try again."
RATE_LIMITED = "Weather or routing service is busy (free-tier rate limit). Retry in a minute."
RETRY_AFTER_S = "60"


def handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    if isinstance(exc, RouteNotFoundError):
        return Response({"detail": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
    if isinstance(exc, RateLimitedError):
        return Response(
            {"detail": RATE_LIMITED},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
            headers={"Retry-After": RETRY_AFTER_S},
        )
    if isinstance(exc, UpstreamError):
        return Response({"detail": UPSTREAM_ERROR}, status=status.HTTP_502_BAD_GATEWAY)
    return exception_handler(exc, context)
