"""Decoder for the Google encoded-polyline format (Valhalla uses precision 6)."""

from routing.types import LatLon


def _decode_values(encoded: str) -> list[int]:
    values: list[int] = []
    result = shift = 0
    for char in encoded:
        byte = ord(char) - 63
        result |= (byte & 0x1F) << shift
        shift += 5
        if byte < 0x20:
            values.append(~(result >> 1) if result & 1 else result >> 1)
            result = shift = 0
    return values


def decode(encoded: str, precision: int = 6) -> list[LatLon]:
    factor = 10**precision
    values = _decode_values(encoded)
    coords: list[LatLon] = []
    lat = lon = 0
    for d_lat, d_lon in zip(values[0::2], values[1::2], strict=True):
        lat += d_lat
        lon += d_lon
        coords.append((lat / factor, lon / factor))
    return coords
