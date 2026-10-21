from dataclasses import dataclass


@dataclass(frozen=True)
class Weather:
    """Hourly conditions at one point, in the units the risk rules use."""

    wind_mph: float  # sustained, scored
    gust_mph: float  # shown, not scored (documented assumption)
    precip_in: float  # total precipitation, shown
    rain_in: float  # liquid rain, scored as "Rain in/hr"
    snow_in: float  # scored as "Snow in/hr"
