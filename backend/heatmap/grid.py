"""Heatmap grid over the routes' bbox (spec §2 `heatmap/`): ~15 km spacing, ~25 km buffer,
capped at ~400 points by widening the spacing when the area is large. Pure functions."""

import math
from dataclasses import dataclass

from routing.types import LatLon

KM_PER_DEG_LAT = 111.32
TARGET_SPACING_KM = 15.0
BUFFER_KM = 25.0
MAX_POINTS = 400


@dataclass(frozen=True)
class BBox:
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float


@dataclass(frozen=True)
class Grid:
    points: list[LatLon]
    spacing_km: float


def build_grid(bbox: BBox) -> Grid:
    area = buffered(bbox, BUFFER_KM)
    height_km, width_km = extent_km(area)
    spacing = TARGET_SPACING_KM
    rows, cols = _count(height_km, spacing), _count(width_km, spacing)
    if rows * cols > MAX_POINTS:
        spacing *= math.sqrt(rows * cols / MAX_POINTS)
        rows, cols = _count(height_km, spacing), _count(width_km, spacing)
        while rows * cols > MAX_POINTS:  # integer rounding can still overshoot slightly
            spacing *= 1.05
            rows, cols = _count(height_km, spacing), _count(width_km, spacing)
    return Grid(points=_points(area, rows, cols), spacing_km=spacing)


def buffered(bbox: BBox, km: float) -> BBox:
    d_lat = km / KM_PER_DEG_LAT
    d_lon = km / (KM_PER_DEG_LAT * _cos_mid_lat(bbox))
    return BBox(
        min_lon=max(-180.0, bbox.min_lon - d_lon),
        min_lat=max(-90.0, bbox.min_lat - d_lat),
        max_lon=min(180.0, bbox.max_lon + d_lon),
        max_lat=min(90.0, bbox.max_lat + d_lat),
    )


def extent_km(bbox: BBox) -> tuple[float, float]:
    """(height, width) in km; width measured at the bbox's middle latitude."""
    height = (bbox.max_lat - bbox.min_lat) * KM_PER_DEG_LAT
    width = (bbox.max_lon - bbox.min_lon) * KM_PER_DEG_LAT * _cos_mid_lat(bbox)
    return height, width


def _count(extent_km: float, spacing_km: float) -> int:
    return math.floor(extent_km / spacing_km) + 1


def _points(area: BBox, rows: int, cols: int) -> list[LatLon]:
    """rows x cols points spread evenly edge-to-edge across the area (row-major, south first)."""
    lats = _linspace(area.min_lat, area.max_lat, rows)
    lons = _linspace(area.min_lon, area.max_lon, cols)
    return [(round(lat, 4), round(lon, 4)) for lat in lats for lon in lons]


def _linspace(lo: float, hi: float, n: int) -> list[float]:
    if n == 1:
        return [(lo + hi) / 2]
    step = (hi - lo) / (n - 1)
    return [lo + i * step for i in range(n)]


def _cos_mid_lat(bbox: BBox) -> float:
    return max(0.01, math.cos(math.radians((bbox.min_lat + bbox.max_lat) / 2)))
