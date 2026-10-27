"""The values of each operating mode of a technology that its Sienna component does not run.

A component runs the modes that it holds: a generator and a line the operations mode, a
storage its charge mode and its discharge mode. The cost, the flows and the emissions of each
other mode, in the operations year, go to the `operating_modes` field of the extension record.
So do the bounds of each mode, held or not, in every year, and the emissions of a mode that a
storage, a line or a conversion runs, which no field of those holds. Each value is for one MWh
of the activity of the mode.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, NamedTuple

import polars as pl

from interop.core.extensions import OperatingMode
from interop.core.pipeline import State
from interop.plugins.shared.constants import (
    EXTENSIONS_PREFIX,
    UNIT_DOLLARS_PER_MWH,
    UNIT_MWH,
    UNIT_PER_UNIT,
    UNIT_TONNES_PER_MWH,
)
from interop.plugins.shared.osemosys_canonical.constants import (
    FUEL,
    OPERATING_MODE,
    POLLUTANT,
    REGION,
    TECHNOLOGY,
    VALUE_COL,
    YEAR,
    FlowParameter,
)
from interop.plugins.shared.osemosys_sienna_constants import ActivityParameter, SupplyParameter
from interop.plugins.shared.osemosys_sienna_translations._canonical import (
    read_parameter,
    read_parameter_all_years,
)
from interop.plugins.shared.osemosys_sienna_translations._events import (
    build_osemosys_field,
    build_sienna_field,
)
from interop.plugins.shared.osemosys_sienna_translations._operations import OperationsYear
from interop.plugins.shared.osemosys_sienna_translations._persisted import set_persisted_rows
from interop.plugins.shared.osemosys_sienna_translations._technology_values import (
    ValueOwners,
)
from interop.plugins.shared.osemosys_sienna_translations._units import (
    ModelUnits,
    express_converted,
)
from interop.ports.outbound.reporting import EventKind, TranslationEvent

OPERATING_MODES = "operating_modes"

_KEYS = [REGION, TECHNOLOGY]
_FIELD = "field"
_DETAIL = "detail"
_STATED = "stated"
_SCALED = "scaled"
_PARAMETER = "parameter"
_UNIT = "unit"
_VALUES = "mode_values"
_NO_VALUE = 0.0


class ModeValue(NamedTuple):
    """One parameter keyed by mode, the field of a mode that holds it, and how it converts.

    `detail` is the key column that keys the field, or None for one value. A bound holds in
    every year, so its detail is the year, and it holds for the modes that the component runs.
    """

    parameter: str
    field: str
    detail: str | None
    unit: str
    convert: Callable[[ModelUnits], Callable[[pl.Expr], pl.Expr] | None]
    is_bound: bool = False


def _no_conversion(_units: ModelUnits) -> None:
    return None


_MODE_VALUES = (
    ModeValue(
        SupplyParameter.VARIABLE_OPERATION_COST,
        "variable_cost",
        None,
        UNIT_DOLLARS_PER_MWH,
        lambda units: units.convert_cost_per_energy_to_dollars_per_mwh,
    ),
    ModeValue(
        FlowParameter.INPUT_ACTIVITY_RATIO, "input_ratios", FUEL, UNIT_PER_UNIT, _no_conversion
    ),
    ModeValue(
        FlowParameter.OUTPUT_ACTIVITY_RATIO, "output_ratios", FUEL, UNIT_PER_UNIT, _no_conversion
    ),
    ModeValue(
        SupplyParameter.EMISSION_RATE,
        "emission_rates",
        POLLUTANT,
        UNIT_TONNES_PER_MWH,
        lambda units: units.convert_emissions_per_energy_to_tonnes_per_mwh,
    ),
    ModeValue(
        ActivityParameter.BY_MODE_UPPER_LIMIT,
        "activity_max",
        YEAR,
        UNIT_MWH,
        lambda units: units.convert_energy_to_mwh,
        is_bound=True,
    ),
    ModeValue(
        ActivityParameter.BY_MODE_LOWER_LIMIT,
        "activity_min",
        YEAR,
        UNIT_MWH,
        lambda units: units.convert_energy_to_mwh,
        is_bound=True,
    ),
    ModeValue(
        ActivityParameter.DECREASE_BY_MODE_LIMIT,
        "activity_decrease_max",
        YEAR,
        UNIT_PER_UNIT,
        _no_conversion,
        is_bound=True,
    ),
)
# The values of a mode that a generator runs, which the generator holds itself.
GENERATOR_RUN_PARAMETERS = frozenset(
    {
        SupplyParameter.VARIABLE_OPERATION_COST,
        FlowParameter.INPUT_ACTIVITY_RATIO,
        FlowParameter.OUTPUT_ACTIVITY_RATIO,
        SupplyParameter.EMISSION_RATE,
    }
)
# The values of a mode that a storage, a line or a conversion runs: it states no emission rate.
LINK_RUN_PARAMETERS = GENERATOR_RUN_PARAMETERS - {SupplyParameter.EMISSION_RATE}
# The bounds of a mode, whose rows a record holds for each technology that it names.
MODE_BOUND_PARAMETERS: tuple[str, ...] = tuple(
    value.parameter for value in _MODE_VALUES if value.is_bound
)


@dataclass(frozen=True)
class OperatingModes:
    """One list of mode values for each technology, by `region` and `technology`."""

    table: pl.DataFrame

    def enrich(self, technologies: pl.DataFrame, keys: list[str] | None = None) -> pl.DataFrame:
        """`technologies` with the list of mode values of each, on `keys` or the default keys."""
        on = keys or _KEYS
        renamed = self.table.rename(dict(zip(_KEYS, on, strict=True)))
        return technologies.join(renamed, on=on, how="left")


def build_operating_modes(
    state: State,
    operations: OperationsYear,
    held: pl.DataFrame,
    run_parameters: frozenset[str] = GENERATOR_RUN_PARAMETERS,
) -> OperatingModes:
    """The mode values of each technology in `held`, which lists the modes that it runs.

    `held` holds `region`, `technology` and `operating_mode`. A mode that the component runs
    keeps out each value of `run_parameters`, which the component holds itself.
    """
    technologies = held.select(_KEYS).unique()
    rows = pl.concat(
        [
            _read_mode_rows(state, operations, technologies, held, value, run_parameters)
            for value in _MODE_VALUES
        ]
    )
    listed = rows.group_by(_KEYS).agg(
        pl.struct(_PARAMETER, OPERATING_MODE, _FIELD, _DETAIL, _STATED, _SCALED, _UNIT).alias(
            _VALUES
        )
    )
    return OperatingModes(listed)


def build_operating_mode_field(row: dict[str, Any]) -> list[OperatingMode] | None:
    """The `operating_modes` of one record, in the order of the modes."""
    by_mode: dict[str, dict[str, Any]] = {}
    for entry in row[_VALUES] or []:
        mode = by_mode.setdefault(entry[OPERATING_MODE], {})
        if entry[_DETAIL] is None:
            mode[entry[_FIELD]] = entry[_SCALED]
        else:
            mode.setdefault(entry[_FIELD], {})[entry[_DETAIL]] = entry[_SCALED]
    modes = [OperatingMode(mode=mode, **fields) for mode, fields in sorted(by_mode.items())]
    return modes or None


def build_mode_events(row: dict[str, Any], owners: ValueOwners) -> list[TranslationEvent]:
    """One VALUE_DERIVED for each value of a mode that the record of one row holds."""
    return [_build_event(row, entry, owners) for entry in row[_VALUES] or []]


def set_mode_bounds_persisted(state: State, owners: ValueOwners, members: pl.DataFrame) -> None:
    """Note that the records of `owners.kind` hold the mode bounds and the emission rates."""
    for parameter in (*MODE_BOUND_PARAMETERS, SupplyParameter.EMISSION_RATE):
        set_persisted_rows(
            state, owners.kind, parameter, [members.select(REGION, TECHNOLOGY)], OPERATING_MODES
        )


# --- the rows ----------------------------------------------------------------------------------


def _read_mode_rows(
    state: State,
    operations: OperationsYear,
    technologies: pl.DataFrame,
    held: pl.DataFrame,
    value: ModeValue,
    run_parameters: frozenset[str],
) -> pl.DataFrame:
    rows = _read_rows(state, operations, technologies, value)
    if value.parameter in run_parameters:
        rows = rows.join(held, on=[*_KEYS, OPERATING_MODE], how="anti")
    rows = rows.filter(pl.col(VALUE_COL) != _NO_VALUE).with_columns(
        pl.col(VALUE_COL).cast(pl.Float64)
    )
    convert = value.convert(operations.units)
    scaled = pl.col(VALUE_COL) if convert is None else express_converted(rows, VALUE_COL, convert)
    detail = pl.lit(None, dtype=pl.Utf8) if value.detail is None else pl.col(value.detail)
    return rows.select(
        *_KEYS,
        pl.lit(value.parameter).alias(_PARAMETER),
        pl.col(OPERATING_MODE),
        pl.lit(value.field).alias(_FIELD),
        detail.cast(pl.Utf8).alias(_DETAIL),
        pl.col(VALUE_COL).alias(_STATED),
        scaled.alias(_SCALED),
        pl.lit(value.unit).alias(_UNIT),
    )


def _read_rows(
    state: State, operations: OperationsYear, technologies: pl.DataFrame, value: ModeValue
) -> pl.DataFrame:
    """A bound reads every year; any other value reads the operations year."""
    if value.is_bound:
        return read_parameter_all_years(state, value.parameter, technologies)
    return read_parameter(state, value.parameter, operations.year).join(
        technologies, on=_KEYS, how="semi"
    )


# --- the events --------------------------------------------------------------------------------


def _build_event(
    row: dict[str, Any], entry: dict[str, Any], owners: ValueOwners
) -> TranslationEvent:
    mode = entry[OPERATING_MODE]
    attribute = f"{EXTENSIONS_PREFIX}{OPERATING_MODES}.{mode}.{entry[_FIELD]}"
    detail = f"{OPERATING_MODE} {mode}"
    if entry[_DETAIL] is not None:
        attribute = f"{attribute}.{entry[_DETAIL]}"
        detail = f"{detail}, {entry[_DETAIL]}"
    return TranslationEvent(
        kind=EventKind.VALUE_DERIVED,
        sources=[
            build_osemosys_field(entry[_PARAMETER], row[owners.report_col], detail, entry[_STATED])
        ],
        destinations=[
            build_sienna_field(
                row[owners.component_col],
                row[owners.name_col],
                attribute,
                entry[_SCALED],
                entry[_UNIT],
            )
        ],
        derivation=_DERIVATION,
    )


_DERIVATION = (
    "the value of an operating mode, for each MWh of its activity; a Sienna component runs one "
    "mode in each direction, so no Sienna field holds it"
)
