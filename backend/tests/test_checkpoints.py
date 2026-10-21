import math
from datetime import UTC, datetime, timedelta

import pytest

from checkpoints import Checkpoint, sample_checkpoints
from checkpoints.geo import EARTH_RADIUS_MI, cumulative_distances_mi, haversine_mi
from checkpoints.sampler import checkpoint_distances_mi, vertex_times_s
from routing.types import Route, Step

MI_PER_DEG_LAT = EARTH_RADIUS_MI * math.pi / 180  # exact along a meridian
DEPARTURE = datetime(2026, 10, 22, 8, 0, tzinfo=UTC)
TOL = 1e-6


def at_mile(mile: float) -> tuple[float, float]:
    """A point `mile` miles north of (0, 0) along the prime meridian."""
    return (mile / MI_PER_DEG_LAT, 0.0)


def meridian_route(
    total_mi: float,
    vertex_every_mi: float,
    steps: list[tuple[float, float]] | None = None,
    duration_s: float = 3600,
) -> Route:
    """Straight route north. `steps` = [(end_mile, duration_s), ...]; default: one uniform step.

    `total_mi` must be a multiple of `vertex_every_mi`.
    """
    n = round(total_mi / vertex_every_mi)
    miles = [i * vertex_every_mi for i in range(n + 1)]
    coords = tuple(at_mile(m) for m in miles)
    spec = steps or [(total_mi, duration_s)]
    built: list[Step] = []
    start = 0
    for end_mile, dur in spec:
        end = miles.index(end_mile)
        built.append(Step(start, end, 0.0, dur))
        start = end
    return Route(
        id=0,
        distance_m=total_mi * 1609.344,
        duration_s=sum(d for _, d in spec),
        coordinates=coords,
        steps=tuple(built),
    )


def miles(cps: list[Checkpoint]) -> list[float]:
    return [round(cp.distance_mi, 6) for cp in cps]


# --- geo ---
def test_haversine_one_degree_of_latitude() -> None:
    assert haversine_mi((0, 0), (1, 0)) == pytest.approx(69.0934, abs=1e-3)


def test_haversine_real_city_pair() -> None:
    # Chicago -> Detroit great-circle distance is ~238 mi.
    assert haversine_mi((41.8781, -87.6298), (42.3314, -83.0458)) == pytest.approx(238, abs=2)


def test_cumulative_distances() -> None:
    coords = (at_mile(0), at_mile(3), at_mile(10))
    assert cumulative_distances_mi(coords) == pytest.approx([0, 3, 10])


# --- spacing (10 / 25 / 50 mi) ---
@pytest.mark.parametrize(
    ("interval", "expected"),
    [
        (10, [10, 20, 30, 40, 50, 60]),
        (25, [25, 50, 60]),
        (50, [50, 60]),
    ],
)
def test_spacing_for_each_interval(interval: int, expected: list[float]) -> None:
    cps = sample_checkpoints(meridian_route(60, 5), interval, DEPARTURE)
    assert miles(cps) == expected
    assert [cp.index for cp in cps] == list(range(len(expected)))


def test_destination_not_duplicated_when_total_is_a_multiple_of_interval() -> None:
    assert checkpoint_distances_mi(50, 25) == [25, 50]
    assert checkpoint_distances_mi(50 + 1e-9, 25) == [25, 50 + 1e-9]  # float noise tolerated


def test_route_shorter_than_interval_has_only_destination() -> None:
    cps = sample_checkpoints(meridian_route(8, 2), 10, DEPARTURE)
    assert miles(cps) == [8]
    assert cps[0].segment_mi == pytest.approx(8)


def test_destination_is_always_last_with_exact_coords_and_full_duration() -> None:
    route = meridian_route(60, 5, duration_s=4000)
    last = sample_checkpoints(route, 25, DEPARTURE)[-1]
    assert (last.lat, last.lon) == route.coordinates[-1]
    assert last.elapsed_s == pytest.approx(4000)
    assert last.eta == DEPARTURE + timedelta(seconds=4000)


# --- mile attribution ---
@pytest.mark.parametrize("interval", [10, 25, 50])
def test_segments_partition_the_route(interval: int) -> None:
    cps = sample_checkpoints(meridian_route(63, 3), interval, DEPARTURE)
    assert sum(cp.segment_mi for cp in cps) == pytest.approx(63)
    assert all(cp.segment_mi > 0 for cp in cps)


def test_each_checkpoint_owns_miles_since_previous() -> None:
    cps = sample_checkpoints(meridian_route(60, 5), 25, DEPARTURE)
    assert [round(cp.segment_mi, 6) for cp in cps] == [25, 25, 10]


# --- position interpolation between vertices ---
def test_checkpoint_between_vertices_is_interpolated() -> None:
    cps = sample_checkpoints(meridian_route(30, 7.5), 10, DEPARTURE)
    assert cps[0].lat == pytest.approx(at_mile(10)[0], abs=TOL)
    assert cps[0].lon == pytest.approx(0.0)
    assert haversine_mi((0, 0), (cps[0].lat, cps[0].lon)) == pytest.approx(10, abs=TOL)


# --- ETA interpolation ---
def test_eta_constant_speed() -> None:
    # 60 mi in 3600 s = 60 mph -> mile 25 is reached after 25 min.
    cps = sample_checkpoints(meridian_route(60, 5), 25, DEPARTURE)
    assert cps[0].elapsed_s == pytest.approx(25 * 60)
    assert cps[0].eta == DEPARTURE + timedelta(minutes=25)
    assert cps[1].eta == DEPARTURE + timedelta(minutes=50)


def test_eta_respects_per_step_speeds() -> None:
    # First 30 mi at 60 mph (1800 s), next 30 mi at 30 mph (3600 s).
    route = meridian_route(60, 5, steps=[(30, 1800), (60, 3600)])
    cps = sample_checkpoints(route, 10, DEPARTURE)
    elapsed = [cp.elapsed_s for cp in cps]
    assert elapsed == pytest.approx([600, 1200, 1800, 3000, 4200, 5400])


def test_eta_interpolates_inside_a_step_between_vertices() -> None:
    # Checkpoint at mile 45 sits mid-way between vertices 40 and 50 inside the slow step.
    route = meridian_route(60, 10, steps=[(30, 1800), (60, 3600)])
    cp = sample_checkpoints(route, 45, DEPARTURE)[0]
    assert cp.distance_mi == pytest.approx(45)
    assert cp.elapsed_s == pytest.approx(1800 + 15 / 30 * 3600)


def test_etas_are_monotonic_and_timezone_aware() -> None:
    cps = sample_checkpoints(meridian_route(102, 3, duration_s=7200), 10, DEPARTURE)
    etas = [cp.eta for cp in cps]
    assert etas == sorted(etas)
    assert all(eta.tzinfo is not None for eta in etas)


def test_zero_length_step_duration_delays_later_vertices() -> None:
    # A 600 s stop at mile 10 (step with start == end) shifts every later ETA.
    cum = [0.0, 10.0, 20.0]
    steps = (Step(0, 1, 0, 600), Step(1, 1, 0, 600), Step(1, 2, 0, 600))
    assert vertex_times_s(cum, steps, 1800) == pytest.approx([0, 600, 1800])


def test_falls_back_to_distance_spread_when_steps_do_not_cover_route() -> None:
    cum = [0.0, 10.0, 30.0]
    gappy = (Step(0, 1, 0, 100),)  # never reaches the last vertex
    assert vertex_times_s(cum, gappy, 3000) == pytest.approx([0, 1000, 3000])
    assert vertex_times_s(cum, (), 3000) == pytest.approx([0, 1000, 3000])


# --- validation ---
def test_rejects_naive_departure() -> None:
    with pytest.raises(ValueError):
        sample_checkpoints(meridian_route(60, 5), 10, datetime(2026, 10, 22, 8, 0))


@pytest.mark.parametrize("interval", [0, -10])
def test_rejects_non_positive_interval(interval: float) -> None:
    with pytest.raises(ValueError):
        sample_checkpoints(meridian_route(60, 5), interval, DEPARTURE)


def test_rejects_single_point_route() -> None:
    route = Route(0, 0, 0, (at_mile(0),), ())
    with pytest.raises(ValueError):
        sample_checkpoints(route, 10, DEPARTURE)
