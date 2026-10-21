import json
from typing import Any

import pytest
import requests
import responses
from responses import matchers

from routing import Place, Route, Step, geocode, get_routes, ors, photon, polyline, valhalla
from upstream import ATTEMPTS, USER_AGENT, UpstreamError

CHICAGO = (41.8781, -87.6298)
DETROIT = (42.3314, -83.0458)
LOAD_LB = 40_000
LOAD_TONNES = 18.14  # 40,000 lb


def encode_polyline(coords: list[tuple[float, float]], precision: int = 6) -> str:
    """Test-only encoder, inverse of routing.polyline.decode."""
    factor = 10**precision
    out: list[str] = []
    prev_lat = prev_lon = 0
    for lat, lon in coords:
        ilat, ilon = round(lat * factor), round(lon * factor)
        for delta in (ilat - prev_lat, ilon - prev_lon):
            value = ~(delta << 1) if delta < 0 else delta << 1
            while value >= 0x20:
                out.append(chr((0x20 | (value & 0x1F)) + 63))
                value >>= 5
            out.append(chr(value + 63))
        prev_lat, prev_lon = ilat, ilon
    return "".join(out)


def ors_feature(coords_lonlat: list[list[float]], distance: float, duration: float) -> dict:
    last = len(coords_lonlat) - 1
    return {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": coords_lonlat},
        "properties": {
            "summary": {"distance": distance, "duration": duration},
            "segments": [
                {
                    "distance": distance,
                    "duration": duration,
                    "steps": [
                        {
                            "distance": distance * 0.6,
                            "duration": duration * 0.5,
                            "way_points": [0, 1],
                        },
                        {
                            "distance": distance * 0.4,
                            "duration": duration * 0.5,
                            "way_points": [1, last],
                        },
                        {"distance": 0, "duration": 0, "way_points": [last, last]},
                    ],
                }
            ],
        },
    }


def valhalla_trip(coords: list[tuple[float, float]], length_km: float, time_s: float) -> dict:
    last = len(coords) - 1
    return {
        "summary": {"length": length_km, "time": time_s},
        "legs": [
            {
                "shape": encode_polyline(coords),
                "maneuvers": [
                    {
                        "time": time_s,
                        "length": length_km,
                        "begin_shape_index": 0,
                        "end_shape_index": last,
                    },
                    {"time": 0, "length": 0, "begin_shape_index": last, "end_shape_index": last},
                ],
            }
        ],
    }


def body_of(call: Any) -> dict:
    return json.loads(call.request.body)


# --- polyline ---
def test_polyline_decodes_reference_example() -> None:
    # Reference example from the Google encoded-polyline spec (precision 5).
    decoded = polyline.decode("_p~iF~ps|U_ulLnnqC_mqNvxq`@", precision=5)
    assert decoded == [(38.5, -120.2), (40.7, -120.95), (43.252, -126.453)]


def test_polyline_round_trips_precision_6() -> None:
    coords = [(41.878114, -87.629798), (42.331427, -83.045754)]
    assert polyline.decode(encode_polyline(coords)) == coords


# --- ORS ---
@responses.activate
def test_ors_directions_request_and_parsing() -> None:
    responses.post(
        ors.DIRECTIONS_URL,
        json={
            "features": [
                ors_feature([[-87.63, 41.88], [-85.0, 42.0], [-83.05, 42.33]], 455_000, 16_000),
                ors_feature([[-87.63, 41.88], [-84.0, 41.5], [-83.05, 42.33]], 470_000, 17_000),
            ]
        },
        match=[matchers.header_matcher({"Authorization": "test-key"})],
    )

    routes = ors.directions(CHICAGO, DETROIT, LOAD_LB, "test-key")

    body = body_of(responses.calls[0])
    assert body["coordinates"] == [[CHICAGO[1], CHICAGO[0]], [DETROIT[1], DETROIT[0]]]
    assert body["alternative_routes"] == {"target_count": 3}
    assert body["options"]["vehicle_type"] == "hgv"
    assert body["options"]["profile_params"]["restrictions"]["weight"] == LOAD_TONNES

    assert [r.id for r in routes] == [0, 1]
    first = routes[0]
    assert first.distance_m == 455_000
    assert first.duration_s == 16_000
    assert first.coordinates == ((41.88, -87.63), (42.0, -85.0), (42.33, -83.05))
    assert first.steps[0] == Step(start_index=0, end_index=1, distance_m=273_000, duration_s=8_000)
    assert first.steps[-1].start_index == first.steps[-1].end_index == 2


def test_ors_body_omits_weight_restriction_for_zero_load() -> None:
    assert "options" not in ors.build_directions_body(CHICAGO, DETROIT, 0)


@responses.activate
def test_ors_no_routes_raises() -> None:
    responses.post(ors.DIRECTIONS_URL, json={"features": []})
    with pytest.raises(UpstreamError):
        ors.directions(CHICAGO, DETROIT, LOAD_LB, "k")


@responses.activate
def test_ors_malformed_route_raises_upstream_error() -> None:
    responses.post(ors.DIRECTIONS_URL, json={"features": [{"properties": {}}]})
    with pytest.raises(UpstreamError):
        ors.directions(CHICAGO, DETROIT, LOAD_LB, "k")


@responses.activate
def test_ors_geocode() -> None:
    responses.get(
        ors.GEOCODE_URL,
        json={
            "features": [
                {
                    "geometry": {"coordinates": [-87.63, 41.88]},
                    "properties": {"label": "Chicago, IL, USA"},
                }
            ]
        },
        match=[matchers.query_param_matcher({"api_key": "k", "text": "Chic", "size": "5"})],
    )
    assert ors.geocode("Chic", "k") == [Place("Chicago, IL, USA", 41.88, -87.63)]


# --- Valhalla fallback ---
@responses.activate
def test_valhalla_request_and_parsing_returns_main_plus_alternates() -> None:
    main = [(41.878114, -87.629798), (42.0, -85.0), (42.331427, -83.045754)]
    alt = [(41.878114, -87.629798), (41.5, -84.0), (42.331427, -83.045754)]
    responses.post(
        valhalla.ROUTE_URL,
        json={
            "trip": valhalla_trip(main, 455.0, 16_000),
            "alternates": [{"trip": valhalla_trip(alt, 470.0, 17_000)}],
        },
    )

    routes = valhalla.directions(CHICAGO, DETROIT, LOAD_LB)

    body = body_of(responses.calls[0])
    assert body["costing"] == "truck"
    assert body["alternates"] == 2
    assert body["costing_options"]["truck"]["weight"] == LOAD_TONNES
    assert body["locations"][0] == {"lat": CHICAGO[0], "lon": CHICAGO[1]}

    assert [r.id for r in routes] == [0, 1]
    assert routes[0].coordinates == tuple(main)
    assert routes[0].distance_m == 455_000
    assert routes[1].duration_s == 17_000
    assert routes[0].steps[0] == Step(0, 2, 455_000, 16_000)


@responses.activate
def test_valhalla_malformed_response_raises_upstream_error() -> None:
    responses.post(valhalla.ROUTE_URL, json={"error": "No path"})
    with pytest.raises(UpstreamError):
        valhalla.directions(CHICAGO, DETROIT, LOAD_LB)


# --- Photon fallback ---
@responses.activate
def test_photon_geocode_builds_label_without_duplicates() -> None:
    responses.get(
        photon.SEARCH_URL,
        json={
            "features": [
                {
                    "geometry": {"coordinates": [-87.63, 41.88]},
                    "properties": {
                        "name": "Chicago",
                        "city": "Chicago",
                        "state": "Illinois",
                        "country": "United States",
                    },
                }
            ]
        },
    )
    assert photon.geocode("Chic") == [Place("Chicago, Illinois, United States", 41.88, -87.63)]


# --- Upstream timeout / retry ---
@responses.activate
def test_sends_app_user_agent_alongside_custom_headers() -> None:
    responses.post(
        ors.DIRECTIONS_URL,
        json={"features": [ors_feature([[-87.63, 41.88], [-83.05, 42.33]], 1, 1)]},
        match=[matchers.header_matcher({"User-Agent": USER_AGENT, "Authorization": "k"})],
    )
    ors.directions(CHICAGO, DETROIT, LOAD_LB, "k")


@responses.activate
def test_retries_once_on_server_error_then_succeeds() -> None:
    responses.get(photon.SEARCH_URL, status=503)
    responses.get(photon.SEARCH_URL, json={"features": []})
    assert photon.geocode("x") == []
    assert len(responses.calls) == 2


@responses.activate
def test_retries_once_on_connection_error_then_fails() -> None:
    responses.get(photon.SEARCH_URL, body=requests.ConnectionError("down"))
    with pytest.raises(UpstreamError):
        photon.geocode("x")
    assert len(responses.calls) == ATTEMPTS == 2


@responses.activate
def test_failures_are_logged_without_query_string(caplog: pytest.LogCaptureFixture) -> None:
    responses.get(ors.GEOCODE_URL, status=429, body='{"error": "rate limited"}')
    with pytest.raises(UpstreamError):
        ors.geocode("Chicago", "super-secret-key")
    assert "HTTP 429" in caplog.text
    assert "rate limited" in caplog.text
    assert "super-secret-key" not in caplog.text


@responses.activate
def test_client_errors_are_not_retried() -> None:
    responses.post(ors.DIRECTIONS_URL, status=400, json={"error": "bad"})
    with pytest.raises(UpstreamError):
        ors.directions(CHICAGO, DETROIT, LOAD_LB, "k")
    assert len(responses.calls) == 1


# --- Service: provider selection + caching ---
@responses.activate
def test_service_uses_ors_when_key_is_set(settings: Any) -> None:
    settings.ORS_API_KEY = "real-key"
    responses.post(
        ors.DIRECTIONS_URL,
        json={"features": [ors_feature([[-87.63, 41.88], [-83.05, 42.33]], 1, 1)]},
    )
    routes = get_routes(CHICAGO, DETROIT, LOAD_LB)
    assert isinstance(routes[0], Route)
    assert responses.calls[0].request.url == ors.DIRECTIONS_URL


@responses.activate
def test_service_falls_back_to_valhalla_without_key(settings: Any) -> None:
    settings.ORS_API_KEY = ""
    responses.post(
        valhalla.ROUTE_URL, json={"trip": valhalla_trip([CHICAGO, DETROIT], 455.0, 16_000)}
    )
    get_routes(CHICAGO, DETROIT, LOAD_LB)
    assert responses.calls[0].request.url == valhalla.ROUTE_URL


@responses.activate
def test_service_geocode_falls_back_to_photon_and_caches(settings: Any) -> None:
    settings.ORS_API_KEY = ""
    responses.get(photon.SEARCH_URL, json={"features": []})
    geocode("Chicago")
    geocode("  chicago ")
    assert len(responses.calls) == 1


def test_service_geocode_blank_query_makes_no_call() -> None:
    assert geocode("   ") == []


@responses.activate
def test_service_caches_routes_per_origin_destination_load(settings: Any) -> None:
    settings.ORS_API_KEY = "k"
    responses.post(
        ors.DIRECTIONS_URL,
        json={"features": [ors_feature([[-87.63, 41.88], [-83.05, 42.33]], 1, 1)]},
    )
    get_routes(CHICAGO, DETROIT, LOAD_LB)
    get_routes(CHICAGO, DETROIT, LOAD_LB)
    assert len(responses.calls) == 1
    get_routes(CHICAGO, DETROIT, LOAD_LB + 1)
    assert len(responses.calls) == 2
