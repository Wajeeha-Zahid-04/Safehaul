"""Weather at checkpoint ETAs, with a 30-minute cache keyed by rounded lat/lon + hour (spec §2)."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from django.core.cache import cache

from routing.types import LatLon
from upstream import UpstreamError
from weather.client import fetch_hourly
from weather.types import Weather

CACHE_TTL_S = 30 * 60
COORD_DECIMALS = 2

PointHour = tuple[LatLon, datetime]


def forecast_hour(eta: datetime) -> datetime:
    """ETA rounded to the nearest whole hour in UTC (half past rounds up)."""
    utc = eta.astimezone(UTC)
    hour = utc.replace(minute=0, second=0, microsecond=0)
    return hour + timedelta(hours=1) if utc - hour >= timedelta(minutes=30) else hour


def round_point(point: LatLon) -> LatLon:
    return (round(point[0], COORD_DECIMALS), round(point[1], COORD_DECIMALS))


def cache_key(point: LatLon, hour: datetime) -> str:
    return f"wx:{point[0]:.{COORD_DECIMALS}f}:{point[1]:.{COORD_DECIMALS}f}:{int(hour.timestamp())}"


def weather_at(queries: Sequence[tuple[LatLon, datetime]]) -> list[Weather]:
    """Forecast for each (point, ETA), using one batched Open-Meteo call for all cache misses."""
    wanted: list[PointHour] = [(round_point(p), forecast_hour(eta)) for p, eta in queries]
    keys = [cache_key(point, hour) for point, hour in wanted]
    found: dict[str, Weather] = cache.get_many(keys)

    missing = [ph for ph, key in zip(wanted, keys, strict=True) if key not in found]
    if missing:
        fresh = _fetch(missing)
        cache.set_many(fresh, CACHE_TTL_S)
        found.update(fresh)

    absent = [key for key in keys if key not in found]
    if absent:
        raise UpstreamError(f"Open-Meteo has no forecast for {len(absent)} checkpoint(s)")
    return [found[key] for key in keys]


def _fetch(missing: list[PointHour]) -> dict[str, Weather]:
    points = list(dict.fromkeys(point for point, _ in missing))
    hours = [hour for _, hour in missing]
    forecasts = fetch_hourly(points, min(hours), max(hours))
    return {
        cache_key(point, datetime.fromtimestamp(unix_hour, UTC)): weather
        for point, forecast in zip(points, forecasts, strict=True)
        for unix_hour, weather in forecast.items()
    }
