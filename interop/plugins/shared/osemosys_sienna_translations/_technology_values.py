"""The values of a technology in the operations year that its Sienna component has no field for.

Each value goes to one field of the extension record of the component. A capacity rates on
the electricity of the component, so it multiplies by the rating ratio, and a cost for each
unit of capacity divides by it. A row that binds nothing, as OSeMOSYS states it, gives no
value, so an absent field means no bound.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any, NamedTuple

import polars as pl

from interop.core.extensions import ExtensionKind
from interop.core.pipeline import State
from interop.plugins.shared.constants import (
    EXTENSIONS_PREFIX,
    UNIT_DOLLARS_PER_MW,
    UNIT_DOLLARS_PER_MW_YEAR,
    UNIT_DOLLARS_PER_MWH,
    UNIT_HOURS,
    UNIT_MW,
    UNIT_MWH,
    UNIT_MWH_PER_MW,
    UNIT_PER_UNIT,
    UNIT_YEARS,
)
from interop.plugins.shared.osemosys_canonical.constants import (
    FUEL,
    REGION,
    TECHNOLOGY,
    VALUE_COL,
    YEAR,
)
from interop.plugins.shared.osemosys_sienna_constants import (
    NO_LIMIT,
    ActivityParameter,
    GrowthParameter,
    InvestmentParameter,
    StorageBalanceParameter,
    SupplyParameter,
)
from interop.plugins.shared.osemosys_sienna_translations._canonical import (
    find_parameter_default,
    read_parameter,
    read_parameter_all_years,
    read_parameter_with_defaults,
)
from interop.plugins.shared.osemosys_sienna_translations._events import (
    build_osemosys_field,
    build_sienna_field,
)
from interop.plugins.shared.osemosys_sienna_translations._operations import OperationsYear
from interop.plugins.shared.osemosys_sienna_translations._persisted import set_persisted_rows
from interop.plugins.shared.osemosys_sienna_translations._units import (
    ModelUnits,
    express_converted,
)
from interop.ports.outbound.reporting import EventKind, SourceField, TranslationEvent

# The electricity of the component for each unit of the activity of the technology.
RATING_RATIO = "rating_ratio"

_STATED_PREFIX = "stated."
_ORIGIN_PREFIX = "origin."
_YEAR_PREFIX = "year."
_FROM_DEFAULT = "default"
_FROM_FALLBACK = "fallback"
_VALUE_SCALED = "value_scaled"
_FALLBACK = "fallback"
_APPLIED_SCOPE = "applied"
_DETAIL = "detail"
_STATED = "stated"
_VALUE = "value"
_NO_BOUND = 0.0
_FLAG_SET = 1.0
_WHOLE = 1.0


class Scale(Enum):
    """How a value in the units of the model becomes the value of a field."""

    NONE = "none"
    CAPACITY = "capacity"
    COST_PER_CAPACITY = "cost_per_capacity"
    ENERGY = "energy"
    COST_PER_ENERGY = "cost_per_energy"
    ENERGY_PER_CAPACITY = "energy_per_capacity"
    FLAG = "flag"
    COMPLEMENT = "complement"


class TechnologyValue(NamedTuple):
    """One parameter, the field that holds its value, and which of its rows bind.

    `detail` names a key column whose members key the field, which is then a dict. A value with a
    `fallback`, a parameter keyed by region, fills a member that states none with the default
    of its parameter, else with the fallback; a value with no fallback leaves the member empty.
    A value of every year reads each year in scope rather than the operations year. A value
    by year gives a field keyed by the operations year. A `derivation` replaces the text that
    the scale gives the event.
    """

    parameter: str
    field: str
    scale: Scale
    unit: str | None
    binds: pl.Expr | None = None
    detail: str | None = None
    fallback: str | None = None
    is_every_year: bool = False
    is_by_year: bool = False
    derivation: str | None = None

    @property
    def column(self) -> str:
        return f"{EXTENSIONS_PREFIX}{self.field}"

    @property
    def stated_column(self) -> str:
        return f"{_STATED_PREFIX}{self.field}"

    @property
    def origin_column(self) -> str:
        return f"{_ORIGIN_PREFIX}{self.field}"

    @property
    def year_column(self) -> str:
        return f"{_YEAR_PREFIX}{self.field}"


@dataclass(frozen=True)
class ValueOwners:
    """The kind of the records, and the columns that name each component and its member.

    `component_col` holds the Sienna type that an event names, or the kind where none.
    `keys` are the key columns that the values of a component are keyed by.
    """

    kind: ExtensionKind
    name_col: str
    report_col: str
    component_col: str
    keys: tuple[str, ...] = (REGION, TECHNOLOGY)


_STATED_VALUE = pl.col(VALUE_COL)
_GROWTH_VALUES = (
    TechnologyValue(
        InvestmentParameter.MAX_CAPACITY_INVESTMENT,
        "max_growth",
        Scale.CAPACITY,
        UNIT_MW,
        _STATED_VALUE != NO_LIMIT,
        is_by_year=True,
    ),
    TechnologyValue(
        GrowthParameter.MIN_CAPACITY_INVESTMENT,
        "min_growth",
        Scale.CAPACITY,
        UNIT_MW,
        _STATED_VALUE > _NO_BOUND,
        is_by_year=True,
    ),
    TechnologyValue(
        GrowthParameter.MAX_GROWTH_RATE,
        "max_growth_rate",
        Scale.NONE,
        UNIT_PER_UNIT,
        is_by_year=True,
    ),
    TechnologyValue(
        GrowthParameter.MIN_GROWTH_RATE,
        "min_growth_rate",
        Scale.NONE,
        UNIT_PER_UNIT,
        is_by_year=True,
    ),
    TechnologyValue(
        GrowthParameter.MAX_FLOOR, "max_growth_floor", Scale.CAPACITY, UNIT_MW, is_by_year=True
    ),
)
# The values of a technology that a portfolio candidate holds beside its yearly values.
CANDIDATE_VALUES: tuple[TechnologyValue, ...] = (
    TechnologyValue(
        ActivityParameter.MODEL_PERIOD_LOWER_LIMIT,
        "e_sum_min_horizon",
        Scale.ENERGY,
        UNIT_MWH,
        _STATED_VALUE > _NO_BOUND,
    ),
    TechnologyValue(
        ActivityParameter.MODEL_PERIOD_UPPER_LIMIT,
        "e_sum_max_horizon",
        Scale.ENERGY,
        UNIT_MWH,
        _STATED_VALUE >= _NO_BOUND,
    ),
    TechnologyValue(
        ActivityParameter.CAPACITY_TO_ACTIVITY_UNIT,
        "capacity_to_activity_unit",
        Scale.ENERGY_PER_CAPACITY,
        UNIT_MWH_PER_MW,
    ),
)
# The values that every technology states, whatever its component.
_TECHNOLOGY_VALUES = (
    TechnologyValue(
        InvestmentParameter.CAPITAL_COST,
        "overnight_cost_per_mw",
        Scale.COST_PER_CAPACITY,
        UNIT_DOLLARS_PER_MW,
    ),
    TechnologyValue(
        InvestmentParameter.UNIT_SIZE,
        "unit_size_mw",
        Scale.CAPACITY,
        UNIT_MW,
        _STATED_VALUE > _NO_BOUND,
    ),
    TechnologyValue(
        InvestmentParameter.CAPACITY_LIMITS_MAX,
        "p_nom_max",
        Scale.CAPACITY,
        UNIT_MW,
        _STATED_VALUE != NO_LIMIT,
    ),
    TechnologyValue(
        InvestmentParameter.CAPACITY_LIMITS_MIN,
        "p_nom_min",
        Scale.CAPACITY,
        UNIT_MW,
        _STATED_VALUE > _NO_BOUND,
    ),
    *_GROWTH_VALUES,
    *CANDIDATE_VALUES,
    TechnologyValue(
        ActivityParameter.MIN_CAPACITY_FACTOR, "capacity_factor_min", Scale.NONE, UNIT_PER_UNIT
    ),
    TechnologyValue(
        ActivityParameter.MIN_PRODUCTION_TARGET,
        "production_share_min",
        Scale.NONE,
        UNIT_PER_UNIT,
        detail=FUEL,
    ),
    TechnologyValue(
        ActivityParameter.MAX_PRODUCTION_TARGET,
        "production_share_max",
        Scale.NONE,
        UNIT_PER_UNIT,
        detail=FUEL,
    ),
)
_LIFE_VALUES = (
    TechnologyValue(InvestmentParameter.LIFETIME, "lifetime_years", Scale.NONE, UNIT_YEARS),
    TechnologyValue(
        InvestmentParameter.TECHNOLOGY_DISCOUNT_RATE,
        "discount_rate",
        Scale.NONE,
        UNIT_PER_UNIT,
        fallback=InvestmentParameter.DISCOUNT_RATE,
    ),
)
# A generator, a line and a conversion state their own life and discount rate.
COMPONENT_VALUES: tuple[TechnologyValue, ...] = (*_TECHNOLOGY_VALUES, *_LIFE_VALUES)
# A line and a conversion state their fixed cost here too, as no Sienna field holds it.
LINK_VALUES: tuple[TechnologyValue, ...] = (
    *COMPONENT_VALUES,
    TechnologyValue(
        SupplyParameter.FIXED_COST,
        "fom_charge_per_mw_year",
        Scale.COST_PER_CAPACITY,
        UNIT_DOLLARS_PER_MW_YEAR,
    ),
)
# The technology that charges a storage, where it does not also discharge it.
CHARGE_VALUES: tuple[TechnologyValue, ...] = (
    TechnologyValue(
        SupplyParameter.FIXED_COST,
        "charge_fom_cost",
        Scale.COST_PER_CAPACITY,
        UNIT_DOLLARS_PER_MW_YEAR,
    ),
)
# The parameters of a technology whose rows the component that holds it applies or keeps.
RATED_PARAMETERS: tuple[str, ...] = (
    SupplyParameter.RESIDUAL_CAPACITY,
    SupplyParameter.AVAILABILITY_FACTOR,
    SupplyParameter.VARIABLE_OPERATION_COST,
)
# A storage takes the values of the technology that discharges it, and states its own life.
DISCHARGE_TECHNOLOGY_VALUES: tuple[TechnologyValue, ...] = _TECHNOLOGY_VALUES
STORAGE_VALUES: tuple[TechnologyValue, ...] = (
    TechnologyValue(
        InvestmentParameter.ENERGY_CAPITAL_COST,
        "energy_overnight_cost",
        Scale.COST_PER_ENERGY,
        UNIT_DOLLARS_PER_MWH,
    ),
    TechnologyValue(InvestmentParameter.STORAGE_LIFETIME, "lifetime_years", Scale.NONE, UNIT_YEARS),
    TechnologyValue(
        InvestmentParameter.STORAGE_DISCOUNT_RATE,
        "discount_rate",
        Scale.NONE,
        UNIT_PER_UNIT,
        fallback=InvestmentParameter.DISCOUNT_RATE,
    ),
    TechnologyValue(
        InvestmentParameter.DURATION_LIMITS_MAX, "duration_max_hours", Scale.NONE, UNIT_HOURS
    ),
    TechnologyValue(
        StorageBalanceParameter.YEAR, "cyclic_state_of_charge_per_period", Scale.FLAG, None
    ),
    TechnologyValue(
        StorageBalanceParameter.SEASON, "cyclic_state_of_charge_per_season", Scale.FLAG, None
    ),
    TechnologyValue(
        StorageBalanceParameter.DAY, "cyclic_state_of_charge_per_day", Scale.FLAG, None
    ),
)


def enrich_technology_values(
    state: State,
    operations: OperationsYear,
    members: pl.DataFrame,
    values: Sequence[TechnologyValue],
    keys: Sequence[str] = (REGION, TECHNOLOGY),
) -> pl.DataFrame:
    """One column for each value, and its stated value, beside each member.

    `members` holds the key columns and `rating_ratio`.
    """
    table = members
    for value in values:
        read = _read_value(state, operations, members, value, list(keys))
        table = table.join(read, on=list(keys), how="left")
    return table


def build_value_fields(row: dict[str, Any], values: Sequence[TechnologyValue]) -> dict[str, Any]:
    """The fields of a record that the values of one row fill, without the absent ones."""
    fields = {value.field: _build_field(row, value) for value in values}
    return {name: field for name, field in fields.items() if field is not None}


def build_value_events(
    row: dict[str, Any], values: Sequence[TechnologyValue], owners: ValueOwners
) -> list[TranslationEvent]:
    """One VALUE_DERIVED for each value that the record of one row holds."""
    return [event for value in values for event in _build_events(row, value, owners)]


def set_applied_rows(
    state: State, owners: ValueOwners, members: pl.DataFrame, parameters: Sequence[str]
) -> None:
    """Note that the components of `owners.kind` apply or keep each row of `members`."""
    for parameter in parameters:
        scope = f"{_APPLIED_SCOPE}-{owners.report_col}"
        set_persisted_rows(state, owners.kind, parameter, [members.select(owners.keys)], scope)


def set_values_persisted(
    state: State, owners: ValueOwners, members: pl.DataFrame, values: Sequence[TechnologyValue]
) -> None:
    """Note that the records of `owners.kind` hold each value of `members`."""
    keys = members.select(owners.keys)
    for value in values:
        set_persisted_rows(state, owners.kind, value.parameter, [keys], value.field)
        if value.fallback is not None:
            set_persisted_rows(
                state, owners.kind, value.fallback, [keys.select(REGION)], value.field
            )


# --- the read of one value ---------------------------------------------------------------------


def _read_value(
    state: State,
    operations: OperationsYear,
    members: pl.DataFrame,
    value: TechnologyValue,
    keys: list[str],
) -> pl.DataFrame:
    rows = _read_rows(state, operations, members.select(keys).unique(), value)
    if value.binds is not None:
        rows = rows.filter(value.binds)
    rows = rows.join(members.select(*keys, RATING_RATIO), on=keys).with_columns(
        _STATED_VALUE.cast(pl.Float64)
    )
    scaled = rows.with_columns(
        _express_scaled(rows, value.scale, operations.units).alias(_VALUE_SCALED)
    )
    if value.detail is not None:
        return _group_details(scaled, value, keys)
    table = scaled.select(
        *keys,
        pl.col(VALUE_COL).alias(value.stated_column),
        pl.col(_VALUE_SCALED).alias(value.column),
        *_select_year(value),
    )
    if value.fallback is None:
        return table
    return _fill_fallback(state, operations, members.select(keys), table, value)


def _select_year(value: TechnologyValue) -> list[pl.Expr]:
    """The year of a value by year, as an integer, so the field can key by it."""
    if not value.is_by_year:
        return []
    return [pl.col(YEAR).cast(pl.Int64).alias(value.year_column)]


def _read_rows(
    state: State, operations: OperationsYear, keys: pl.DataFrame, value: TechnologyValue
) -> pl.DataFrame:
    """A value of every year reads every year; another reads the operations year."""
    if value.is_every_year:
        return read_parameter_all_years(state, value.parameter, keys)
    rows = read_parameter(state, value.parameter, operations.year)
    return rows.join(keys, on=keys.columns, how="semi")


def _group_details(rows: pl.DataFrame, value: TechnologyValue, keys: list[str]) -> pl.DataFrame:
    detail = value.detail or ""
    entry = pl.struct(
        pl.col(detail).alias(_DETAIL),
        pl.col(VALUE_COL).alias(_STATED),
        pl.col(_VALUE_SCALED).alias(_VALUE),
    )
    return (
        rows.sort(detail)
        .group_by(keys, maintain_order=True)
        .agg(entry.alias(value.column))
        .with_columns(pl.col(value.column).alias(value.stated_column))
    )


def _fill_fallback(
    state: State,
    operations: OperationsYear,
    keys: pl.DataFrame,
    table: pl.DataFrame,
    value: TechnologyValue,
) -> pl.DataFrame:
    """The default of the parameter, else the value of the region, where a member states none."""
    joined = keys.join(table, on=keys.columns, how="left")
    default = find_parameter_default(state, value.parameter)
    if default is not None:
        return _fill_value(joined, value, pl.lit(float(default)), _FROM_DEFAULT)
    regions = keys.select(REGION).unique()
    rates = read_parameter_with_defaults(
        state, value.fallback or "", operations.year, regions
    ).select(REGION, pl.col(VALUE_COL).cast(pl.Float64).alias(_FALLBACK))
    filled = _fill_value(
        joined.join(rates, on=REGION, how="left"), value, pl.col(_FALLBACK), _FROM_FALLBACK
    )
    return filled.drop(_FALLBACK)


def _fill_value(
    table: pl.DataFrame, value: TechnologyValue, filler: pl.Expr, origin: str
) -> pl.DataFrame:
    is_unstated = pl.col(value.column).is_null() & filler.is_not_null()
    return table.with_columns(
        pl.col(value.column).fill_null(filler),
        pl.col(value.stated_column).fill_null(filler),
        pl.when(is_unstated).then(pl.lit(origin)).otherwise(None).alias(value.origin_column),
    )


def _express_scaled(rows: pl.DataFrame, scale: Scale, units: ModelUnits) -> pl.Expr:
    ratio = pl.col(RATING_RATIO)
    if scale is Scale.CAPACITY:
        return express_converted(rows, VALUE_COL, units.convert_capacity_to_mw) * ratio
    if scale is Scale.COST_PER_CAPACITY:
        convert = units.convert_cost_per_capacity_to_dollars_per_mw
        return express_converted(rows, VALUE_COL, convert) / ratio
    if scale is Scale.ENERGY:
        return express_converted(rows, VALUE_COL, units.convert_energy_to_mwh) * ratio
    if scale is Scale.COST_PER_ENERGY:
        return express_converted(rows, VALUE_COL, units.convert_cost_per_energy_to_dollars_per_mwh)
    if scale is Scale.ENERGY_PER_CAPACITY:
        return express_converted(rows, VALUE_COL, _build_energy_per_capacity(units))
    if scale is Scale.FLAG:
        return _STATED_VALUE == _FLAG_SET
    if scale is Scale.COMPLEMENT:
        return _WHOLE - _STATED_VALUE
    return _STATED_VALUE


def _build_energy_per_capacity(units: ModelUnits) -> Callable[[pl.Expr], pl.Expr]:
    def convert(value: pl.Expr) -> pl.Expr:
        return units.convert_energy_to_mwh(value) / units.convert_capacity_to_mw(1.0)

    return convert


# --- the record and the events -----------------------------------------------------------------


def _build_field(row: dict[str, Any], value: TechnologyValue) -> Any:
    cell = row[value.column]
    if cell is None:
        return None
    if value.is_by_year:
        return {row[value.year_column]: cell}
    if value.detail is None:
        return cell
    return {entry[_DETAIL]: entry[_VALUE] for entry in cell} or None


def _build_events(
    row: dict[str, Any], value: TechnologyValue, owners: ValueOwners
) -> list[TranslationEvent]:
    cell = row[value.column]
    if cell is None:
        return []
    entries = cell if value.detail is not None else [_build_entry(row, value)]
    return [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[_build_source(row, value, owners, entry)],
            destinations=[
                build_sienna_field(
                    row[owners.component_col],
                    row[owners.name_col],
                    _build_attribute(value, entry[_DETAIL]),
                    entry[_VALUE],
                    value.unit,
                )
            ],
            derivation=_choose_derivation(row, value),
        )
        for entry in entries
    ]


def _build_source(
    row: dict[str, Any], value: TechnologyValue, owners: ValueOwners, entry: dict[str, Any]
) -> SourceField:
    """The parameter that gave the value: the region's own rate where the fallback applied."""
    if row.get(value.origin_column) == _FROM_FALLBACK:
        return build_osemosys_field(value.fallback or "", row[REGION], None, entry[_STATED])
    return build_osemosys_field(
        value.parameter, row[owners.report_col], entry[_DETAIL], entry[_STATED]
    )


def _choose_derivation(row: dict[str, Any], value: TechnologyValue) -> str:
    origin = row.get(value.origin_column)
    if origin == _FROM_DEFAULT:
        return _DEFAULT_DERIVATION.format(parameter=value.parameter)
    if origin == _FROM_FALLBACK:
        return _FALLBACK_DERIVATION.format(parameter=value.parameter, fallback=value.fallback)
    return value.derivation or _DERIVATIONS[value.scale]


def _build_entry(row: dict[str, Any], value: TechnologyValue) -> dict[str, Any]:
    return {_DETAIL: None, _STATED: row[value.stated_column], _VALUE: _build_field(row, value)}


def _build_attribute(value: TechnologyValue, detail: str | None) -> str:
    return value.column if detail is None else f"{value.column}.{detail}"


_DEFAULT_DERIVATION = (
    "the model states no {parameter} for the member, so the default of the parameter applies; "
    "no Sienna field holds it"
)
_FALLBACK_DERIVATION = (
    "the model states no {parameter} for the member and the parameter has no default, so the "
    "{fallback} of the region applies; no Sienna field holds it"
)
_DERIVATIONS: dict[Scale, str] = {
    Scale.NONE: "the value of the operations year, which no Sienna field holds",
    Scale.CAPACITY: (
        "the value of the operations year, in MW, × the electricity of the component for each "
        "unit of activity; no Sienna field holds it"
    ),
    Scale.COST_PER_CAPACITY: (
        "the value of the operations year, in $/MW, / the electricity of the component for each "
        "unit of activity; no Sienna field holds it"
    ),
    Scale.ENERGY: (
        "the value, in MWh, × the electricity of the component for each unit of activity in the "
        "operations year; no Sienna field holds it"
    ),
    Scale.COST_PER_ENERGY: "the value of the operations year, in $/MWh; no Sienna field holds it",
    Scale.ENERGY_PER_CAPACITY: "the value, in MWh for each MW; no Sienna field holds it",
    Scale.FLAG: "1 sets the flag; no Sienna field holds it",
    Scale.COMPLEMENT: "1 - the value of the operations year; no Sienna field holds it",
}
