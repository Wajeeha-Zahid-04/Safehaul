"""Checkpoint risk classification (spec §1 "Risk rules" and "Load overrides").

Pure functions, no I/O. A checkpoint's level is the maximum across wind, rain and snow
after load overrides are applied.
"""

import math
from dataclasses import dataclass
from enum import IntEnum


class RiskLevel(IntEnum):
    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def label(self) -> str:
        return self.name.replace("_", " ").title()


@dataclass(frozen=True)
class Band:
    """Values at or above `threshold` (strictly above if not `inclusive`) reach `level`."""

    threshold: float
    level: RiskLevel
    inclusive: bool = True


@dataclass(frozen=True)
class Scale:
    name: str
    unit: str
    bands: tuple[Band, ...]  # ordered from most to least severe


@dataclass(frozen=True)
class LoadOverride:
    """Wind in [wind_min, wind_max) with load strictly above `load_above_lb` -> `level`."""

    wind_min: float
    wind_max: float
    load_above_lb: float
    level: RiskLevel


WIND = Scale(
    "Wind",
    "mph",
    (
        Band(55, RiskLevel.NO_TRAVEL),
        Band(45, RiskLevel.SEVERE),
        Band(35, RiskLevel.HIGH),
        Band(25, RiskLevel.MODERATE),
    ),
)
RAIN = Scale(
    "Rain",
    "in/hr",
    (
        Band(1.00, RiskLevel.NO_TRAVEL, inclusive=False),
        Band(0.50, RiskLevel.SEVERE),
        Band(0.25, RiskLevel.HIGH),
        Band(0.10, RiskLevel.MODERATE),
    ),
)
SNOW = Scale(
    "Snow",
    "in/hr",
    (
        Band(3.0, RiskLevel.NO_TRAVEL, inclusive=False),
        Band(2.0, RiskLevel.SEVERE),
        Band(1.0, RiskLevel.HIGH),
        Band(0.5, RiskLevel.MODERATE),
    ),
)

# Wind >= 55 -> No Travel for any load is already covered by the WIND scale.
LOAD_OVERRIDES = (
    LoadOverride(45, 55, 30_000, RiskLevel.NO_TRAVEL),
    LoadOverride(35, 45, 40_000, RiskLevel.SEVERE),
)

LOW_REASON = "All conditions below Moderate thresholds"

Finding = tuple[RiskLevel, str]


def _band_finding(value: float, scale: Scale) -> Finding | None:
    for band in scale.bands:
        if value > band.threshold or (band.inclusive and value == band.threshold):
            op = "≥" if band.inclusive else ">"
            reason = (
                f"{scale.name} {value:g} {scale.unit} {op} {band.threshold:g} → {band.level.label}"
            )
            return band.level, reason
    return None


def _override_findings(wind_mph: float, load_lb: float) -> list[Finding]:
    return [
        (
            o.level,
            f"Load {load_lb:,.0f} lb > {o.load_above_lb:,.0f} with wind {wind_mph:g} mph "
            f"({o.wind_min:g}–<{o.wind_max:g}) → {o.level.label}",
        )
        for o in LOAD_OVERRIDES
        if o.wind_min <= wind_mph < o.wind_max and load_lb > o.load_above_lb
    ]


def _validate(**values: float) -> None:
    for name, value in values.items():
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"{name} must be a finite, non-negative number, got {value!r}")


def classify(
    wind_mph: float, rain_in_hr: float, snow_in_hr: float, load_lb: float
) -> tuple[RiskLevel, list[str]]:
    """Return the checkpoint's risk level and the rule(s) that set it."""
    _validate(wind_mph=wind_mph, rain_in_hr=rain_in_hr, snow_in_hr=snow_in_hr, load_lb=load_lb)

    findings = [
        finding
        for finding in (
            _band_finding(wind_mph, WIND),
            _band_finding(rain_in_hr, RAIN),
            _band_finding(snow_in_hr, SNOW),
        )
        if finding is not None
    ]
    findings += _override_findings(wind_mph, load_lb)

    if not findings:
        return RiskLevel.LOW, [LOW_REASON]

    level = max(level for level, _ in findings)
    return level, [reason for finding_level, reason in findings if finding_level == level]
