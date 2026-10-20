"""The years that a portfolio plans over, with the units of the model and its operations mode."""

from __future__ import annotations

from dataclasses import dataclass

from interop.core.pipeline import State
from interop.plugins.shared.osemosys_sienna_translations import (
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
    """One year of the plan, with the representative days of that year."""
    return OperationsYear(year, plan.units, build_calendar(state, year), plan.mode)
