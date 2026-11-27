"""What a technology costs, what it emits and what bounds its activity, for each of its modes.

A Sienna generator states what one megawatt hour of its electricity costs, and its record
states what one megawatt of its capacity costs to build and to keep. A plant that draws its
fuel from a bus pays for that fuel at the bus, so the cost and the emission rates of such a
plant are the `own_` fields of its record, which hold neither.

A value with no year holds in every year of the model, because a Sienna generator states one
cost and no cost for one year. A value that the record keys by the year holds in that year
alone.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, NamedTuple

import polars as pl

from interop.core.extensions import GeneratorExtension, OperatingMode
from interop.plugins.shared.constants import (
    EXTENSIONS_PREFIX,
    UNIT_DOLLARS_PER_MW,
    UNIT_DOLLARS_PER_MW_YEAR,
    UNIT_DOLLARS_PER_MWH,
    UNIT_MWH,
    UNIT_PER_UNIT,
    UNIT_TONNES_PER_MWH,
    UNIT_YEARS,
)
from interop.plugins.shared.osemosys_canonical.constants import (
    OPERATING_MODE,
    POLLUTANT,
    REGION,
    TECHNOLOGY,
    VALUE_COL,
    YEAR,
)
from interop.plugins.shared.osemosys_sienna_constants import (
    ActivityParameter,
    InvestmentParameter,
    SupplyParameter,
)
from interop.plugins.shared.sienna_osemosys_translations.generator_columns import (
    AVAILABILITY,
    COST_ATTRIBUTE,
    HELD_MODE,
    RECORD_AVAILABILITY_ATTRIBUTE,
    SOURCE_COMPONENT,
    VARIABLE_COST_MWH,
)
from interop.plugins.shared.sienna_osemosys_translations.generator_flows import (
    PARAMETER,
    SOURCE_ATTRIBUTE,
)
from interop.plugins.shared.sienna_osemosys_translations.generator_modes import (
    list_mode_records,
)
from interop.plugins.shared.sienna_osemosys_translations.generators import GeneratorSources

# The unit that an event states for the value of the row.
UNIT = "unit"

# The record fields that the costs, the rates and the bounds of a technology come from.
VALUE_MAPPED_FIELDS = (
    "own_marginal_cost",
    "own_emission_rates_t_per_mwh",
    "emission_rates_t_per_mwh",
    "fom_charge_per_mw_year",
    "overnight_cost_per_mw",
    "lifetime_years",
    "e_sum_min",
    "e_sum_max",
    "e_sum_min_horizon",
    "e_sum_max_horizon",
    "operating_modes",
)

VALUES_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    REGION: pl.Utf8,
    TECHNOLOGY: pl.Utf8,
    PARAMETER: pl.Utf8,
    OPERATING_MODE: pl.Utf8,
    POLLUTANT: pl.Utf8,
    YEAR: pl.Int64,
    VALUE_COL: pl.Float64,
    SOURCE_COMPONENT: pl.Utf8,
    SOURCE_ATTRIBUTE: pl.Utf8,
    UNIT: pl.Utf8,
}


class _Value(NamedTuple):
    """One value of one technology. `year` is None where the value holds in every year."""

    parameter: str
    value: float
    attribute: str
    unit: str
    mode: str | None = None
    pollutant: str | None = None
    year: int | None = None


class _Yearly(NamedTuple):
    """One record field that states a value for each year, and the parameter that holds it."""

    field: str
    parameter: str
    unit: str


_ANNUAL_LIMITS = (
    _Yearly("e_sum_min", SupplyParameter.ACTIVITY_LOWER_LIMIT, UNIT_MWH),
    _Yearly("e_sum_max", SupplyParameter.ACTIVITY_UPPER_LIMIT, UNIT_MWH),
)
_HORIZON_LIMITS = (
    _Yearly("e_sum_min_horizon", ActivityParameter.MODEL_PERIOD_LOWER_LIMIT, UNIT_MWH),
    _Yearly("e_sum_max_horizon", ActivityParameter.MODEL_PERIOD_UPPER_LIMIT, UNIT_MWH),
)
_CAPACITY_VALUES = (
    _Yearly("fom_charge_per_mw_year", SupplyParameter.FIXED_COST, UNIT_DOLLARS_PER_MW_YEAR),
    _Yearly("overnight_cost_per_mw", InvestmentParameter.CAPITAL_COST, UNIT_DOLLARS_PER_MW),
    _Yearly("lifetime_years", InvestmentParameter.LIFETIME, UNIT_YEARS),
)
_MODE_BOUNDS = (
    _Yearly("activity_max", ActivityParameter.BY_MODE_UPPER_LIMIT, UNIT_MWH),
    _Yearly("activity_min", ActivityParameter.BY_MODE_LOWER_LIMIT, UNIT_MWH),
    _Yearly("activity_decrease_max", ActivityParameter.DECREASE_BY_MODE_LIMIT, UNIT_PER_UNIT),
)
_MODES_FIELD = "operating_modes"
_OWN_COST_FIELD = "own_marginal_cost"
_COST_FIELD = "variable_cost"
_RATES_FIELD = "emission_rates"


def build_generator_values(sources: GeneratorSources) -> pl.DataFrame:
    """One row for each cost, each emission rate and each bound of each technology."""
    rows = [
        _build_row(row, value)
        for row in sources.table.iter_rows(named=True)
        for value in _list_values(
            row, sources.records.get_fields(row[TECHNOLOGY], VALUE_MAPPED_FIELDS)
        )
    ]
    return pl.DataFrame(rows, schema=VALUES_SCHEMA)


def _build_row(generator: dict[str, Any], value: _Value) -> dict[str, Any]:
    return {
        REGION: generator[REGION],
        TECHNOLOGY: generator[TECHNOLOGY],
        PARAMETER: value.parameter,
        OPERATING_MODE: value.mode,
        POLLUTANT: value.pollutant,
        YEAR: value.year,
        VALUE_COL: value.value,
        SOURCE_COMPONENT: generator[SOURCE_COMPONENT],
        SOURCE_ATTRIBUTE: value.attribute,
        UNIT: value.unit,
    }


def _list_values(generator: dict[str, Any], record: GeneratorExtension) -> Iterator[_Value]:
    held = str(generator[HELD_MODE])
    yield from _list_held_cost(generator, record, held)
    yield from _list_held_rates(record, held)
    yield from _list_availability(generator)
    yield from _list_record_values(record, _CAPACITY_VALUES)
    yield from _list_record_values(record, _HORIZON_LIMITS)
    yield from _list_yearly_values(record, _ANNUAL_LIMITS)
    for mode in list_mode_records(record):
        yield from _list_mode_values(mode, held)


# --- the mode that the generator runs -------------------------------------------


def _list_held_cost(
    generator: dict[str, Any], record: GeneratorExtension, held: str
) -> Iterator[_Value]:
    """The cost of a plant that draws its fuel from a bus holds no price of that fuel."""
    own = record.own_marginal_cost
    stated = own if own is not None else generator[VARIABLE_COST_MWH]
    if stated is None:
        return
    attribute = (
        generator[COST_ATTRIBUTE] if own is None else f"{EXTENSIONS_PREFIX}{_OWN_COST_FIELD}"
    )
    yield _Value(
        SupplyParameter.VARIABLE_OPERATION_COST,
        stated,
        attribute,
        UNIT_DOLLARS_PER_MWH,
        mode=held,
    )


def _list_held_rates(record: GeneratorExtension, held: str) -> Iterator[_Value]:
    """The rates of a plant that draws its fuel from a bus hold no emission of that fuel."""
    own = record.own_emission_rates_t_per_mwh
    field = "own_emission_rates_t_per_mwh" if own is not None else "emission_rates_t_per_mwh"
    rates = own if own is not None else record.emission_rates_t_per_mwh
    yield from _list_rates(rates, held, f"{EXTENSIONS_PREFIX}{field}")


def _list_availability(generator: dict[str, Any]) -> Iterator[_Value]:
    """Only a technology that no Sienna component holds states a limit on the energy of a
    year."""
    stated = generator[AVAILABILITY]
    if stated is not None:
        yield _Value(
            SupplyParameter.AVAILABILITY_FACTOR,
            stated,
            RECORD_AVAILABILITY_ATTRIBUTE,
            UNIT_PER_UNIT,
        )


# --- the values that the record states ------------------------------------------


def _list_record_values(
    record: GeneratorExtension, stated: tuple[_Yearly, ...]
) -> Iterator[_Value]:
    """One value of the record that holds over the whole model."""
    for field in stated:
        value = getattr(record, field.field)
        if value is not None:
            yield _Value(field.parameter, value, f"{EXTENSIONS_PREFIX}{field.field}", field.unit)


def _list_yearly_values(
    record: GeneratorExtension, stated: tuple[_Yearly, ...]
) -> Iterator[_Value]:
    """One value of the record for each year that it names."""
    for field in stated:
        by_year = getattr(record, field.field) or {}
        for year, value in sorted(by_year.items()):
            attribute = f"{EXTENSIONS_PREFIX}{field.field}.{year}"
            yield _Value(field.parameter, value, attribute, field.unit, year=year)


# --- the values that each other mode states -------------------------------------


def _list_mode_values(mode: OperatingMode, held: str) -> Iterator[_Value]:
    """The bounds of every mode, and the cost and the rates of a mode that no field holds."""
    yield from _list_mode_bounds(mode)
    if mode.mode == held:
        return
    if mode.variable_cost is not None:
        attribute = _build_mode_attribute(mode.mode, _COST_FIELD)
        yield _Value(
            SupplyParameter.VARIABLE_OPERATION_COST,
            mode.variable_cost,
            attribute,
            UNIT_DOLLARS_PER_MWH,
            mode=mode.mode,
        )
    yield from _list_rates(
        mode.emission_rates, mode.mode, _build_mode_attribute(mode.mode, _RATES_FIELD)
    )


def _list_mode_bounds(mode: OperatingMode) -> Iterator[_Value]:
    for field in _MODE_BOUNDS:
        by_year = getattr(mode, field.field) or {}
        for year, value in sorted(by_year.items()):
            attribute = f"{_build_mode_attribute(mode.mode, field.field)}.{year}"
            yield _Value(field.parameter, value, attribute, field.unit, mode=mode.mode, year=year)


def _list_rates(rates: dict[str, float] | None, mode: str, attribute: str) -> Iterator[_Value]:
    for pollutant, rate in sorted((rates or {}).items()):
        yield _Value(
            SupplyParameter.EMISSION_RATE,
            rate,
            f"{attribute}.{pollutant}",
            UNIT_TONNES_PER_MWH,
            mode=mode,
            pollutant=pollutant,
        )


def _build_mode_attribute(mode: str, field: str) -> str:
    return f"{EXTENSIONS_PREFIX}{_MODES_FIELD}.{mode}.{field}"
