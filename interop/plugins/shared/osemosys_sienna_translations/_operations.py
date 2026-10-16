"""The model year that an operations system holds, with its units and its calendar."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Literal, Protocol

from interop.core.pipeline import State
from interop.plugins.shared.osemosys_sienna_translations._calendar import Calendar
from interop.plugins.shared.osemosys_sienna_translations._canonical import list_model_years
from interop.plugins.shared.osemosys_sienna_translations._units import ModelUnits
from interop.ports.errors import UserInputError


@dataclass(frozen=True)
class OperationsYear:
    year: int
    units: ModelUnits
    calendar: Calendar


class OperationsMapping(Protocol):
    """One component group of the operations step, which runs inside it and not alone."""

    step_name: ClassVar[str]

    def map_components(self, state: State, operations: OperationsYear) -> None: ...


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
