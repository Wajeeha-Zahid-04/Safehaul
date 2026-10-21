import json
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
import responses
from django.utils import timezone
from rest_framework.test import APIClient

from checkpoints.geo import haversine_mi
from heatmap import BBox, build_grid, build_heatmap
from heatmap.grid import BUFFER_KM, KM_PER_DEG_LAT, MAX_POINTS, TARGET_SPACING_KM
from heatmap.service import HOURS, score_grid
from weather import Weather
from weather.client import FORECAST_URL

KM_PER_MI = 1.609344
SMALL = BBox(min_lon=-87.7, min_lat=41.8, max_lon=-87.5, max_lat=41.9)  # ~17 x 11 km
CHICAGO_DENVER = BBox(min_lon=-105.0, min_lat=39.7, max_lon=-87.6, max_lat=41.9)
H0 = datetime(2026, 10, 22, 14, tzinfo=UTC)


def km_between(a: tuple[float, float], b: tuple[float, float]) -> float:
    return haversine_mi(a, b) * KM_PER_MI


# --- grid ---
def test_small_bbox_uses_target_spacing_and_buffer() -> None:
    grid = build_grid(SMALL)
    assert grid.spacing_km == TARGET_SPACING_KM
    lats = sorted({lat for lat, _ in grid.points})
    lons = sorted({lon for _, lon in grid.points})
    assert len(grid.points) == len(lats) * len(lons)
    buffer_deg = BUFFER_KM / KM_PER_DEG_LAT
    assert lats[0] == pytest.approx(SMALL.min_lat - buffer_deg, abs=1e-3)
    assert lats[-1] == pytest.approx(SMALL.max_lat + buffer_deg, abs=1e-3)
    # Neighbouring points are "about 15 km" apart (never closer than the target).
    gap_km = km_between((lats[0], lons[0]), (lats[1], lons[0]))
    assert TARGET_SPACING_KM <= gap_km < TARGET_SPACING_KM * 1.5
    east_km = km_between((lats[0], lons[0]), (lats[0], lons[1]))
    assert TARGET_SPACING_KM * 0.95 <= east_km < TARGET_SPACING_KM * 1.5


def test_degenerate_bbox_still_gets_buffered_grid() -> None:
    grid = build_grid(BBox(-87.6, 41.8, -87.6, 41.8))
    assert len(grid.points) == 16  # 50 km square at 15 km -> 4 x 4


@pytest.mark.parametrize(
    "bbox",
    [
        CHICAGO_DENVER,
        BBox(-125.0, 24.0, -66.0, 49.0),  # contiguous US
        BBox(-80.0, 25.0, -79.0, 47.0),  # tall and thin
        BBox(-124.0, 40.0, -70.0, 40.5),  # wide and flat
    ],
)
def test_large_bbox_is_capped_at_400_points_by_widening_spacing(bbox: BBox) -> None:
    grid = build_grid(bbox)
    assert len(grid.points) <= MAX_POINTS
    assert len(grid.points) >= MAX_POINTS * 0.7  # cap is used, not wasted
    assert grid.spacing_km > TARGET_SPACING_KM


def test_grid_is_clamped_to_valid_coordinates() -> None:
    grid = build_grid(BBox(179.9, 89.9, 180.0, 90.0))
    assert all(-90 <= lat <= 90 and -180 <= lon <= 180 for lat, lon in grid.points)


# --- scoring ---
def test_score_grid_is_hour_major_and_applies_load_overrides() -> None:
    h1 = H0 + timedelta(hours=1)
    windy = Weather(wind_mph=48, gust_mph=60, precip_in=0, rain_in=0, snow_in=0)
    calm = Weather(wind_mph=5, gust_mph=8, precip_in=0, rain_in=0, snow_in=0)
    forecasts = [
        {int(H0.timestamp()): windy, int(h1.timestamp()): calm},
        {int(H0.timestamp()): calm},  # no data for h1
    ]
    assert score_grid(forecasts, [H0, h1], load_lb=0) == [[3, 0], [0, None]]
    assert score_grid(forecasts, [H0, h1], load_lb=35_000) == [[4, 0], [0, None]]


# --- build_heatmap with mocked Open-Meteo ---
def open_meteo_callback(request: Any) -> tuple[int, dict[str, str], str]:
    """Answer any batched request with one location per requested point, 49 hourly values."""
    query = parse_qs(urlparse(request.url).query)
    lats = query["latitude"][0].split(",")
    start = datetime.strptime(query["start_hour"][0], "%Y-%m-%dT%H:%M").replace(tzinfo=UTC)
    end = datetime.strptime(query["end_hour"][0], "%Y-%m-%dT%H:%M").replace(tzinfo=UTC)
    n = int((end - start).total_seconds() // 3600) + 1
    times = [int((start + timedelta(hours=h)).timestamp()) for h in range(n)]
    units = {
        "wind_speed_10m": "mp/h",
        "wind_gusts_10m": "mp/h",
        "precipitation": "inch",
        "rain": "inch",
        "snowfall": "inch",
    }
    body = [
        {
            "hourly_units": units,
            "hourly": {
                "time": times,
                "wind_speed_10m": [30.0] * n,  # Moderate
                "wind_gusts_10m": [40.0] * n,
                "precipitation": [0.0] * n,
                "rain": [0.0] * n,
                "snowfall": [0.0] * n,
            },
        }
        for _ in lats
    ]
    return 200, {}, json.dumps(body if len(body) > 1 else body[0])


@responses.activate
def test_build_heatmap_shape_chunks_and_caches() -> None:
    responses.add_callback(responses.GET, FORECAST_URL, callback=open_meteo_callback)
    start = H0 + timedelta(minutes=40)  # rounds to 15:00

    result = build_heatmap(CHICAGO_DENVER, start, load_lb=0)

    n_points = len(result["points"])
    assert result["hours"] == HOURS == 49
    assert result["start"] == "2026-10-22T15:00:00+00:00"
    assert len(result["scores"]) == 49
    assert all(len(row) == n_points for row in result["scores"])
    assert {score for row in result["scores"] for score in row} == {1}
    # >100 points -> split into chunks of 100, all fetched for the 0-48 h window.
    assert len(responses.calls) == -(-n_points // 100)
    query = parse_qs(urlparse(responses.calls[0].request.url).query)
    assert query["start_hour"] == ["2026-10-22T15:00"]
    assert query["end_hour"] == ["2026-10-24T15:00"]

    calls = len(responses.calls)
    build_heatmap(CHICAGO_DENVER, start, load_lb=0)
    assert len(responses.calls) == calls  # served from cache


# --- POST /api/heatmap ---
def heatmap_body(**overrides: Any) -> dict[str, Any]:
    body = {
        "bbox": [SMALL.min_lon, SMALL.min_lat, SMALL.max_lon, SMALL.max_lat],
        "start": (timezone.now() + timedelta(minutes=10)).isoformat(),
    }
    return {**body, **overrides}


@responses.activate
def test_heatmap_endpoint_returns_compact_arrays() -> None:
    responses.add_callback(responses.GET, FORECAST_URL, callback=open_meteo_callback)
    res = APIClient().post("/api/heatmap", heatmap_body(), format="json")
    assert res.status_code == 200
    data = res.json()
    assert set(data) == {"start", "hours", "spacing_km", "points", "scores"}
    assert data["hours"] == 49
    assert len(data["points"][0]) == 2


@pytest.mark.parametrize(
    "overrides",
    [
        {"bbox": [1, 2, 3]},
        {"bbox": [1, 2, 3, 4, 5]},
        {"bbox": [-87.5, 41.8, -87.7, 41.9]},  # min_lon > max_lon
        {"bbox": [-87.7, 41.9, -87.5, 41.8]},  # min_lat > max_lat
        {"bbox": [-181, 41.8, -87.5, 41.9]},
        {"bbox": [-87.7, 41.8, -87.5, 91]},
        {"start": (timezone.now() - timedelta(hours=1)).isoformat()},
        {"start": (timezone.now() + timedelta(hours=49)).isoformat()},
        {"load_lb": 120_001},
        {"load_lb": -5},
    ],
)
def test_heatmap_rejects_invalid_input(overrides: dict[str, Any]) -> None:
    assert (
        APIClient().post("/api/heatmap", heatmap_body(**overrides), format="json").status_code
        == 400
    )


def test_heatmap_load_is_optional_and_forwarded(monkeypatch: pytest.MonkeyPatch) -> None:
    from api import views

    seen: list[float] = []
    monkeypatch.setattr(views, "build_heatmap", lambda bbox, start, load: seen.append(load) or {})
    client = APIClient()
    assert client.post("/api/heatmap", heatmap_body(), format="json").status_code == 200
    assert (
        client.post("/api/heatmap", heatmap_body(load_lb=35_000), format="json").status_code == 200
    )
    assert seen == [0, 35_000]


@responses.activate
def test_heatmap_upstream_failure_is_generic_502() -> None:
    responses.get(FORECAST_URL, status=500)
    res = APIClient().post("/api/heatmap", heatmap_body(), format="json")
    assert res.status_code == 502
    assert "detail" in res.json()


def test_heatmap_is_throttled_at_30_per_minute() -> None:
    client = APIClient()
    statuses = [client.post("/api/heatmap", {}, format="json").status_code for _ in range(31)]
    assert statuses[:30] == [400] * 30
    assert statuses[30] == 429
