import math

import pytest

from risk import RiskLevel, classify

L, M, H, S, NT = (
    RiskLevel.LOW,
    RiskLevel.MODERATE,
    RiskLevel.HIGH,
    RiskLevel.SEVERE,
    RiskLevel.NO_TRAVEL,
)
EPS = 0.001
LIGHT_LOAD = 10_000


def level(wind: float = 0, rain: float = 0, snow: float = 0, load: float = LIGHT_LOAD) -> RiskLevel:
    return classify(wind, rain, snow, load)[0]


# --- Wind: <25 | 25–<35 | 35–<45 | 45–<55 | ≥55 (lower bound inclusive) ---
@pytest.mark.parametrize(
    ("wind", "expected"),
    [
        (0, L),
        (25 - EPS, L),
        (25, M),
        (35 - EPS, M),
        (35, H),
        (45 - EPS, H),
        (45, S),
        (55 - EPS, S),
        (55, NT),
        (120, NT),
    ],
)
def test_wind_boundaries(wind: float, expected: RiskLevel) -> None:
    assert level(wind=wind) == expected


# --- Rain: <0.10 | 0.10–<0.25 | 0.25–<0.50 | 0.50–≤1.00 | >1.00 ---
@pytest.mark.parametrize(
    ("rain", "expected"),
    [
        (0, L),
        (0.10 - EPS, L),
        (0.10, M),
        (0.25 - EPS, M),
        (0.25, H),
        (0.50 - EPS, H),
        (0.50, S),
        (1.00, S),
        (1.00 + EPS, NT),
        (5.0, NT),
    ],
)
def test_rain_boundaries(rain: float, expected: RiskLevel) -> None:
    assert level(rain=rain) == expected


# --- Snow: <0.5 | 0.5–<1.0 | 1.0–<2.0 | 2.0–≤3.0 | >3.0 ---
@pytest.mark.parametrize(
    ("snow", "expected"),
    [
        (0, L),
        (0.5 - EPS, L),
        (0.5, M),
        (1.0 - EPS, M),
        (1.0, H),
        (2.0 - EPS, H),
        (2.0, S),
        (3.0, S),
        (3.0 + EPS, NT),
        (10.0, NT),
    ],
)
def test_snow_boundaries(snow: float, expected: RiskLevel) -> None:
    assert level(snow=snow) == expected


# --- Load overrides ---
@pytest.mark.parametrize(
    ("wind", "load", "expected"),
    [
        # Wind ≥55 → No Travel for any load.
        (55, 0, NT),
        (55, 120_000, NT),
        # Wind 45–<55 with load >30,000 → No Travel.
        (45, 30_000, S),
        (45, 30_000 + 1, NT),
        (55 - EPS, 30_000, S),
        (55 - EPS, 30_000 + 1, NT),
        (45 - EPS, 30_000 + 1, H),  # below 45 the 30k rule does not apply
        # Wind 35–<45 with load >40,000 → Severe.
        (35, 40_000, H),
        (35, 40_000 + 1, S),
        (45 - EPS, 40_000, H),
        (45 - EPS, 40_000 + 1, S),
        (35 - EPS, 120_000, M),  # below 35 no override applies
        # Heaviest load in the 45–<55 band is No Travel, not just Severe.
        (45, 40_000 + 1, NT),
        # Heavy load alone with calm wind changes nothing.
        (0, 120_000, L),
    ],
)
def test_load_overrides(wind: float, load: float, expected: RiskLevel) -> None:
    assert level(wind=wind, load=load) == expected


# --- Max across conditions ---
def test_level_is_max_across_conditions() -> None:
    assert level(wind=10, rain=0.30, snow=0.6) == H


def test_override_combines_with_other_conditions_via_max() -> None:
    # Wind 40 + 45k lb → Severe; rain >1.00 → No Travel wins.
    assert level(wind=40, rain=1.5, load=45_000) == NT
    # Wind 40 + 45k lb → Severe beats Moderate snow.
    assert level(wind=40, snow=0.7, load=45_000) == S


# --- Reasons ---
def test_low_has_a_reason() -> None:
    lvl, reasons = classify(5, 0, 0, LIGHT_LOAD)
    assert lvl == L
    assert reasons == ["All conditions below Moderate thresholds"]


def test_reasons_only_include_rules_at_final_level() -> None:
    lvl, reasons = classify(10, 0.30, 0.6, LIGHT_LOAD)
    assert lvl == H
    assert reasons == ["Rain 0.3 in/hr ≥ 0.25 → High"]


def test_tied_conditions_report_every_triggering_rule() -> None:
    _, reasons = classify(47, 0.6, 2.5, LIGHT_LOAD)
    assert reasons == [
        "Wind 47 mph ≥ 45 → Severe",
        "Rain 0.6 in/hr ≥ 0.5 → Severe",
        "Snow 2.5 in/hr ≥ 2 → Severe",
    ]


def test_exclusive_no_travel_reason_uses_strict_operator() -> None:
    _, reasons = classify(0, 1.2, 0, LIGHT_LOAD)
    assert reasons == ["Rain 1.2 in/hr > 1 → No Travel"]


def test_override_reason_names_load_rule() -> None:
    lvl, reasons = classify(48, 0, 0, 35_000)
    assert lvl == NT
    assert reasons == ["Load 35,000 lb > 30,000 with wind 48 mph (45–<55) → No Travel"]


# --- Input validation ---
@pytest.mark.parametrize(
    "args",
    [
        (-1, 0, 0, 0),
        (0, -0.1, 0, 0),
        (0, 0, -0.1, 0),
        (0, 0, 0, -1),
        (math.nan, 0, 0, 0),
        (0, math.inf, 0, 0),
    ],
)
def test_rejects_negative_or_non_finite_inputs(args: tuple[float, float, float, float]) -> None:
    with pytest.raises(ValueError):
        classify(*args)


def test_level_labels() -> None:
    assert [lvl.label for lvl in RiskLevel] == ["Low", "Moderate", "High", "Severe", "No Travel"]
    assert [int(lvl) for lvl in RiskLevel] == [0, 1, 2, 3, 4]
