"""The base of every sidecar record, and the shapes of the values that a record keys.

``interop/core/extensions.py`` holds the document and the kinds. This module holds what the
record models of every kind share, so a module of record models can use it without a cycle.
"""

from __future__ import annotations

from typing import TypeAlias

from pydantic import BaseModel, ConfigDict

# A value for each year, whose JSON key is the year as a string that must parse as an int.
ByYear: TypeAlias = dict[int, float]
# A flag for each year, keyed by the year.
FlagByYear: TypeAlias = dict[int, bool]
# A value for each fuel, keyed by the name of the fuel.
ByFuel: TypeAlias = dict[str, float]
# A value for each pollutant, keyed by the name of the pollutant.
ByPollutant: TypeAlias = dict[str, float]
# A value for each bus, keyed by the name of the bus.
ByBus: TypeAlias = dict[str, float]


class ExtensionRecord(BaseModel):
    """One component's record. ``name`` is the identifier in every framework."""

    model_config = ConfigDict(extra="forbid")

    name: str

    def has_any_value(self) -> bool:
        """Whether the record states anything, rather than only the name it is keyed by."""
        return bool(self.model_dump(exclude={"name"}, exclude_none=True))


class ExpansionExtension(ExtensionRecord):
    """What a candidate states that PyPSA's own expansion columns have no home for."""

    # MW. What one unit of a candidate is. PyPSA sizes a candidate by p_nom_max alone, so
    # the size of a single unit has no field there.
    unit_size_mw: float | None = None
    # yr. How long the plant runs. PyPSA has one lifetime and the capital recovery period
    # claims it, so this has no field there.
    technical_life_years: float | None = None
    # $/MW/yr. PyPSA's fom_cost is a charge for the whole modelled horizon, not a yearly
    # one, so a yearly charge has no field there.
    fom_charge_per_mw_year: float | None = None
    # The year the object leaves service, which PLEXOS states as a dated Units of zero.
    # PyPSA carries build_year on the component and nothing for the other end of its life.
    retirement_year: int | None = None
    # MW. PyPSA's p_nom_max and p_nom_min. Sienna states one rating and no build range, so a
    # candidate loses both without these.
    p_nom_max: float | None = None
    p_nom_min: float | None = None
    # $/MW. PyPSA Generator.overnight_cost. Sienna prices no build on an operations model.
    overnight_cost_per_mw: float | None = None
    # PyPSA Generator.discount_rate, which annuitises the build cost. No Sienna field.
    discount_rate: float | None = None
    # yr. PyPSA Generator.lifetime, the period the build cost annuitises over.
    lifetime_years: float | None = None
    # The year the object enters service. PyPSA carries build_year; Sienna carries nothing.
    build_year: int | None = None
