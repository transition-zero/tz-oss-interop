"""Reads that each component group needs for a table of technologies of the operations year."""

from __future__ import annotations

import logging

import polars as pl

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.osemosys_canonical.constants import (
    OPERATING_MODE,
    REGION,
    TECHNOLOGY,
    VALUE_COL,
    AnnotationColumn,
)
from interop.plugins.shared.osemosys_sienna_constants import (
    OSEMOSYS_TO_SIENNA_PIPELINE,
    TECHNOLOGIES_LABEL,
    TECHNOLOGY_COUNTED_NOUN,
    WHOLE_CAPACITY,
    SupplyParameter,
)
from interop.plugins.shared.osemosys_sienna_translations._canonical import (
    read_parameter,
    read_parameter_with_defaults,
)
from interop.plugins.shared.osemosys_sienna_translations._events import build_osemosys_field
from interop.plugins.shared.osemosys_sienna_translations._generator_columns import (
    FUEL_TYPE,
    PRIME_MOVER,
    RESIDUAL_CAPACITY,
    SIENNA_TYPE,
    TECHNOLOGY_NAME,
)
from interop.plugins.shared.osemosys_sienna_user_mappings import OsemosysSiennaCarrierMappings
from interop.plugins.shared.sienna_carrier_targets import (
    CarrierTarget,
    PrimeMoverTarget,
    ThermalTarget,
)
from interop.plugins.shared.sienna_constants import SIENNA_NAME_COLUMN, SiennaComponent
from interop.plugins.shared.warning_text import name_a_few
from interop.ports.outbound.reporting import EventKind, TranslationEvent

log = logging.getLogger(__name__)

# The column of the availability factor, and of the variable cost, of each technology.
AVAILABILITY_FACTOR = "availability_factor"
VARIABLE_COST = "variable_cost"

_KEYS = [REGION, TECHNOLOGY]
_NO_COST = 0.0
_EACH_TIMESLICE = "each timeslice"
_CAPACITY_FACTOR_NOTE = (
    "the operations system applies no capacity_factor to a storage or a line, so the share of "
    "the capacity that the technology can use in each timeslice is lost"
)
_TARGET_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    AnnotationColumn.CATEGORY: pl.Utf8,
    SIENNA_TYPE: pl.Utf8,
    PRIME_MOVER: pl.Utf8,
    FUEL_TYPE: pl.Utf8,
}


def enrich_residual_capacity(state: State, year: int, technologies: pl.DataFrame) -> pl.DataFrame:
    """The `residual_capacity` of each technology at the year, in the unit of the model."""
    stated = read_parameter_with_defaults(
        state, SupplyParameter.RESIDUAL_CAPACITY, year, technologies.select(_KEYS)
    ).select(*_KEYS, pl.col(VALUE_COL).fill_null(0.0).alias(RESIDUAL_CAPACITY))
    return technologies.join(stated, on=_KEYS, how="left")


def read_availability_factors(state: State, year: int, keys: pl.DataFrame) -> pl.DataFrame:
    """`keys` holds region and technology; a technology that states no factor takes 1."""
    stated = read_parameter_with_defaults(state, SupplyParameter.AVAILABILITY_FACTOR, year, keys)
    factor = pl.col(VALUE_COL).cast(pl.Float64).fill_null(WHOLE_CAPACITY)
    return stated.select(*_KEYS, factor.alias(AVAILABILITY_FACTOR))


def read_variable_costs(state: State, year: int, keys: pl.DataFrame) -> pl.DataFrame:
    """`keys` holds region, technology and mode; a mode that states no cost takes 0."""
    stated = read_parameter_with_defaults(
        state, SupplyParameter.VARIABLE_OPERATION_COST, year, keys
    )
    cost = pl.col(VALUE_COL).cast(pl.Float64).fill_null(_NO_COST)
    return stated.select(*_KEYS, OPERATING_MODE, cost.alias(VARIABLE_COST))


def enrich_targets(
    technologies: pl.DataFrame, mappings: OsemosysSiennaCarrierMappings
) -> pl.DataFrame:
    """The Sienna type, prime mover and fuel that the `carriers:` row of each category names."""
    categories = technologies[AnnotationColumn.CATEGORY].drop_nulls().unique().sort().to_list()
    rows = [_build_target_row(category, mappings.find_mapping(category)) for category in categories]
    targets = pl.DataFrame(rows, schema=_TARGET_SCHEMA)
    return technologies.join(targets, on=AnnotationColumn.CATEGORY, how="left")


def build_no_carriers_row_note(category: str | None) -> str:
    """Why a technology with no carriers: row for its category has no Sienna type."""
    if category is None:
        return "the technology has no category, so no carriers: row gives it a Sienna type"
    return f"no carriers: row names the category {category!r}, so it has no Sienna type"


def report_unread_capacity_factors(
    state: State, year: int, technologies: pl.DataFrame, recorder: ScopedRecorder
) -> None:
    """Record NOT_MAPPED for each technology that states a capacity_factor below 1, and warn.

    `technologies` holds `region`, `technology` and the name of each in a report.
    """
    names = (
        read_parameter(state, SupplyParameter.CAPACITY_FACTOR, year)
        .filter(pl.col(VALUE_COL) != WHOLE_CAPACITY)
        .join(technologies.select(*_KEYS, TECHNOLOGY_NAME), on=_KEYS)[TECHNOLOGY_NAME]
        .unique()
        .sort()
        .to_list()
    )
    for name in names:
        recorder.append(
            TranslationEvent(
                kind=EventKind.NOT_MAPPED,
                sources=[
                    build_osemosys_field(SupplyParameter.CAPACITY_FACTOR, name, _EACH_TIMESLICE)
                ],
                note=_CAPACITY_FACTOR_NOTE,
            )
        )
    if names:
        log.warning(
            "%s: %d %s state a capacity_factor, which the operations system does not apply to a "
            "storage or a line. %s: %s",
            OSEMOSYS_TO_SIENNA_PIPELINE,
            len(names),
            TECHNOLOGY_COUNTED_NOUN,
            TECHNOLOGIES_LABEL,
            name_a_few(names),
        )


def list_bus_names(state: State) -> list[str]:
    """The name of each ACBus that the bus group wrote, which is the location it stands for."""
    buses = state.destination_tables.get(SiennaComponent.AC_BUS)
    return [] if buses is None else buses[SIENNA_NAME_COLUMN].to_list()


def _build_target_row(category: str, target: CarrierTarget | None) -> dict[str, str | None]:
    if target is None:
        return {AnnotationColumn.CATEGORY: category, SIENNA_TYPE: None}
    prime_mover = (
        target.sienna_prime_mover_type
        if isinstance(target, PrimeMoverTarget | ThermalTarget)
        else None
    )
    fuel = target.sienna_fuel_type if isinstance(target, ThermalTarget) else None
    return {
        AnnotationColumn.CATEGORY: category,
        SIENNA_TYPE: str(target.sienna_component_type),
        PRIME_MOVER: None if prime_mover is None else str(prime_mover),
        FUEL_TYPE: None if fuel is None else str(fuel),
    }
