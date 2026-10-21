import pytest

from recommend import RouteStats, ScoredSegment, rank, recommend, route_stats, sort_key
from risk import RiskLevel

L, M, H, S, NT = (
    RiskLevel.LOW,
    RiskLevel.MODERATE,
    RiskLevel.HIGH,
    RiskLevel.SEVERE,
    RiskLevel.NO_TRAVEL,
)
HOUR = 3600


def stats(
    route_id: int,
    notravel: float = 0,
    severe: float = 0,
    high: float = 0,
    avg: float = 0,
    duration_s: float = HOUR,
) -> RouteStats:
    return RouteStats(
        route_id=route_id,
        distance_mi=100,
        duration_s=duration_s,
        notravel_mi=notravel,
        severe_mi=severe,
        high_mi=high,
        avg_score=avg,
        do_not_travel=notravel > 0,
    )


def seg(miles: float, level: RiskLevel) -> ScoredSegment:
    return ScoredSegment(miles, level)


# --- route_stats ---
def test_route_stats_attributes_segment_miles_to_each_level() -> None:
    s = route_stats(7, 5000, [seg(25, L), seg(25, H), seg(25, S), seg(10, NT), seg(15, H)])
    assert s.route_id == 7
    assert s.duration_s == 5000
    assert s.distance_mi == pytest.approx(100)
    assert s.high_mi == pytest.approx(40)
    assert s.severe_mi == pytest.approx(25)
    assert s.notravel_mi == pytest.approx(10)
    assert s.do_not_travel is True


def test_avg_score_is_mile_weighted() -> None:
    # 50 mi Low (0) + 50 mi Severe (3) -> 1.5, despite 3 checkpoints vs 1.
    s = route_stats(0, HOUR, [seg(20, L), seg(20, L), seg(10, L), seg(50, S)])
    assert s.avg_score == pytest.approx(1.5)


def test_short_destination_stub_does_not_skew_average() -> None:
    # A 2 mi No-Travel stub barely moves a 100 mi Low route.
    s = route_stats(0, HOUR, [seg(50, L), seg(48, L), seg(2, NT)])
    assert s.avg_score == pytest.approx(0.08)


def test_route_without_no_travel_is_not_flagged() -> None:
    s = route_stats(0, HOUR, [seg(30, S), seg(30, H)])
    assert s.do_not_travel is False
    assert s.notravel_mi == 0


def test_zero_length_route_has_zero_average() -> None:
    assert route_stats(0, 0, [seg(0, H)]).avg_score == 0


# --- sort order: each criterion decides only when all earlier ones tie ---
def test_fewest_no_travel_miles_wins_over_everything_else() -> None:
    a = stats(0, notravel=1, severe=0, high=0, avg=0.1, duration_s=HOUR)
    b = stats(1, notravel=0, severe=90, high=10, avg=3.0, duration_s=5 * HOUR)
    assert [s.route_id for s in rank([a, b])] == [1, 0]


def test_then_fewest_severe_miles() -> None:
    a = stats(0, severe=10, high=0, avg=0.5)
    b = stats(1, severe=5, high=80, avg=2.0, duration_s=3 * HOUR)
    assert [s.route_id for s in rank([a, b])] == [1, 0]


def test_then_fewest_high_miles() -> None:
    a = stats(0, severe=5, high=20, avg=0.5)
    b = stats(1, severe=5, high=10, avg=1.5, duration_s=3 * HOUR)
    assert [s.route_id for s in rank([a, b])] == [1, 0]


def test_then_lowest_average_score() -> None:
    a = stats(0, high=10, avg=1.2)
    b = stats(1, high=10, avg=0.9, duration_s=3 * HOUR)
    assert [s.route_id for s in rank([a, b])] == [1, 0]


def test_then_shortest_duration() -> None:
    a = stats(0, high=10, avg=0.9, duration_s=2 * HOUR)
    b = stats(1, high=10, avg=0.9, duration_s=HOUR)
    assert [s.route_id for s in rank([a, b])] == [1, 0]


def test_full_tie_is_broken_by_route_id_deterministically() -> None:
    assert [s.route_id for s in rank([stats(2), stats(0), stats(1)])] == [0, 1, 2]


def test_three_routes_full_ordering() -> None:
    fast_risky = stats(0, severe=12, duration_s=HOUR)
    slow_safe = stats(1, severe=0, high=30, duration_s=HOUR + 720)
    safest_slowest = stats(2, severe=0, high=5, duration_s=2 * HOUR)
    assert [s.route_id for s in rank([fast_risky, slow_safe, safest_slowest])] == [2, 1, 0]


def test_float_noise_in_miles_falls_through_to_next_key() -> None:
    a = stats(0, severe=25.0000000001, duration_s=HOUR)
    b = stats(1, severe=25.0, duration_s=2 * HOUR)
    assert [s.route_id for s in rank([a, b])] == [0, 1]  # treated as tie -> faster wins


def test_sort_key_matches_spec_tuple() -> None:
    s = stats(3, notravel=1, severe=2, high=3, avg=1.5, duration_s=99)
    assert sort_key(s) == (1, 2, 3, 1.5, 99, 3)


# --- recommend + reason ---
def test_recommend_returns_top_route_and_full_ranking() -> None:
    rec = recommend([stats(0, severe=12), stats(1, severe=0, duration_s=HOUR + 720)])
    assert rec.route_id == 1
    assert rec.ranked_ids == [1, 0]
    assert rec.reason == "0 severe mi vs 12, 12 min slower"


def test_reason_when_recommended_is_also_fastest() -> None:
    rec = recommend([stats(0, high=4), stats(1, high=9, duration_s=2 * HOUR)])
    assert rec.reason == "4 high mi vs 9, fastest"


def test_reason_for_no_travel_decision() -> None:
    rec = recommend([stats(0, notravel=8), stats(1, severe=30, duration_s=HOUR + 300)])
    assert rec.reason == "No No-Travel miles (vs 8), 5 min slower"


def test_reason_for_average_score_decision() -> None:
    rec = recommend([stats(0, avg=0.75), stats(1, avg=0.25, duration_s=HOUR + 60)])
    assert rec.reason == "Lowest avg risk (0.25 vs 0.75), 1 min slower"


def test_reason_for_duration_decision() -> None:
    rec = recommend([stats(0, duration_s=2 * HOUR), stats(1, duration_s=HOUR)])
    assert rec.route_id == 1
    assert rec.reason == "Same risk as alternatives, fastest"


def test_reason_for_full_tie() -> None:
    assert recommend([stats(0), stats(1)]).reason == "Tied with alternatives on risk and duration"


def test_reason_when_every_route_has_no_travel() -> None:
    rec = recommend([stats(0, notravel=20), stats(1, notravel=5, duration_s=2 * HOUR)])
    assert rec.route_id == 1
    assert rec.reason == "Do not travel: every route has No-Travel miles (5 mi here)"


def test_reason_for_single_route() -> None:
    rec = recommend([stats(0, severe=3, high=7)])
    assert rec.reason == "Only route: 3 severe mi, 7 high mi"


def test_recommend_rejects_empty_input() -> None:
    with pytest.raises(ValueError):
        recommend([])


def test_end_to_end_from_segments() -> None:
    a = route_stats(0, HOUR, [seg(25, L), seg(25, S), seg(10, L)])
    b = route_stats(1, HOUR + 12 * 60, [seg(25, M), seg(25, H), seg(12, L)])
    rec = recommend([a, b])
    assert rec.route_id == 1
    assert rec.reason == "0 severe mi vs 25, 12 min slower"
