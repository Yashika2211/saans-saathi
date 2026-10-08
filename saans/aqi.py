"""CPCB National Air Quality Index (NAQI) sub-index for PM2.5 and PM10.

NAQI is officially computed on 24-hour averages. We apply the same breakpoints to
hourly forecast concentrations, so every value here is labelled "AQI (est.)".

Concentrations are rounded to whole µg/m³ before lookup, which is how the published
integer breakpoint table (0-30, 31-60, ...) is meant to be read. Above the last
published breakpoint the table is open-ended; we use the common convention of
extending the last band by the width of the band before it, and cap at 500.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

AQI_LABEL = "AQI (est.)"

# (conc_lo, conc_hi, index_lo, index_hi), µg/m³
PM25_BREAKPOINTS = (
    (0, 30, 0, 50),
    (31, 60, 51, 100),
    (61, 90, 101, 200),
    (91, 120, 201, 300),
    (121, 250, 301, 400),
    (251, 380, 401, 500),
)

PM10_BREAKPOINTS = (
    (0, 50, 0, 50),
    (51, 100, 51, 100),
    (101, 250, 101, 200),
    (251, 350, 201, 300),
    (351, 430, 301, 400),
    (431, 510, 401, 500),
)


@dataclass(frozen=True)
class Category:
    name: str
    lo: int
    hi: int
    color: str  # CPCB colour scale


CATEGORIES = (
    Category("Good", 0, 50, "#00B050"),
    Category("Satisfactory", 51, 100, "#92D050"),
    Category("Moderate", 101, 200, "#FFFF00"),
    Category("Poor", 201, 300, "#FF9900"),
    Category("Very Poor", 301, 400, "#FF0000"),
    Category("Severe", 401, 500, "#C00000"),
)


def _round_half_up(x: float) -> int:
    return int(math.floor(x + 0.5))


def sub_index(conc: float | None, table) -> int | None:
    if conc is None:
        return None
    c = max(0, _round_half_up(conc))
    for b_lo, b_hi, i_lo, i_hi in table:
        if b_lo <= c <= b_hi:
            return _round_half_up(i_lo + (i_hi - i_lo) / (b_hi - b_lo) * (c - b_lo))
    return 500


def pm25_index(conc: float | None) -> int | None:
    return sub_index(conc, PM25_BREAKPOINTS)


def pm10_index(conc: float | None) -> int | None:
    return sub_index(conc, PM10_BREAKPOINTS)


def aqi_est(pm25: float | None, pm10: float | None) -> int | None:
    """Hourly AQI (est.): the worse of the PM2.5 and PM10 sub-indices."""
    values = [v for v in (pm25_index(pm25), pm10_index(pm10)) if v is not None]
    return max(values) if values else None


def category(aqi: int | None) -> Category | None:
    if aqi is None:
        return None
    for cat in CATEGORIES:
        if aqi <= cat.hi:
            return cat
    return CATEGORIES[-1]
