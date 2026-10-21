from datetime import UTC, datetime
from typing import Any

import pytest
import responses
from rest_framework.test import APIClient

from api import planner, views
from routing import ors, valhalla
from routing.errors import NOT_FOUND, TOO_LONG_FALLBACK, TOO_LONG_ORS, RouteNotFoundError
from upstream import ATTEMPTS, RateLimitedError, UpstreamError
from weather.client import FORECAST_URL, fetch_hourly
from weather.service import forecast_hour

from .test_api import plan_body
from .test_heatmap import heatmap_body

A, B = (39.73, -121.84), (39.77, -86.16)


# --- upstream: 429 is its own error and is not retried ---
@responses.activate
def test_429_raises_rate_limited_without_retry() -> None:
    responses.get(FORECAST_URL, status=429, json={"error": True, "reason": "Minutely limit"})
    hour = forecast_hour(datetime.now(UTC))
    with pytest.raises(RateLimitedError):
        fetch_hourly([(41.0, -87.0)], hour, hour)
    assert len(responses.calls) == 1 < ATTEMPTS


@responses.activate
def test_upstream_error_keeps_status_and_body() -> None:
    responses.post(valhalla.ROUTE_URL, status=500, body="boom")
    with pytest.raises(UpstreamError) as info:
        valhalla.directions(A, B, 0)
    assert not isinstance(info.value, RouteNotFoundError)


# --- Valhalla 4xx -> RouteNotFoundError ---
@responses.activate
def test_valhalla_distance_limit_becomes_too_long() -> None:
    responses.post(
        valhalla.ROUTE_URL,
        status=400,
        json={
            "error_code": 154,
            "error": "Path distance exceeds the max distance limit: 1500000 meters",
        },
    )
    with pytest.raises(RouteNotFoundError, match="too long"):
        valhalla.directions(A, B, 40_000)


@responses.activate
def test_valhalla_other_4xx_becomes_not_found() -> None:
    responses.post(
        valhalla.ROUTE_URL, status=400, json={"error_code": 442, "error": "No path could be found"}
    )
    with pytest.raises(RouteNotFoundError) as info:
        valhalla.directions(A, B, 40_000)
    assert str(info.value) == NOT_FOUND


@responses.activate
def test_valhalla_429_stays_rate_limited_not_route_error() -> None:
    responses.post(valhalla.ROUTE_URL, status=429, json={"error": "slow down"})
    with pytest.raises(RateLimitedError):
        valhalla.directions(A, B, 40_000)


# --- ORS error codes ---
@pytest.mark.parametrize(
    ("code", "message"),
    [(2004, TOO_LONG_ORS), (2009, NOT_FOUND), (2010, NOT_FOUND)],
)
@responses.activate
def test_ors_route_error_codes(code: int, message: str) -> None:
    responses.post(ors.DIRECTIONS_URL, status=404, json={"error": {"code": code, "message": "x"}})
    with pytest.raises(RouteNotFoundError) as info:
        ors.directions(A, B, 40_000, "k")
    assert str(info.value) == message


@responses.activate
def test_ors_unknown_4xx_stays_upstream_error() -> None:
    responses.post(
        ors.DIRECTIONS_URL, status=403, json={"error": "Access to this API has been disallowed"}
    )
    with pytest.raises(UpstreamError) as info:
        ors.directions(A, B, 40_000, "k")
    assert not isinstance(info.value, RouteNotFoundError)


# --- HTTP mapping via api.exceptions.handler ---
def _raise(exc: Exception) -> Any:
    def boom(*_: Any) -> None:
        raise exc

    return boom


def test_plan_route_not_found_is_422_with_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(planner, "get_routes", _raise(RouteNotFoundError(TOO_LONG_FALLBACK)))
    res = APIClient().post("/api/plan", plan_body(), format="json")
    assert res.status_code == 422
    assert res.json() == {"detail": TOO_LONG_FALLBACK}


def test_plan_rate_limited_is_503_with_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(planner, "get_routes", _raise(RateLimitedError("x", 429)))
    res = APIClient().post("/api/plan", plan_body(), format="json")
    assert res.status_code == 503
    assert res["Retry-After"] == "60"
    assert "busy" in res.json()["detail"]


@responses.activate
def test_heatmap_rate_limited_is_503() -> None:
    responses.get(FORECAST_URL, status=429, json={"error": True, "reason": "Minutely limit"})
    res = APIClient().post("/api/heatmap", heatmap_body(), format="json")
    assert res.status_code == 503
    assert res["Retry-After"] == "60"


def test_geocode_rate_limited_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(views, "geocode", _raise(RateLimitedError("x", 429)))
    assert APIClient().get("/api/geocode", {"q": "Chicago"}).status_code == 503


def test_validation_errors_still_use_drf_default() -> None:
    res = APIClient().post("/api/plan", {}, format="json")
    assert res.status_code == 400
    assert "origin" in res.json()
