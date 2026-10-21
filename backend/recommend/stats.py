"""Route stats + recommendation sort (spec §1 "Recommendation order", §2 `recommend/`).

Routes are ranked by the tuple (notravel_mi, severe_mi, high_mi, avg_score, duration), all
ascending. Each checkpoint owns the miles since the previous checkpoint, so its level is
attributed to that many miles.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from risk import RiskLevel

# Mile and score keys are compared after rounding so float noise in haversine sums can't
# decide a ranking that is really a tie (it falls through to the next key instead).
MILE_KEY_DECIMALS = 2
SCORE_KEY_DECIMALS = 4


@dataclass(frozen=True)
class ScoredSegment:
    miles: float
    level: RiskLevel


@dataclass(frozen=True)
class RouteStats:
    route_id: int
    distance_mi: float
    duration_s: float
    notravel_mi: float
    severe_mi: float
    high_mi: float
    avg_score: float  # mile-weighted mean of checkpoint scores (0-4)
    do_not_travel: bool  # route contains any No-Travel checkpoint


@dataclass(frozen=True)
class Recommendation:
    route_id: int
    ranked_ids: list[int]
    reason: str


def route_stats(route_id: int, duration_s: float, segments: Sequence[ScoredSegment]) -> RouteStats:
    distance_mi = sum(s.miles for s in segments)
    weighted = sum(s.miles * int(s.level) for s in segments)
    return RouteStats(
        route_id=route_id,
        distance_mi=distance_mi,
        duration_s=duration_s,
        notravel_mi=_miles_at(segments, RiskLevel.NO_TRAVEL),
        severe_mi=_miles_at(segments, RiskLevel.SEVERE),
        high_mi=_miles_at(segments, RiskLevel.HIGH),
        avg_score=weighted / distance_mi if distance_mi > 0 else 0.0,
        do_not_travel=any(s.level == RiskLevel.NO_TRAVEL for s in segments),
    )


def sort_key(stats: RouteStats) -> tuple[float, float, float, float, float, int]:
    """Spec order; route_id is a final tie-break so the result is deterministic."""
    return (
        round(stats.notravel_mi, MILE_KEY_DECIMALS),
        round(stats.severe_mi, MILE_KEY_DECIMALS),
        round(stats.high_mi, MILE_KEY_DECIMALS),
        round(stats.avg_score, SCORE_KEY_DECIMALS),
        stats.duration_s,
        stats.route_id,
    )


def rank(all_stats: Sequence[RouteStats]) -> list[RouteStats]:
    return sorted(all_stats, key=sort_key)


def recommend(all_stats: Sequence[RouteStats]) -> Recommendation:
    if not all_stats:
        raise ValueError("cannot recommend from zero routes")
    ranked = rank(all_stats)
    return Recommendation(
        route_id=ranked[0].route_id,
        ranked_ids=[s.route_id for s in ranked],
        reason=recommendation_reason(ranked),
    )


def recommendation_reason(ranked: Sequence[RouteStats]) -> str:
    """One-line reason for the top route, e.g. "0 severe mi vs 14, 12 min slower"."""
    best = ranked[0]
    if best.do_not_travel:
        return f"Do not travel: every route has No-Travel miles ({_mi(best.notravel_mi)} mi here)"
    if len(ranked) == 1:
        return f"Only route: {_mi(best.severe_mi)} severe mi, {_mi(best.high_mi)} high mi"

    timing = _timing(best, ranked)
    runner_up = ranked[1]
    deciding = _deciding_key(best, runner_up)
    if deciding is None:
        return "Tied with alternatives on risk and duration"
    if deciding == 0:
        return f"No No-Travel miles (vs {_mi(runner_up.notravel_mi)}), {timing}"
    if deciding in (1, 2):
        label = "severe" if deciding == 1 else "high"
        best_mi = best.severe_mi if deciding == 1 else best.high_mi
        other_mi = runner_up.severe_mi if deciding == 1 else runner_up.high_mi
        return f"{_mi(best_mi)} {label} mi vs {_mi(other_mi)}, {timing}"
    if deciding == 3:
        return f"Lowest avg risk ({best.avg_score:.2f} vs {runner_up.avg_score:.2f}), {timing}"
    return "Same risk as alternatives, fastest"


def _deciding_key(best: RouteStats, runner_up: RouteStats) -> int | None:
    """Index of the first sort criterion (0-4) that separates the top two routes."""
    for i, (a, b) in enumerate(zip(sort_key(best)[:5], sort_key(runner_up)[:5], strict=True)):
        if a != b:
            return i
    return None


def _timing(best: RouteStats, ranked: Sequence[RouteStats]) -> str:
    fastest_s = min(s.duration_s for s in ranked)
    slower_min = round((best.duration_s - fastest_s) / 60)
    return "fastest" if slower_min <= 0 else f"{slower_min} min slower"


def _miles_at(segments: Sequence[ScoredSegment], level: RiskLevel) -> float:
    return sum(s.miles for s in segments if s.level == level)


def _mi(miles: float) -> str:
    return f"{round(miles, 1):g}"
