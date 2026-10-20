"""The model year that an operations system holds, with its units and its calendar."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Literal, Protocol

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.osemosys_canonical.constants import YEAR
from interop.plugins.shared.osemosys_sienna_constants import OPERATIONS_YEAR_KEY
from interop.plugins.shared.osemosys_sienna_translations._calendar import Calendar
from interop.plugins.shared.osemosys_sienna_translations._canonical import list_model_years
from interop.plugins.shared.osemosys_sienna_translations._units import ModelUnits
from interop.ports.errors import UserInputError


@dataclass(frozen=True)
class OperationsYear:
    """`mode` is the operating mode whose values the operations system runs."""

    year: int
    units: ModelUnits
    calendar: Calendar
    mode: str


class OperationsMapping(Protocol):
    """One component group of the operations step, which runs inside it and not alone."""

    step_name: ClassVar[str]

    def map_components(self, state: State, operations: OperationsYear) -> None: ...


def set_operations_year(state: State, year: int) -> None:
    """Keep the operations year in the state, for a later step of the pipeline."""
    state.source_time_series[OPERATIONS_YEAR_KEY] = pl.LazyFrame({YEAR: [year]})


def require_operations_year(state: State) -> int:
    """The year that the operations step translated; a pipeline with no such step stops."""
    table = state.source_time_series.get(OPERATIONS_YEAR_KEY)
    if table is None:
        raise UserInputError(
            "The report of the parameters that no step applies needs the operations year. Put "
            "the step after osemosys_to_sienna_map_components in the pipeline."
        )
    return int(table.collect().item(0, YEAR))


def require_model_year(state: State, requested: int | Literal["earliest"]) -> int:
    """The requested year, or the earliest model year. Another year stops the run."""
    years = list_model_years(state)
    if isinstance(requested, str):
        if not years:
            raise UserInputError(
                "The parameter `year` is `earliest`, but the model states no year."
            )
        return years[0]
    if requested not in years:
        listed = ", ".join(str(year) for year in years) or "none"
        raise UserInputError(
            f"The parameter `year` is {requested}, which is not a year of the model. "
            f"The model years are: {listed}."
        )
    return requested
