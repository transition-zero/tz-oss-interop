"""The investment periods of a plan: one for each year that its slices fall in."""

from __future__ import annotations

from datetime import date

import polars as pl

from interop.plugins.shared.power_systems_investments_schema import SeriesDocument

_FIRST_MONTH = 1
_FIRST_DAY = 1
_LAST_MONTH = 12
_LAST_DAY = 31


def convert_year_key(key: str) -> str:
    """A year as the plan states it, so that ``"2030.0"`` and ``"2030"`` are the same year."""
    try:
        return str(int(float(key)))
    except ValueError:
        return key


def build_periods(years: list[int]) -> pl.DataFrame:
    """One investment period for each year, each running that whole year."""
    return pl.DataFrame(
        [
            {
                SeriesDocument.START: date(year, _FIRST_MONTH, _FIRST_DAY).isoformat(),
                SeriesDocument.END: date(year, _LAST_MONTH, _LAST_DAY).isoformat(),
            }
            for year in sorted(set(years))
        ]
    )
