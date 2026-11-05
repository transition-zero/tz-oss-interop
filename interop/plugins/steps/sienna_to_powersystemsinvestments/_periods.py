"""The investment periods of a plan: one for each year that its slices fall in."""

from __future__ import annotations

from datetime import date

import polars as pl

from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.power_systems_investments_schema import SeriesDocument
from interop.plugins.shared.warning_text import name_a_few
from interop.plugins.steps.sienna_to_powersystemsinvestments._events import (
    PLAN,
    record_not_mapped,
    warn_step,
)

INVESTMENT_PERIODS = "InvestmentPeriods"
_FIRST_MONTH = 1
_FIRST_DAY = 1
_LAST_MONTH = 12
_LAST_DAY = 31

_GAP_NOTE = (
    "the model counts the operations of each investment period's own year only, while it "
    "amortises capital over the whole recovery period, so the years {years} between the "
    "periods carry no operating cost"
)
_GAP_WARNING = (
    "PowerSystemsInvestments counts the operations of each period's own year only, so the %d "
    "year(s) between the periods carry no operating cost: %s"
)


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


def report_gap_years(years: list[str], recorder: ScopedRecorder) -> None:
    """Record and warn the years between the periods, which the model gives no operations."""
    stated = {int(year) for year in years}
    span = range(min(stated), max(stated) + 1) if stated else range(0)
    gaps = [str(year) for year in span if year not in stated]
    if not gaps:
        return
    record_not_mapped(
        recorder,
        component=INVESTMENT_PERIODS,
        name=PLAN,
        field=SeriesDocument.PERIODS,
        value=years,
        derivation=_GAP_NOTE.format(years=", ".join(gaps)),
    )
    warn_step(_GAP_WARNING, len(gaps), name_a_few(gaps))
