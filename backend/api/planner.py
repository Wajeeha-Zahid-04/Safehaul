"""Trip planning pipeline: routes -> checkpoints -> weather at ETA -> risk -> stats -> ranking."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from checkpoints import Checkpoint, checkpoint_paths, sample_checkpoints
from recommend import RouteStats, ScoredSegment, recommend, route_stats
from risk import RiskLevel, classify
from routing import Route, get_routes
from routing.types import LatLon
from weather import Weather, forecast_hour, weather_at

COORD_DECIMALS = 5
VALUE_DECIMALS = 3


@dataclass(frozen=True)
class ScoredCheckpoint:
    checkpoint: Checkpoint
    weather: Weather
    level: RiskLevel
    reasons: list[str]
    path: list[LatLon]


def plan_trip(
    origin: LatLon, destination: LatLon, departure: datetime, load_lb: float, interval_mi: int
) -> dict[str, Any]:
    routes = get_routes(origin, destination, load_lb)
    sampled = [sample_checkpoints(route, interval_mi, departure) for route in routes]

    # One batched Open-Meteo call per route, run concurrently to stay inside the 5 s budget.
    with ThreadPoolExecutor(max_workers=len(routes)) as pool:
        weathers = list(
            pool.map(lambda cps: weather_at([((c.lat, c.lon), c.eta) for c in cps]), sampled)
        )

    scored = [
        score_route(route, cps, wx, load_lb)
        for route, cps, wx in zip(routes, sampled, weathers, strict=True)
    ]
    stats = [
        route_stats(
            route.id,
            route.duration_s,
            [ScoredSegment(s.checkpoint.segment_mi, s.level) for s in cps],
        )
        for route, cps in zip(routes, scored, strict=True)
    ]
    recommendation = recommend(stats)
    stats_by_id = {s.route_id: s for s in stats}
    scored_by_id = {route.id: (route, cps) for route, cps in zip(routes, scored, strict=True)}

    return {
        "recommended_id": recommendation.route_id,
        "recommendation_reason": recommendation.reason,
        "all_no_travel": all(s.do_not_travel for s in stats),
        "routes": [
            route_payload(*scored_by_id[route_id], stats_by_id[route_id], rank)
            for rank, route_id in enumerate(recommendation.ranked_ids)
        ],
    }


def score_route(
    route: Route, checkpoints: list[Checkpoint], weathers: list[Weather], load_lb: float
) -> list[ScoredCheckpoint]:
    paths = checkpoint_paths(route, checkpoints)
    scored: list[ScoredCheckpoint] = []
    for cp, wx, path in zip(checkpoints, weathers, paths, strict=True):
        level, reasons = classify(wx.wind_mph, wx.rain_in, wx.snow_in, load_lb)
        scored.append(ScoredCheckpoint(cp, wx, level, reasons, path))
    return scored


def route_payload(
    route: Route, scored: list[ScoredCheckpoint], stats: RouteStats, rank: int
) -> dict[str, Any]:
    lats = [lat for lat, _ in route.coordinates]
    lons = [lon for _, lon in route.coordinates]
    return {
        "id": route.id,
        "rank": rank,
        "distance_mi": round(stats.distance_mi, 1),
        "duration_s": round(route.duration_s),
        "notravel_mi": round(stats.notravel_mi, 1),
        "severe_mi": round(stats.severe_mi, 1),
        "high_mi": round(stats.high_mi, 1),
        "avg_score": round(stats.avg_score, 2),
        "do_not_travel": stats.do_not_travel,
        "bbox": [_c(min(lons)), _c(min(lats)), _c(max(lons)), _c(max(lats))],
        "checkpoints": [checkpoint_payload(s) for s in scored],
    }


def checkpoint_payload(s: ScoredCheckpoint) -> dict[str, Any]:
    cp, wx = s.checkpoint, s.weather
    return {
        "index": cp.index,
        "lat": _c(cp.lat),
        "lon": _c(cp.lon),
        "distance_mi": round(cp.distance_mi, 1),
        "segment_mi": round(cp.segment_mi, 2),
        "eta": cp.eta.isoformat(),
        "forecast_hour": forecast_hour(cp.eta).isoformat(),
        "wind_mph": _v(wx.wind_mph),
        "gust_mph": _v(wx.gust_mph),
        "rain_in": _v(wx.rain_in),
        "precip_in": _v(wx.precip_in),
        "snow_in": _v(wx.snow_in),
        "level": int(s.level),
        "level_label": s.level.label,
        "reasons": s.reasons,
        # GeoJSON order [lon, lat] so the frontend can use it directly.
        "path": [[_c(lon), _c(lat)] for lat, lon in s.path],
    }


def _c(value: float) -> float:
    return round(value, COORD_DECIMALS)


def _v(value: float) -> float:
    return round(value, VALUE_DECIMALS)
