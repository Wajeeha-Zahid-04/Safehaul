"""Keyless fallback router (public Valhalla, truck costing). Used only when ORS_API_KEY is unset."""

from typing import Any

from routing import errors, polyline
from routing.types import LatLon, Route, Step, lb_to_tonnes
from upstream import UpstreamError, request_json

ROUTE_URL = "https://valhalla1.openstreetmap.de/route"
ALTERNATES = 2  # Valhalla returns the main route + N alternates -> 3 routes total.
KM_TO_M = 1000


def directions(origin: LatLon, destination: LatLon, load_lb: float) -> list[Route]:
    try:
        data = request_json("POST", ROUTE_URL, json=build_route_body(origin, destination, load_lb))
    except UpstreamError as exc:
        raise errors.from_valhalla(exc) from exc
    try:
        trips = [data["trip"], *(alt["trip"] for alt in data.get("alternates", []))]
        return [_parse_trip(i, trip) for i, trip in enumerate(trips)]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise UpstreamError("Valhalla returned an unexpected response") from exc


def build_route_body(origin: LatLon, destination: LatLon, load_lb: float) -> dict[str, Any]:
    body: dict[str, Any] = {
        "locations": [
            {"lat": origin[0], "lon": origin[1]},
            {"lat": destination[0], "lon": destination[1]},
        ],
        "costing": "truck",
        "alternates": ALTERNATES,
        "units": "kilometers",
    }
    if load_lb > 0:
        body["costing_options"] = {"truck": {"weight": lb_to_tonnes(load_lb)}}
    return body


def _parse_trip(route_id: int, trip: dict[str, Any]) -> Route:
    # Two locations -> exactly one leg, so shape indices are route-global.
    leg = trip["legs"][0]
    steps = tuple(
        Step(
            start_index=m["begin_shape_index"],
            end_index=m["end_shape_index"],
            distance_m=m["length"] * KM_TO_M,
            duration_s=m["time"],
        )
        for m in leg["maneuvers"]
    )
    return Route(
        id=route_id,
        distance_m=trip["summary"]["length"] * KM_TO_M,
        duration_s=trip["summary"]["time"],
        coordinates=tuple(polyline.decode(leg["shape"], precision=6)),
        steps=steps,
    )
