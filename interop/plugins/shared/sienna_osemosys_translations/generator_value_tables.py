"""The canonical parameter table of each cost, each emission rate and each bound.

The canonical schema states the key columns of each parameter, so one writer serves them all:
it takes the columns that the schema names, and it writes one row for each year of the model
where the parameter has a year column and the value holds in every year.

A value that equals the default of its parameter needs no row, because OSeMOSYS reads the
default where a model states nothing. So a generator that costs nothing to run writes no
`VariableCost` row, and a rate of 0 writes no `EmissionActivityRatio` row.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import polars as pl

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.osemosys_canonical.constants import (
    REGION,
    TECHNOLOGY,
    VALUE_COL,
    YEAR,
)
from interop.plugins.shared.osemosys_canonical.schema import load_canonical_schema
from interop.plugins.shared.osemosys_sienna_constants import (
    ActivityParameter,
    InvestmentParameter,
    SupplyParameter,
)
from interop.plugins.shared.sienna_osemosys_translations.constants import NAME_SEPARATOR
from interop.plugins.shared.sienna_osemosys_translations.destination import (
    ParameterRows,
    set_parameter_table,
)
from interop.plugins.shared.sienna_osemosys_translations.events import (
    build_derived,
    build_osemosys_parameter,
    build_sienna_source,
)
from interop.plugins.shared.sienna_osemosys_translations.generator_flows import (
    PARAMETER,
    SOURCE_ATTRIBUTE,
)
from interop.plugins.shared.sienna_osemosys_translations.generator_values import (
    UNIT,
    build_generator_values,
)
from interop.plugins.shared.sienna_osemosys_translations.generators import (
    SOURCE_COMPONENT,
    GeneratorSources,
)

# Every parameter that a cost, an emission rate or a bound of a technology fills.
GENERATOR_VALUE_PARAMETERS: tuple[str, ...] = (
    SupplyParameter.VARIABLE_OPERATION_COST,
    SupplyParameter.FIXED_COST,
    InvestmentParameter.CAPITAL_COST,
    InvestmentParameter.LIFETIME,
    SupplyParameter.EMISSION_RATE,
    SupplyParameter.ACTIVITY_LOWER_LIMIT,
    SupplyParameter.ACTIVITY_UPPER_LIMIT,
    ActivityParameter.MODEL_PERIOD_LOWER_LIMIT,
    ActivityParameter.MODEL_PERIOD_UPPER_LIMIT,
    ActivityParameter.BY_MODE_UPPER_LIMIT,
    ActivityParameter.BY_MODE_LOWER_LIMIT,
    ActivityParameter.DECREASE_BY_MODE_LIMIT,
)

_DERIVATION = (
    "the value of the record, which already divides by the electricity output ratio of the "
    "technology"
)


def set_generator_value_tables(
    state: State, sources: GeneratorSources, years: Sequence[int], recorder: ScopedRecorder
) -> None:
    """Write the cost, the emission rate and the bound of each technology, over every year."""
    if sources.table.height == 0:
        return
    values = build_generator_values(sources)
    for parameter in GENERATOR_VALUE_PARAMETERS:
        stated = _list_stated(values, parameter)
        _set_table_with_rows(state, parameter, _list_rows(stated, parameter, years))
        _record_values(stated, parameter, recorder)


def _list_stated(values: pl.DataFrame, parameter: str) -> pl.DataFrame:
    """The rows of one parameter whose value the default of that parameter does not already
    state."""
    default = load_canonical_schema().parameters[parameter].default
    stated = values.filter(pl.col(PARAMETER) == parameter)
    if default is None:
        return stated
    return stated.filter(pl.col(VALUE_COL) != default)


def _list_rows(stated: pl.DataFrame, parameter: str, years: Sequence[int]) -> ParameterRows:
    """The key columns that the schema names, over the years that the row holds in."""
    columns = load_canonical_schema().parameters[parameter].column_names
    return [
        {**{column: _read_key(row, column, year) for column in columns}, VALUE_COL: row[VALUE_COL]}
        for row in stated.iter_rows(named=True)
        for year in _list_row_years(row, columns, years)
    ]


def _list_row_years(
    row: dict[str, Any], columns: Sequence[str], years: Sequence[int]
) -> list[int | None]:
    """A parameter with no year column gives one row, whose year no key column reads."""
    if YEAR not in columns:
        return [None]
    return [row[YEAR]] if row[YEAR] is not None else list(years)


def _read_key(row: dict[str, Any], column: str, year: int | None) -> Any:
    return year if column == YEAR else row[column]


def _record_values(stated: pl.DataFrame, parameter: str, recorder: ScopedRecorder) -> None:
    """One event for each value, and not one for each year that a value holds in."""
    for row in stated.iter_rows(named=True):
        source = build_sienna_source(
            row[SOURCE_COMPONENT],
            row[TECHNOLOGY],
            row[SOURCE_ATTRIBUTE],
            value=row[VALUE_COL],
            unit=row[UNIT],
        )
        destination = build_osemosys_parameter(
            parameter, _build_name(row, parameter), row[VALUE_COL], row[UNIT]
        )
        recorder.append(build_derived([source], [destination], _DERIVATION))


def _build_name(row: dict[str, Any], parameter: str) -> str:
    """A value is named by its region, its technology and each other key that the schema
    names."""
    columns = load_canonical_schema().parameters[parameter].column_names
    keys = [column for column in columns if column not in (REGION, TECHNOLOGY, YEAR)]
    parts = [row[REGION], row[TECHNOLOGY], *(str(row[column]) for column in keys)]
    return NAME_SEPARATOR.join(parts)


def _set_table_with_rows(state: State, parameter: str, rows: ParameterRows) -> None:
    if rows:
        set_parameter_table(state, parameter, rows)
