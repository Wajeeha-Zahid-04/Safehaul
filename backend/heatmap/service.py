"""Corridor heatmap: risk score per grid point per hour for 0-48 h (spec §2 `heatmap/`)."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Any

from django.core.cache import cache

from heatmap.grid import BBox, build_grid
from risk import classify
from routing.types import LatLon
from weather.client import HourlyForecast, fetch_hourly
from weather.service import forecast_hour

HOURS = 49  # 0..48 inclusive
CHUNK_SIZE = 100  # points per Open-Meteo request, keeps the GET URL short
CACHE_TTL_S = 30 * 60
BBOX_KEY_DECIMALS = 2

Scores = list[list[int | None]]  # scores[hour][point]; None = no forecast for that hour


def build_heatmap(bbox: BBox, start: datetime, load_lb: float) -> dict[str, Any]:
    start_hour = forecast_hour(start)
    key = _cache_key(bbox, start_hour, load_lb)
    cached: dict[str, Any] | None = cache.get(key)
    if cached is not None:
        return cached

    grid = build_grid(bbox)
    hours = [start_hour + timedelta(hours=h) for h in range(HOURS)]
    forecasts = _fetch_all(grid.points, hours[0], hours[-1])
    result = {
        "start": start_hour.isoformat(),
        "hours": HOURS,
        "spacing_km": round(grid.spacing_km, 1),
        "points": [[lat, lon] for lat, lon in grid.points],
        "scores": score_grid(forecasts, hours, load_lb),
    }
    cache.set(key, result, CACHE_TTL_S)
    return result


def score_grid(forecasts: list[HourlyForecast], hours: list[datetime], load_lb: float) -> Scores:
    scores: Scores = []
    for hour in hours:
        unix_hour = int(hour.timestamp())
        row: list[int | None] = []
        for forecast in forecasts:
            wx = forecast.get(unix_hour)
            row.append(
                None
                if wx is None
                else int(classify(wx.wind_mph, wx.rain_in, wx.snow_in, load_lb)[0])
            )
        scores.append(row)
    return scores


def _fetch_all(points: list[LatLon], start: datetime, end: datetime) -> list[HourlyForecast]:
    chunks = [points[i : i + CHUNK_SIZE] for i in range(0, len(points), CHUNK_SIZE)]
    with ThreadPoolExecutor(max_workers=len(chunks)) as pool:
        results = list(pool.map(lambda chunk: fetch_hourly(chunk, start, end), chunks))
    return [forecast for chunk_result in results for forecast in chunk_result]


def _cache_key(bbox: BBox, start_hour: datetime, load_lb: float) -> str:
    edges = ",".join(
        f"{v:.{BBOX_KEY_DECIMALS}f}"
        for v in (bbox.min_lon, bbox.min_lat, bbox.max_lon, bbox.max_lat)
    )
    return f"heatmap:{edges}:{int(start_hour.astimezone(UTC).timestamp())}:{load_lb:g}"
