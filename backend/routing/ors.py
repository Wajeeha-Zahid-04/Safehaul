"""OpenRouteService client: geocode autocomplete + driving-hgv with 3 alternatives (spec §2)."""

from typing import Any

from routing.types import LatLon, Place, Route, Step, lb_to_tonnes
from upstream import UpstreamError, request_json

BASE_URL = "https://api.openrouteservice.org"
GEOCODE_URL = f"{BASE_URL}/geocode/autocomplete"
DIRECTIONS_URL = f"{BASE_URL}/v2/directions/driving-hgv/geojson"
ALTERNATIVE_COUNT = 3
GEOCODE_LIMIT = 5


def geocode(query: str, api_key: str) -> list[Place]:
    data = request_json(
        "GET", GEOCODE_URL, params={"api_key": api_key, "text": query, "size": GEOCODE_LIMIT}
    )
    try:
        return [_parse_place(feature) for feature in data.get("features", [])]
    except (KeyError, TypeError, ValueError) as exc:
        raise UpstreamError("ORS geocode returned an unexpected response") from exc


def directions(origin: LatLon, destination: LatLon, load_lb: float, api_key: str) -> list[Route]:
    data = request_json(
        "POST",
        DIRECTIONS_URL,
        json=build_directions_body(origin, destination, load_lb),
        headers={"Authorization": api_key},
    )
    features = data.get("features") or []
    if not features:
        raise UpstreamError("ORS returned no routes")
    try:
        return [_parse_route(i, feature) for i, feature in enumerate(features)]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise UpstreamError("ORS returned an unexpected response") from exc


def build_directions_body(origin: LatLon, destination: LatLon, load_lb: float) -> dict[str, Any]:
    body: dict[str, Any] = {
        # ORS expects [lon, lat].
        "coordinates": [[origin[1], origin[0]], [destination[1], destination[0]]],
        "alternative_routes": {"target_count": ALTERNATIVE_COUNT},
        "units": "m",
    }
    if load_lb > 0:
        body["options"] = {
            "vehicle_type": "hgv",
            "profile_params": {"restrictions": {"weight": lb_to_tonnes(load_lb)}},
        }
    return body


def _parse_place(feature: dict[str, Any]) -> Place:
    lon, lat = feature["geometry"]["coordinates"]
    return Place(label=feature["properties"]["label"], lat=lat, lon=lon)


def _parse_route(route_id: int, feature: dict[str, Any]) -> Route:
    props = feature["properties"]
    steps = tuple(
        Step(
            start_index=step["way_points"][0],
            end_index=step["way_points"][1],
            distance_m=step["distance"],
            duration_s=step["duration"],
        )
        for segment in props["segments"]
        for step in segment["steps"]
    )
    return Route(
        id=route_id,
        distance_m=props["summary"]["distance"],
        duration_s=props["summary"]["duration"],
        coordinates=tuple((lat, lon) for lon, lat, *_ in feature["geometry"]["coordinates"]),
        steps=steps,
    )
