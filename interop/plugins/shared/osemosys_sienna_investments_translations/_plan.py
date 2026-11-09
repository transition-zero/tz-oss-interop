"""The years that a portfolio plans over, with the units of the model and its operations mode."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.osemosys_sienna_constants import CalendarHourCol, CalendarPeriodCol
from interop.plugins.shared.osemosys_sienna_translations import (
    Calendar,
    ModelUnits,
    OperationsYear,
    build_calendar,
    parse_units,
    read_operations_mode,
)
from interop.plugins.shared.osemosys_sienna_translations._canonical import list_model_years


@dataclass(frozen=True)
class InvestmentPlan:
    """The years in scope, in ascending order. The first is the year of the base system."""

    years: tuple[int, ...]
    units: ModelUnits
    mode: str

    @property
    def base_year(self) -> int:
        return self.years[0]

    @property
    def cost_year(self) -> int:
        """The year that each cost is quoted in: `units: currency_year`, else the base year."""
        return self.units.currency_year or self.base_year


def find_investment_plan(state: State) -> InvestmentPlan | None:
    """The plan over the years in `set/year`, or None when the model states no year."""
    years = list_model_years(state)
    if not years:
        return None
    return InvestmentPlan(tuple(years), parse_units(state), read_operations_mode(state))


def build_plan_year(state: State, plan: InvestmentPlan, year: int) -> OperationsYear:
    """One year of the plan, on the representative days of the base year, from 1 January of
    the year.

    The expansion weights every year by the representative periods of the base year, so the MW
    of each year must use the hours and the weights of those days to give back its demand.
    """
    calendar = build_calendar(state, plan.base_year)
    return OperationsYear(year, plan.units, _build_moved_calendar(calendar, plan, year), plan.mode)


def _build_moved_calendar(calendar: Calendar, plan: InvestmentPlan, year: int) -> Calendar:
    """The same hours and periods, from 1 January of `year`."""
    offset = _start_of(year) - _start_of(plan.base_year)
    return replace(
        calendar,
        hours=calendar.hours.with_columns(pl.col(CalendarHourCol.TIMESTAMP) + offset),
        periods=calendar.periods.with_columns(pl.col(CalendarPeriodCol.FIRST_TIMESTAMP) + offset),
    )


def _start_of(year: int) -> datetime:
    return datetime(year, 1, 1)
