"""Open-Meteo batched hourly forecast client (spec §2 `weather/`).

One request covers many points via comma-separated latitude/longitude lists. Values are
normalised to mph / inches using the units Open-Meteo reports in `hourly_units`: snowfall in
cm is divided by 2.54, as the spec requires. When `precipitation_unit=inch` is requested,
Open-Meteo already returns snowfall in inches, so it is used as-is rather than divided twice.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from routing.types import LatLon
from upstream import UpstreamError, request_json
from weather.types import Weather

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
HOUR_FORMAT = "%Y-%m-%dT%H:%M"

# Weather field -> Open-Meteo hourly variable.
VARIABLES = {
    "wind_mph": "wind_speed_10m",
    "gust_mph": "wind_gusts_10m",
    "precip_in": "precipitation",
    "rain_in": "rain",
    "snow_in": "snowfall",
}

# Multiplier from the reported unit to mph (speeds) or inches (depths).
UNIT_FACTORS = {
    "mp/h": 1.0,
    "km/h": 1 / 1.609344,
    "inch": 1.0,
    "mm": 1 / 25.4,
    "cm": 1 / 2.54,
}

HourlyForecast = dict[int, Weather]  # unix hour (UTC) -> conditions


def fetch_hourly(
    points: Sequence[LatLon], start_hour: datetime, end_hour: datetime
) -> list[HourlyForecast]:
    """Hourly forecast for each point (same order as `points`), start..end hour inclusive (UTC)."""
    if not points:
        return []
    data = request_json("GET", FORECAST_URL, params=build_params(points, start_hour, end_hour))
    locations = data if isinstance(data, list) else [data]
    if len(locations) != len(points):
        raise UpstreamError(f"Open-Meteo returned {len(locations)} locations for {len(points)}")
    try:
        return [parse_location(location) for location in locations]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise UpstreamError("Open-Meteo returned an unexpected response") from exc


def build_params(
    points: Sequence[LatLon], start_hour: datetime, end_hour: datetime
) -> dict[str, str]:
    return {
        "latitude": ",".join(f"{lat:.2f}" for lat, _ in points),
        "longitude": ",".join(f"{lon:.2f}" for _, lon in points),
        "hourly": ",".join(VARIABLES.values()),
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": "GMT",
        "timeformat": "unixtime",
        "start_hour": start_hour.strftime(HOUR_FORMAT),
        "end_hour": end_hour.strftime(HOUR_FORMAT),
    }


def parse_location(location: dict[str, Any]) -> HourlyForecast:
    hourly, units = location["hourly"], location["hourly_units"]
    factors = {field: _unit_factor(units[var]) for field, var in VARIABLES.items()}
    forecast: HourlyForecast = {}
    for i, unix_hour in enumerate(hourly["time"]):
        values = {field: hourly[var][i] for field, var in VARIABLES.items()}
        if any(value is None for value in values.values()):
            continue  # hour without data; treated as missing by the lookup
        forecast[int(unix_hour)] = Weather(
            **{field: float(value) * factors[field] for field, value in values.items()}
        )
    return forecast


def _unit_factor(unit: str) -> float:
    try:
        return UNIT_FACTORS[unit]
    except KeyError:
        raise UpstreamError(f"Unexpected Open-Meteo unit {unit!r}") from None
