"""Checkpoint sampler (spec §2 `checkpoints/`).

Walks the route polyline at a fixed interval using haversine cumulative distance. ETA is
departure + the cumulative duration interpolated at that distance. The destination is always
the final checkpoint, and each checkpoint owns the miles since the previous one (spec §1).
"""

import math
from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import pairwise

from checkpoints.geo import cumulative_distances_mi
from routing.types import LatLon, Route, Step

DISTANCE_EPS_MI = 1e-6


@dataclass(frozen=True)
class Checkpoint:
    index: int
    lat: float
    lon: float
    distance_mi: float  # cumulative from origin
    segment_mi: float  # miles owned: from the previous checkpoint (or origin) to here
    elapsed_s: float
    eta: datetime


def sample_checkpoints(route: Route, interval_mi: float, departure: datetime) -> list[Checkpoint]:
    _validate(route, interval_mi, departure)
    cum_mi = cumulative_distances_mi(route.coordinates)
    times_s = vertex_times_s(cum_mi, route.steps, route.duration_s)

    checkpoints: list[Checkpoint] = []
    previous_mi = 0.0
    for index, target_mi in enumerate(checkpoint_distances_mi(cum_mi[-1], interval_mi)):
        lat, lon, elapsed_s = _interpolate(route.coordinates, cum_mi, times_s, target_mi)
        checkpoints.append(
            Checkpoint(
                index=index,
                lat=lat,
                lon=lon,
                distance_mi=target_mi,
                segment_mi=target_mi - previous_mi,
                elapsed_s=elapsed_s,
                eta=departure + timedelta(seconds=elapsed_s),
            )
        )
        previous_mi = target_mi
    return checkpoints


def checkpoint_distances_mi(total_mi: float, interval_mi: float) -> list[float]:
    """interval, 2*interval, ... strictly before the destination, then the destination itself.

    A small tolerance stops float noise in the haversine sum (e.g. 50.0000001 mi at a 25 mi
    interval) from adding a near-zero-length checkpoint next to the destination.
    """
    count = max(0, math.ceil((total_mi - DISTANCE_EPS_MI) / interval_mi) - 1)
    return [interval_mi * k for k in range(1, count + 1)] + [total_mi]


def vertex_times_s(cum_mi: list[float], steps: tuple[Step, ...], total_s: float) -> list[float]:
    """Elapsed seconds at each vertex.

    Each step's duration is spread over its vertices in proportion to distance, so speed
    differences between steps are preserved. If the steps don't cover the polyline
    contiguously, fall back to spreading the route's total duration evenly by distance.
    """
    if not _steps_cover(steps, len(cum_mi) - 1):
        return _times_by_distance(cum_mi, 0, len(cum_mi) - 1, 0.0, total_s)

    times = [0.0] * len(cum_mi)
    elapsed = 0.0
    for step in steps:
        segment = _times_by_distance(
            cum_mi, step.start_index, step.end_index, elapsed, step.duration_s
        )
        times[step.start_index + 1 : step.end_index + 1] = segment[1:]
        elapsed += step.duration_s
    return times


def _times_by_distance(
    cum_mi: list[float], start: int, end: int, start_s: float, duration_s: float
) -> list[float]:
    span = cum_mi[end] - cum_mi[start]
    if span <= 0:
        return [start_s] + [start_s + duration_s] * (end - start)
    return [
        start_s + duration_s * (cum_mi[i] - cum_mi[start]) / span for i in range(start, end + 1)
    ]


def _steps_cover(steps: tuple[Step, ...], last_index: int) -> bool:
    if not steps or steps[0].start_index != 0 or steps[-1].end_index != last_index:
        return False
    in_order = all(s.start_index <= s.end_index for s in steps)
    contiguous = all(a.end_index == b.start_index for a, b in pairwise(steps))
    return in_order and contiguous


def _interpolate(
    coords: tuple[LatLon, ...], cum_mi: list[float], times_s: list[float], target_mi: float
) -> tuple[float, float, float]:
    """Position and elapsed time at `target_mi` along the polyline."""
    if target_mi >= cum_mi[-1]:
        lat, lon = coords[-1]
        return lat, lon, times_s[-1]
    hi = bisect_right(cum_mi, target_mi)  # cum_mi[hi - 1] <= target < cum_mi[hi]
    lo = hi - 1
    span = cum_mi[hi] - cum_mi[lo]
    f = (target_mi - cum_mi[lo]) / span if span > 0 else 0.0
    (lat_a, lon_a), (lat_b, lon_b) = coords[lo], coords[hi]
    return (
        lat_a + f * (lat_b - lat_a),
        lon_a + f * (lon_b - lon_a),
        times_s[lo] + f * (times_s[hi] - times_s[lo]),
    )


def _validate(route: Route, interval_mi: float, departure: datetime) -> None:
    if len(route.coordinates) < 2:
        raise ValueError("route needs at least two coordinates")
    if not interval_mi > 0:
        raise ValueError(f"interval_mi must be positive, got {interval_mi!r}")
    if departure.tzinfo is None:
        raise ValueError("departure must be timezone-aware")
