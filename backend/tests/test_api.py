import math
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from api import planner, views
from checkpoints.geo import EARTH_RADIUS_MI
from routing import Place
from routing.types import LatLon, Route, Step
from upstream import UpstreamError
from weather import Weather

MI_PER_DEG_LAT = EARTH_RADIUS_MI * math.pi / 180
RISKY_LON, SAFE_LON = 0.0, 0.5


def meridian_route(route_id: int, lon: float, total_mi: float, duration_s: float) -> Route:
    coords = tuple((m / MI_PER_DEG_LAT, lon) for m in range(0, int(total_mi) + 1, 5))
    return Route(
        route_id,
        total_mi * 1609.344,
        duration_s,
        coords,
        (Step(0, len(coords) - 1, 0, duration_s),),
    )


ROUTES = [
    meridian_route(0, RISKY_LON, 60, 3600),  # faster, but windy
    meridian_route(1, SAFE_LON, 60, 3600 + 12 * 60),  # 12 min slower, calm
]


def fake_weather(queries: Sequence[tuple[LatLon, datetime]]) -> list[Weather]:
    def at(lon: float) -> Weather:
        wind = 48.0 if abs(lon - RISKY_LON) < 0.25 else 5.0
        return Weather(wind_mph=wind, gust_mph=wind + 10, precip_in=0, rain_in=0, snow_in=0)

    return [at(lon) for (_, lon), _ in queries]


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.fixture
def fake_upstreams(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    calls = {"routes": 0, "weather": 0}

    def routes(*_: Any) -> list[Route]:
        calls["routes"] += 1
        return ROUTES

    def weather(queries: Sequence[tuple[LatLon, datetime]]) -> list[Weather]:
        calls["weather"] += 1
        return fake_weather(queries)

    monkeypatch.setattr(planner, "get_routes", routes)
    monkeypatch.setattr(planner, "weather_at", weather)
    return calls


def plan_body(**overrides: Any) -> dict[str, Any]:
    body = {
        "origin": {"label": "Start", "lat": 0.0, "lon": 0.0},
        "destination": {"label": "End", "lat": 0.87, "lon": 0.0},
        "departure": (timezone.now() + timedelta(hours=1)).isoformat(),
        "load_lb": 20_000,
        "interval_mi": 25,
    }
    return {**body, **overrides}


def post_plan(client: APIClient, body: dict[str, Any]) -> Any:
    return client.post("/api/plan", body, format="json")


# --- POST /api/plan: happy path ---
@pytest.mark.usefixtures("fake_upstreams")
def test_plan_recommends_the_calm_route_with_reason(client: APIClient) -> None:
    res = post_plan(client, plan_body())
    assert res.status_code == 200
    data = res.json()
    assert data["recommended_id"] == 1
    assert data["recommendation_reason"] == "0 severe mi vs 60, 12 min slower"
    assert data["all_no_travel"] is False
    assert [r["id"] for r in data["routes"]] == [1, 0]
    assert [r["rank"] for r in data["routes"]] == [0, 1]


@pytest.mark.usefixtures("fake_upstreams")
def test_plan_route_and_checkpoint_shape(client: APIClient) -> None:
    risky = next(r for r in post_plan(client, plan_body()).json()["routes"] if r["id"] == 0)
    assert risky["distance_mi"] == pytest.approx(60, abs=0.1)
    assert risky["severe_mi"] == pytest.approx(60, abs=0.1)
    assert risky["avg_score"] == 3
    assert risky["do_not_travel"] is False
    assert len(risky["bbox"]) == 4

    cps = risky["checkpoints"]
    assert [cp["distance_mi"] for cp in cps] == [25, 50, 60]
    first = cps[0]
    assert first["level"] == 3
    assert first["level_label"] == "Severe"
    assert first["reasons"] == ["Wind 48 mph ≥ 45 → Severe"]
    assert first["gust_mph"] == 58
    assert first["path"][0] == [0.0, 0.0]  # GeoJSON [lon, lat], starts at origin
    assert first["path"][-1] == [first["lon"], first["lat"]]
    assert cps[1]["path"][0] == first["path"][-1]  # segments are contiguous
    assert datetime.fromisoformat(first["eta"]) < datetime.fromisoformat(cps[-1]["eta"])


def test_plan_heavy_load_triggers_override_and_no_travel_flag(
    client: APIClient, fake_upstreams: dict[str, int]
) -> None:
    data = post_plan(client, plan_body(load_lb=35_000)).json()
    risky = next(r for r in data["routes"] if r["id"] == 0)
    assert risky["do_not_travel"] is True
    assert risky["checkpoints"][0]["level_label"] == "No Travel"
    assert data["recommended_id"] == 1


def test_plan_fetches_weather_once_per_route(
    client: APIClient, fake_upstreams: dict[str, int]
) -> None:
    post_plan(client, plan_body())
    assert fake_upstreams == {"routes": 1, "weather": len(ROUTES)}


def test_plan_all_routes_no_travel(client: APIClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(planner, "get_routes", lambda *_: ROUTES)
    monkeypatch.setattr(planner, "weather_at", lambda q: [Weather(60, 70, 0, 0, 0) for _ in q])
    data = post_plan(client, plan_body()).json()
    assert data["all_no_travel"] is True
    assert data["recommendation_reason"].startswith("Do not travel")


# --- POST /api/plan: validation ---
@pytest.mark.parametrize(
    "overrides",
    [
        {"load_lb": -1},
        {"load_lb": 120_001},
        {"interval_mi": 15},
        {"interval_mi": "abc"},
        {"departure": (timezone.now() - timedelta(hours=1)).isoformat()},
        {"departure": (timezone.now() + timedelta(hours=48, minutes=5)).isoformat()},
        {"departure": "not-a-date"},
        {"origin": {"label": "x" * 201, "lat": 0, "lon": 0}},
        {"origin": {"label": "Start", "lat": 91, "lon": 0}},
        {"destination": {"label": "End", "lat": 0, "lon": 181}},
        {"destination": {"label": "Same", "lat": 0.0, "lon": 0.0}},
        {"origin": "Chicago"},
    ],
)
@pytest.mark.usefixtures("fake_upstreams")
def test_plan_rejects_invalid_input(client: APIClient, overrides: dict[str, Any]) -> None:
    assert post_plan(client, plan_body(**overrides)).status_code == 400


@pytest.mark.parametrize(
    "overrides",
    [
        {"load_lb": 0},
        {"load_lb": 120_000},
        {"interval_mi": 10},
        {"interval_mi": 50},
        {"departure": (timezone.now() + timedelta(hours=47, minutes=59)).isoformat()},
        {"departure": (timezone.now() - timedelta(minutes=2)).isoformat()},  # grace window
        {"origin": {"label": "x" * 200, "lat": 0, "lon": 0}},
    ],
)
@pytest.mark.usefixtures("fake_upstreams")
def test_plan_accepts_boundary_values(client: APIClient, overrides: dict[str, Any]) -> None:
    assert post_plan(client, plan_body(**overrides)).status_code == 200


def test_plan_requires_all_fields(client: APIClient) -> None:
    res = client.post("/api/plan", {}, format="json")
    assert res.status_code == 400
    assert set(res.json()) == {"origin", "destination", "departure", "load_lb", "interval_mi"}


def test_plan_rejects_get(client: APIClient) -> None:
    assert client.get("/api/plan").status_code == 405


# --- errors ---
def test_plan_upstream_failure_is_generic_502(
    client: APIClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_: Any) -> None:
        raise UpstreamError("https://secret-upstream/ returned 500 key=abc")

    monkeypatch.setattr(planner, "get_routes", boom)
    res = post_plan(client, plan_body())
    assert res.status_code == 502
    assert res.json() == {"detail": "Upstream service unavailable. Please try again."}


# --- throttling ---
def test_plan_is_throttled_at_30_per_minute_per_ip(client: APIClient) -> None:
    statuses = [client.post("/api/plan", {}, format="json").status_code for _ in range(31)]
    assert statuses[:30] == [400] * 30
    assert statuses[30] == 429


def test_throttle_is_per_ip(client: APIClient) -> None:
    for _ in range(30):
        client.post("/api/plan", {}, format="json", REMOTE_ADDR="10.0.0.1")
    assert client.post("/api/plan", {}, format="json", REMOTE_ADDR="10.0.0.1").status_code == 429
    assert client.post("/api/plan", {}, format="json", REMOTE_ADDR="10.0.0.2").status_code == 400


# --- GET /api/geocode ---
def test_geocode_returns_results(client: APIClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(views, "geocode", lambda q: [Place(f"{q}, IL", 41.88, -87.63)])
    res = client.get("/api/geocode", {"q": "Chicago"})
    assert res.status_code == 200
    assert res.json() == {"results": [{"label": "Chicago, IL", "lat": 41.88, "lon": -87.63}]}


@pytest.mark.parametrize("params", [{}, {"q": ""}, {"q": "x" * 201}])
def test_geocode_validates_query(client: APIClient, params: dict[str, str]) -> None:
    assert client.get("/api/geocode", params).status_code == 400


def test_geocode_upstream_failure_is_502(
    client: APIClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(_: str) -> None:
        raise UpstreamError("down")

    monkeypatch.setattr(views, "geocode", boom)
    assert client.get("/api/geocode", {"q": "Chicago"}).status_code == 502
