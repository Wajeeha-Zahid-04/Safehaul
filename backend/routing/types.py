from dataclasses import dataclass

LatLon = tuple[float, float]

LB_TO_TONNES = 0.45359237 / 1000


@dataclass(frozen=True)
class Place:
    label: str
    lat: float
    lon: float


@dataclass(frozen=True)
class Step:
    """A stretch of the route geometry, from coordinates[start_index] to coordinates[end_index]."""

    start_index: int
    end_index: int
    distance_m: float
    duration_s: float


@dataclass(frozen=True)
class Route:
    id: int
    distance_m: float
    duration_s: float
    coordinates: tuple[LatLon, ...]
    steps: tuple[Step, ...]


def lb_to_tonnes(load_lb: float) -> float:
    return round(load_lb * LB_TO_TONNES, 2)
