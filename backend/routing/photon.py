"""Keyless fallback geocoder (Photon by Komoot). Used only when ORS_API_KEY is unset."""

from typing import Any

from routing.types import Place
from upstream import UpstreamError, request_json

SEARCH_URL = "https://photon.komoot.io/api/"
LIMIT = 5
LABEL_FIELDS = ("name", "city", "state", "country")


def geocode(query: str) -> list[Place]:
    data = request_json("GET", SEARCH_URL, params={"q": query, "limit": LIMIT})
    try:
        return [_parse_place(feature) for feature in data.get("features", [])]
    except (KeyError, TypeError, ValueError) as exc:
        raise UpstreamError("Photon returned an unexpected response") from exc


def _label(props: dict[str, Any]) -> str:
    parts: list[str] = []
    for field in LABEL_FIELDS:
        value = props.get(field)
        if value and value not in parts:
            parts.append(value)
    return ", ".join(parts)


def _parse_place(feature: dict[str, Any]) -> Place:
    lon, lat = feature["geometry"]["coordinates"]
    return Place(label=_label(feature["properties"]), lat=lat, lon=lon)
