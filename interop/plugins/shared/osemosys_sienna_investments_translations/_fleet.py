"""The base system components that a candidate stands for: ExistingDevices, RetirementPotential.

A candidate adds to the components of the base system that share its category and its
location. A component leaves service in the first year after the base year in which the
residual capacity of its technology is zero. The model states no build year.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.constants import Framework
from interop.plugins.shared.osemosys_canonical.constants import (
    TECHNOLOGY,
    YEAR,
    AnnotationColumn,
)
from interop.plugins.shared.osemosys_sienna_constants import (
    TECHNOLOGY_COUNTED_NOUN,
    SupplyParameter,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._columns import (
    CANDIDATE_NAME,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._plan import (
    InvestmentPlan,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._yearly import (
    TECHNOLOGY_KEYS,
    read_yearly_values,
)
from interop.plugins.shared.pypsa_sienna_investments_translations import (
    OSEMOSYS_TO_SIENNA_INVESTMENTS,
    CandidateTechnology,
    InvestmentsSource,
    build_existing_fleet_source_table,
)
from interop.plugins.shared.sienna_constants import SIENNA_NAME_COLUMN, SiennaComponent

# What the shared retirement rule calls the year that a device leaves service.
_RETIREMENT_YEAR = "retirement_year"
_RESIDUAL = SupplyParameter.RESIDUAL_CAPACITY.value
_NO_CATEGORY = ""

FLEET_SOURCE = InvestmentsSource(
    framework=Framework.OSEMOSYS,
    pipeline=OSEMOSYS_TO_SIENNA_INVESTMENTS,
    component=TECHNOLOGY,
    display=TECHNOLOGY,
    plural=TECHNOLOGY_COUNTED_NOUN,
    attribute_names={_RETIREMENT_YEAR: f"first year with no {_RESIDUAL}"},
    retirement_derivation=(
        "the first year after the earliest year in scope in which the residual_capacity of "
        "the technology of the device is zero"
    ),
    retirement_cost_note=(
        "RetirementPotential requires a retirement cost and OSeMOSYS prices no retirement, so "
        "retiring a device costs nothing"
    ),
)


@dataclass(frozen=True)
class FleetFamily:
    """The candidates of one type, and every member that a base system component of it names.

    Both tables hold `candidate_name`, `region`, `technology`, `category` and `location`. The
    technology of a member is the one whose residual capacity the component holds.
    """

    component_type: str
    device_class: str
    candidates: pl.DataFrame
    members: pl.DataFrame
    base_types: Sequence[SiennaComponent]


def build_fleet_table(
    state: State, plan: InvestmentPlan, families: Sequence[FleetFamily]
) -> pl.DataFrame:
    """One row for each candidate that has a fleet in the base system."""
    return pl.concat([_build_family_fleet(state, plan, family) for family in families])


def _build_family_fleet(state: State, plan: InvestmentPlan, family: FleetFamily) -> pl.DataFrame:
    devices = family.members.filter(
        pl.col(CANDIDATE_NAME).is_in(sorted(_list_base_names(state, family.base_types)))
    )
    groups = _build_groups(devices)
    retired = _read_retirement_years(state, plan, devices)
    return build_existing_fleet_source_table(
        _list_candidates(family), groups, build_years={}, retirement_years=retired
    )


def _list_base_names(state: State, types: Collection[SiennaComponent]) -> set[str]:
    names: set[str] = set()
    for component in types:
        table = state.destination_tables.get(component)
        if table is not None:
            names |= set(table[SIENNA_NAME_COLUMN].to_list())
    return names


def _build_groups(devices: pl.DataFrame) -> dict[tuple[str, str | None], list[str]]:
    groups: dict[tuple[str, str | None], list[str]] = {}
    for name, category, location in (
        devices.sort(CANDIDATE_NAME)
        .select(CANDIDATE_NAME, AnnotationColumn.CATEGORY, AnnotationColumn.LOCATION)
        .iter_rows()
    ):
        groups.setdefault((category or _NO_CATEGORY, location), []).append(name)
    return groups


def _read_retirement_years(
    state: State, plan: InvestmentPlan, devices: pl.DataFrame
) -> dict[str, int]:
    keys = devices.select(TECHNOLOGY_KEYS).unique()
    later = read_yearly_values(state, _RESIDUAL, keys, plan.years).filter(
        (pl.col(YEAR) > plan.base_year) & (pl.col(_RESIDUAL) <= 0)
    )
    first = later.group_by(TECHNOLOGY_KEYS).agg(pl.col(YEAR).min())
    named = devices.join(first, on=TECHNOLOGY_KEYS).select(CANDIDATE_NAME, YEAR)
    return dict(named.iter_rows())


def _list_candidates(family: FleetFamily) -> list[CandidateTechnology]:
    return [
        CandidateTechnology(
            name=name,
            component_type=family.component_type,
            device_class=family.device_class,
            carrier=category or _NO_CATEGORY,
            region=location,
        )
        for name, category, location in family.candidates.select(
            CANDIDATE_NAME, AnnotationColumn.CATEGORY, AnnotationColumn.LOCATION
        ).iter_rows()
    ]
