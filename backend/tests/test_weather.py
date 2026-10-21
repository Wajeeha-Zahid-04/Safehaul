from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
import responses

from upstream import UpstreamError
from weather import Weather, forecast_hour, weather_at
from weather.client import FORECAST_URL, build_params, fetch_hourly, parse_location

H14 = datetime(2026, 10, 22, 14, tzinfo=UTC)
INCH_UNITS = {
    "time": "unixtime",
    "wind_speed_10m": "mp/h",
    "wind_gusts_10m": "mp/h",
    "precipitation": "inch",
    "rain": "inch",
    "snowfall": "inch",
}


def location(
    hours: list[datetime],
    wind: float = 10,
    gust: float = 15,
    precip: float = 0.0,
    rain: float = 0.0,
    snow: float = 0.0,
    units: dict[str, str] | None = None,
) -> dict[str, Any]:
    n = len(hours)
    return {
        "hourly_units": units or INCH_UNITS,
        "hourly": {
            "time": [int(h.timestamp()) for h in hours],
            "wind_speed_10m": [wind] * n,
            "wind_gusts_10m": [gust] * n,
            "precipitation": [precip] * n,
            "rain": [rain] * n,
            "snowfall": [snow] * n,
        },
    }


def query_of(call: Any) -> dict[str, list[str]]:
    return parse_qs(urlparse(call.request.url).query)


# --- forecast hour = ETA rounded to the nearest hour ---
@pytest.mark.parametrize(
    ("eta", "expected"),
    [
        (datetime(2026, 10, 22, 14, 0, tzinfo=UTC), H14),
        (datetime(2026, 10, 22, 14, 29, 59, tzinfo=UTC), H14),
        (datetime(2026, 10, 22, 14, 30, tzinfo=UTC), H14 + timedelta(hours=1)),
        (datetime(2026, 10, 22, 13, 30, tzinfo=UTC), H14),
        (datetime(2026, 10, 22, 23, 45, tzinfo=UTC), datetime(2026, 10, 23, 0, tzinfo=UTC)),
        # Non-UTC input is converted: 09:40 at UTC-5 = 14:40 UTC -> 15:00 UTC.
        (
            datetime(2026, 10, 22, 9, 40, tzinfo=timezone(timedelta(hours=-5))),
            H14 + timedelta(hours=1),
        ),
    ],
)
def test_forecast_hour_rounds_to_nearest_hour(eta: datetime, expected: datetime) -> None:
    assert forecast_hour(eta) == expected


# --- request ---
def test_build_params_batches_points_and_requests_spec_units() -> None:
    params = build_params(
        [(41.87812, -87.6298), (42.3314, -83.0458)], H14, H14 + timedelta(hours=3)
    )
    assert params["latitude"] == "41.88,42.33"
    assert params["longitude"] == "-87.63,-83.05"
    assert params["hourly"] == "wind_speed_10m,wind_gusts_10m,precipitation,rain,snowfall"
    assert params["wind_speed_unit"] == "mph"
    assert params["precipitation_unit"] == "inch"
    assert params["start_hour"] == "2026-10-22T14:00"
    assert params["end_hour"] == "2026-10-22T17:00"


# --- unit conversion ---
def test_inch_units_used_as_is() -> None:
    w = parse_location(location([H14], wind=30, gust=40, precip=0.3, rain=0.2, snow=1.5))
    assert w[int(H14.timestamp())] == Weather(30, 40, 0.3, 0.2, 1.5)


def test_snowfall_in_cm_is_divided_by_2_54() -> None:
    units = {**INCH_UNITS, "snowfall": "cm"}
    w = parse_location(location([H14], snow=2.54, units=units))[int(H14.timestamp())]
    assert w.snow_in == pytest.approx(1.0)


def test_metric_rain_and_wind_are_converted() -> None:
    units = {**INCH_UNITS, "precipitation": "mm", "rain": "mm", "wind_speed_10m": "km/h"}
    w = parse_location(location([H14], wind=80.4672, rain=25.4, precip=12.7, units=units))
    weather = w[int(H14.timestamp())]
    assert weather.wind_mph == pytest.approx(50)
    assert weather.rain_in == pytest.approx(1.0)
    assert weather.precip_in == pytest.approx(0.5)


def test_unknown_unit_raises() -> None:
    with pytest.raises(UpstreamError):
        parse_location(location([H14], units={**INCH_UNITS, "snowfall": "furlongs"}))


def test_hours_with_null_values_are_skipped() -> None:
    loc = location([H14, H14 + timedelta(hours=1)])
    loc["hourly"]["rain"][1] = None
    assert list(parse_location(loc)) == [int(H14.timestamp())]


# --- batched client ---
@responses.activate
def test_fetch_hourly_parses_one_location_per_point_in_order() -> None:
    responses.get(FORECAST_URL, json=[location([H14], wind=5), location([H14], wind=50)])
    result = fetch_hourly([(41.0, -87.0), (42.0, -83.0)], H14, H14)
    assert [f[int(H14.timestamp())].wind_mph for f in result] == [5, 50]
    assert len(responses.calls) == 1


@responses.activate
def test_fetch_hourly_accepts_single_object_for_one_point() -> None:
    responses.get(FORECAST_URL, json=location([H14], wind=7))
    assert fetch_hourly([(41.0, -87.0)], H14, H14)[0][int(H14.timestamp())].wind_mph == 7


@responses.activate
def test_fetch_hourly_location_count_mismatch_raises() -> None:
    responses.get(FORECAST_URL, json=[location([H14])])
    with pytest.raises(UpstreamError):
        fetch_hourly([(41.0, -87.0), (42.0, -83.0)], H14, H14)


@responses.activate
def test_fetch_hourly_malformed_payload_raises() -> None:
    responses.get(FORECAST_URL, json={"error": True, "reason": "bad"})
    with pytest.raises(UpstreamError):
        fetch_hourly([(41.0, -87.0)], H14, H14)


def test_fetch_hourly_no_points_makes_no_call() -> None:
    assert fetch_hourly([], H14, H14) == []


# --- weather_at: ETA lookup, batching, caching ---
@responses.activate
def test_weather_at_uses_one_batched_call_and_picks_eta_hour() -> None:
    h15, h16 = H14 + timedelta(hours=1), H14 + timedelta(hours=2)
    first = location([H14, h15, h16])
    first["hourly"]["wind_speed_10m"] = [10, 20, 30]
    second = location([H14, h15, h16])
    second["hourly"]["wind_speed_10m"] = [40, 50, 60]
    responses.get(FORECAST_URL, json=[first, second])

    result = weather_at(
        [
            ((41.0, -87.0), H14 + timedelta(minutes=10)),  # -> 14:00
            ((42.0, -83.0), H14 + timedelta(minutes=95)),  # 15:35 -> 16:00
        ]
    )

    assert [w.wind_mph for w in result] == [10, 60]
    assert len(responses.calls) == 1
    query = query_of(responses.calls[0])
    assert query["start_hour"] == ["2026-10-22T14:00"]
    assert query["end_hour"] == ["2026-10-22T16:00"]


@responses.activate
def test_weather_at_dedupes_points_that_round_to_same_key() -> None:
    responses.get(FORECAST_URL, json=location([H14], wind=12))
    result = weather_at([((41.001, -87.001), H14), ((41.004, -86.996), H14)])
    assert [w.wind_mph for w in result] == [12, 12]
    assert query_of(responses.calls[0])["latitude"] == ["41.00"]


@responses.activate
def test_weather_at_serves_repeat_lookups_from_cache() -> None:
    responses.get(FORECAST_URL, json=location([H14], wind=12))
    weather_at([((41.0, -87.0), H14)])
    weather_at([((41.0, -87.0), H14 + timedelta(minutes=20))])  # same rounded hour
    assert len(responses.calls) == 1


@responses.activate
def test_weather_at_only_fetches_cache_misses() -> None:
    responses.get(FORECAST_URL, json=location([H14], wind=12))
    weather_at([((41.0, -87.0), H14)])
    responses.get(FORECAST_URL, json=location([H14], wind=33))
    result = weather_at([((41.0, -87.0), H14), ((45.0, -90.0), H14)])
    assert [w.wind_mph for w in result] == [12, 33]
    assert query_of(responses.calls[1])["latitude"] == ["45.00"]


@responses.activate
def test_weather_at_missing_hour_raises() -> None:
    responses.get(FORECAST_URL, json=location([H14]))
    with pytest.raises(UpstreamError):
        weather_at([((41.0, -87.0), H14 + timedelta(hours=5))])
