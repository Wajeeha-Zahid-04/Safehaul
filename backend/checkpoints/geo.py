import math
from itertools import pairwise

from routing.types import LatLon

EARTH_RADIUS_MI = 3958.7613


def haversine_mi(a: LatLon, b: LatLon) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MI * math.asin(min(1.0, math.sqrt(h)))


def cumulative_distances_mi(coords: tuple[LatLon, ...]) -> list[float]:
    """Distance from the first vertex to each vertex, in miles."""
    totals = [0.0]
    for a, b in pairwise(coords):
        totals.append(totals[-1] + haversine_mi(a, b))
    return totals
