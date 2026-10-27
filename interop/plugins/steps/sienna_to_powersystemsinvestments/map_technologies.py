"""Step: shape a SiennaSchemas portfolio into what PowerSystemsInvestmentsPortfolios reads.

Four things differ between the two documents, and this step settles all four. A region the
portfolio names by id becomes a Zone the package resolves that id against. A capital cost the
schema wraps in a struct becomes the value curve the package's field holds. A cost structure
gains the ``__metadata__`` block the package picks a concrete type by, at every depth. A
capacity limit stated once for each year becomes the one limit the package holds.

The flat component list and the per-component ``__metadata__`` block are sink formatting.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, ClassVar, NamedTuple

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import MINUTES_PER_HOUR
from interop.plugins.shared.power_simulations_schema import PSInputOutputCurve
from interop.plugins.shared.power_systems_investments_schema import (
    PSIP_MODULE,
    TECHNOLOGY_FINANCIAL_DATA_TYPE,
    PortfolioColumn,
    PortfolioComponent,
    PortfolioEnvelope,
    PortfolioStorageColumn,
    find_fixed_parameter,
)
from interop.plugins.shared.sienna_constants import (
    SIENNA_NAME_COLUMN,
    SIENNA_REGION_COLUMN,
    MinMaxField,
    SiennaAreaCol,
    SiennaComponent,
    SiennaStructField,
    SiennaTable,
)
from interop.plugins.shared.sienna_investments_constants import (
    PORTFOLIO_FINANCIAL_DATA_TABLE,
    SiennaAggregateTransportTechnologyCol,
    SiennaCapitalCostField,
    SiennaDemandRequirementCol,
    SiennaInvestmentsComponent,
    SiennaOperationCostField,
    SiennaStorageCapitalCostField,
    SiennaStorageTechnologyCol,
    SiennaSupplyTechnologyCol,
)
from interop.plugins.steps.sienna_to_powersimulations._cost_events import build_operation_cost
from interop.plugins.steps.sienna_to_powersystemsinvestments._carbon_caps import (
    report_carbon_caps,
)
from interop.plugins.steps.sienna_to_powersystemsinvestments._events import (
    record_default,
    record_not_mapped,
    record_translation,
)
from interop.plugins.steps.sienna_to_powersystemsinvestments._existing_fleet import (
    map_existing_fleet,
)
from interop.plugins.steps.sienna_to_powersystemsinvestments._limits import (
    LimitRow,
    LimitsByYear,
)
from interop.plugins.steps.sienna_to_powersystemsinvestments._representative_days import (
    derive_representative_day_series,
    list_portfolio_years,
)
from interop.plugins.steps.sienna_to_powersystemsinvestments._transport import TransportLinks
from interop.plugins.steps.sienna_to_powersystemsinvestments._unmodelled import report_unmodelled

# The types the step carries over, in the order the document lists them.
_TECHNOLOGY_TYPES: tuple[SiennaInvestmentsComponent, ...] = (
    SiennaInvestmentsComponent.SUPPLY_TECHNOLOGY,
    SiennaInvestmentsComponent.STORAGE_TECHNOLOGY,
    SiennaInvestmentsComponent.AGGREGATE_TRANSPORT_TECHNOLOGY,
    SiennaInvestmentsComponent.DEMAND_REQUIREMENT,
    SiennaInvestmentsComponent.CARBON_CAPS,
)


class _CapitalCostRule(NamedTuple):
    """Where each cost of a type's capital cost struct goes, and why."""

    fields: tuple[tuple[str, str], ...]
    derivation: str


_ONE_CAPITAL_COST = _CapitalCostRule(
    fields=((SiennaCapitalCostField.CAPITAL_COST, SiennaSupplyTechnologyCol.CAPITAL_COSTS),),
    derivation="CapitalCost -> the value curve the field holds, tagged InputOutputCurve",
)

# The package holds one value curve per thing a plan may add, so a storage technology's one
# struct becomes three.
_CAPITAL_COST_RULES: dict[SiennaInvestmentsComponent, _CapitalCostRule] = {
    SiennaInvestmentsComponent.SUPPLY_TECHNOLOGY: _ONE_CAPITAL_COST,
    SiennaInvestmentsComponent.AGGREGATE_TRANSPORT_TECHNOLOGY: _ONE_CAPITAL_COST,
    SiennaInvestmentsComponent.STORAGE_TECHNOLOGY: _CapitalCostRule(
        fields=(
            (
                SiennaStorageCapitalCostField.CHARGE_CAPITAL_COST,
                PortfolioStorageColumn.CAPITAL_COSTS_CHARGE,
            ),
            (
                SiennaStorageCapitalCostField.DISCHARGE_CAPITAL_COST,
                PortfolioStorageColumn.CAPITAL_COSTS_DISCHARGE,
            ),
            (
                SiennaStorageCapitalCostField.ENERGY_CAPITAL_COST,
                PortfolioStorageColumn.CAPITAL_COSTS_ENERGY,
            ),
        ),
        derivation="StorageCapitalCost -> one value curve per capacity a plan may add",
    ),
}

_NO_COST = 0.0


def _zero_value_curve() -> dict[str, Any]:
    """A curve stating no cost, for a field the destination requires and no source fills."""
    return PSInputOutputCurve.model_validate({}).model_dump()


# The carbon intensity map SiennaSchemas names on a technology, which this never fills.
_CO2_FIELD = "co2"

# A rate of one means a candidate reaches any output within the hour, which is what a
# source stating no limit means.
_UNLIMITED_RATE = 1.0
_NO_LOSS = 1.0

# What the destination cannot read as absent. It resolves a list of ids against its own
# components, iterates a map, and indexes a pair by name, and a null stops each of the three
# rather than standing for a value the source never states.
_REQUIRED_EMPTY: dict[SiennaInvestmentsComponent, tuple[tuple[str, Any], ...]] = {
    SiennaInvestmentsComponent.SUPPLY_TECHNOLOGY: (
        (SIENNA_REGION_COLUMN, []),
        (SiennaSupplyTechnologyCol.REQUIREMENTS, []),
        (SiennaSupplyTechnologyCol.FUEL, []),
        (_CO2_FIELD, {}),
        (SiennaSupplyTechnologyCol.COFIRE_START_LIMITS, {}),
        (SiennaSupplyTechnologyCol.COFIRE_LEVEL_LIMITS, {}),
        (
            SiennaSupplyTechnologyCol.RAMP_LIMITS,
            {SiennaStructField.UP: _UNLIMITED_RATE, SiennaStructField.DOWN: _UNLIMITED_RATE},
        ),
        (
            SiennaSupplyTechnologyCol.TIME_LIMITS,
            {SiennaStructField.UP: _UNLIMITED_RATE, SiennaStructField.DOWN: _UNLIMITED_RATE},
        ),
    ),
    SiennaInvestmentsComponent.STORAGE_TECHNOLOGY: (
        (SIENNA_REGION_COLUMN, []),
        (SiennaStorageTechnologyCol.REQUIREMENTS, []),
        (
            SiennaStorageTechnologyCol.EFFICIENCY,
            {SiennaStructField.IN: _NO_LOSS, SiennaStructField.OUT: _NO_LOSS},
        ),
    ),
    SiennaInvestmentsComponent.AGGREGATE_TRANSPORT_TECHNOLOGY: (
        (SiennaAggregateTransportTechnologyCol.REQUIREMENTS, []),
    ),
    SiennaInvestmentsComponent.DEMAND_REQUIREMENT: (
        (SIENNA_REGION_COLUMN, []),
        (SiennaDemandRequirementCol.REQUIREMENTS, []),
        # The model at the pinned revision reads neither, so neither enters a result.
        (SiennaDemandRequirementCol.VALUE_OF_LOST_LOAD, _NO_COST),
        (SiennaDemandRequirementCol.UNSERVED_DEMAND_CURVE, _zero_value_curve()),
    ),
}

# The package's own defaults for a limit, which bound nothing a plan builds.
_NO_CAPACITY_LIMIT = {MinMaxField.MIN: 0.0, MinMaxField.MAX: 1e8}
_NO_DURATION_LIMIT = {MinMaxField.MIN: 0.0, MinMaxField.MAX: 1000.0}
_TRANSPORT_UNIT_SIZE = 1.0

# The fields the reader rejects as null where a source may state none, with the package's default.
_PACKAGE_DEFAULTS: dict[SiennaInvestmentsComponent, tuple[tuple[str, Any], ...]] = {
    SiennaInvestmentsComponent.SUPPLY_TECHNOLOGY: (
        (SiennaSupplyTechnologyCol.CAPACITY_LIMITS, _NO_CAPACITY_LIMIT),
    ),
    SiennaInvestmentsComponent.STORAGE_TECHNOLOGY: (
        (SiennaStorageTechnologyCol.CAPACITY_LIMITS_DISCHARGE, _NO_CAPACITY_LIMIT),
        (SiennaStorageTechnologyCol.CAPACITY_LIMITS_ENERGY, _NO_CAPACITY_LIMIT),
        (SiennaStorageTechnologyCol.DURATION_LIMITS, _NO_DURATION_LIMIT),
    ),
    SiennaInvestmentsComponent.AGGREGATE_TRANSPORT_TECHNOLOGY: (
        (SiennaAggregateTransportTechnologyCol.CAPACITY_LIMITS, _NO_CAPACITY_LIMIT),
        (SiennaAggregateTransportTechnologyCol.UNIT_SIZE, _TRANSPORT_UNIT_SIZE),
    ),
}

# What an operation cost of the package requires and no SiennaSchemas operation cost states.
_OPERATION_COST_DEFAULTS: dict[SiennaInvestmentsComponent, tuple[str, ...]] = {
    SiennaInvestmentsComponent.STORAGE_TECHNOLOGY: (
        SiennaStructField.ENERGY_SHORTAGE_COST,
        SiennaStructField.ENERGY_SURPLUS_COST,
    ),
}

# The limits that SiennaSchemas states in minutes and the package reads in hours.
_MINUTE_LIMITS: dict[SiennaInvestmentsComponent, tuple[str, ...]] = {
    SiennaInvestmentsComponent.STORAGE_TECHNOLOGY: (SiennaStorageTechnologyCol.DURATION_LIMITS,),
}


class SiennaToPowerSystemsInvestmentsMapTechnologies(TranslationStep):
    name: ClassVar[str] = "sienna_to_powersystemsinvestments_map_technologies"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def run(self, state: State, params: BaseModel | None) -> State:
        _map_zones(state, self._recorder)
        _map_financial_data(state)
        links = TransportLinks(self._recorder)
        context = _PlanContext(
            frozenset(list_portfolio_years(state)),
            LimitsByYear(self._recorder),
            links,
            {SiennaInvestmentsComponent.AGGREGATE_TRANSPORT_TECHNOLOGY: links.set_links},
        )
        rows_by_type = {
            str(sienna_type): _map_rows(state, sienna_type, context, self._recorder)
            for sienna_type in _TECHNOLOGY_TYPES
            if sienna_type in state.source_topology
        }
        self._map_existing_fleet(state, rows_by_type)
        report_unmodelled(rows_by_type, self._recorder)
        for sienna_type, rows in rows_by_type.items():
            # The rows of one type state different cost fields, and Polars reads 100 by default.
            state.destination_tables[sienna_type] = pl.DataFrame(rows, infer_schema_length=None)
        context.limits.warn_lost()
        context.links.warn_lost()
        report_carbon_caps(state, self._recorder)
        derive_representative_day_series(state, self._recorder)
        return state

    def _map_existing_fleet(
        self, state: State, rows_by_type: dict[str, list[dict[str, Any]]]
    ) -> None:
        """Give the plan the fleet that already runs, and a technology for each unnamed plant."""
        plants = map_existing_fleet(state, rows_by_type, self._recorder)
        if not plants:
            return
        supply = rows_by_type.setdefault(SiennaInvestmentsComponent.SUPPLY_TECHNOLOGY.value, [])
        for plant in plants:
            supply.append(_map_existing_plant(plant.row, plant.operation_cost, self._recorder))


class _PlanContext(NamedTuple):
    """The years of the plan, and what settles the fields whose meaning the model changes."""

    years: frozenset[str]
    limits: LimitsByYear
    links: TransportLinks
    # What changes every row of a type beyond the fields that all types share.
    row_rules: Mapping[SiennaInvestmentsComponent, Callable[[dict[str, Any]], None]]


def _map_zones(state: State, recorder: ScopedRecorder) -> None:
    """One Zone per area of the base system, because a technology names its region by id.

    The package resolves that id against the regions the portfolio itself holds, so an area
    the portfolio never states leaves every technology in it regionless.
    """
    source = state.source_topology.get(SiennaTable.AREAS)
    if source is None:
        return
    rows: list[dict[str, Any]] = []
    for area in source.collect().iter_rows(named=True):
        name = area[SiennaAreaCol.NAME]
        rows.append({PortfolioColumn.NAME: name, PortfolioColumn.ID: area[SiennaAreaCol.ID]})
        record_translation(
            recorder,
            component=SiennaComponent.AREA.value,
            name=name,
            source_field=SiennaAreaCol.ID,
            source_value=area[SiennaAreaCol.ID],
            destination_field=PortfolioColumn.ID,
            destination_value=area[SiennaAreaCol.ID],
            derivation="Area -> Zone, the region a technology names by id",
        )
    if rows:
        state.destination_tables[PortfolioComponent.ZONE] = pl.DataFrame(rows)


def _map_financial_data(state: State) -> None:
    """The rates the whole portfolio discounts by, which the destination reads unchanged."""
    source = state.source_topology.get(PORTFOLIO_FINANCIAL_DATA_TABLE)
    if source is None:
        return
    state.destination_tables[PORTFOLIO_FINANCIAL_DATA_TABLE] = source.collect()


def _map_rows(
    state: State,
    sienna_type: SiennaInvestmentsComponent,
    context: _PlanContext,
    recorder: ScopedRecorder,
) -> list[dict[str, Any]]:
    """Carry one type over, reshaping the fields whose shape or meaning differs."""
    rows = []
    for row in state.source_topology[sienna_type].collect().iter_rows(named=True):
        mapped = dict(row)
        context.limits.set_limits(
            mapped, LimitRow(sienna_type, mapped[SIENNA_NAME_COLUMN], context.years)
        )
        _set_fixed_parameter(mapped, sienna_type, recorder)
        set_rule = context.row_rules.get(sienna_type)
        if set_rule is not None:
            set_rule(mapped)
        rows.append(_map_one(mapped, sienna_type, recorder))
    return rows


def _set_fixed_parameter(
    row: dict[str, Any], sienna_type: SiennaInvestmentsComponent, recorder: ScopedRecorder
) -> None:
    """Name the one parameter that the adapter sets a model for, where the type has only one."""
    parameter = find_fixed_parameter(sienna_type)
    if parameter is None:
        return
    stated = row.get(PortfolioColumn.POWER_SYSTEMS_TYPE)
    row[PortfolioColumn.POWER_SYSTEMS_TYPE] = parameter
    record_translation(
        recorder,
        component=str(sienna_type),
        name=row[SIENNA_NAME_COLUMN],
        source_field=PortfolioColumn.POWER_SYSTEMS_TYPE,
        source_value=stated,
        destination_field=PortfolioColumn.POWER_SYSTEMS_TYPE,
        destination_value=parameter,
        derivation=(
            f"the adapter sets a model for {sienna_type}{{{parameter}}} only, and the model "
            f"treats every parameter of the type alike, so the technology names {parameter}"
        ),
    )


def _map_existing_plant(
    row: dict[str, Any], operation_cost: dict[str, Any], recorder: ScopedRecorder
) -> dict[str, Any]:
    """A technology for one existing plant, running at the cost the base system states."""
    mapped = _map_one(row, SiennaInvestmentsComponent.SUPPLY_TECHNOLOGY, recorder)
    mapped[SiennaSupplyTechnologyCol.OPERATION_COSTS] = operation_cost
    return mapped


def _map_one(
    row: dict[str, Any], sienna_type: SiennaInvestmentsComponent, recorder: ScopedRecorder
) -> dict[str, Any]:
    name = row[SIENNA_NAME_COLUMN]
    _map_capital_costs(row, sienna_type, name, recorder)
    _convert_minute_limits(row, sienna_type, name, recorder)
    _fill_required(row, sienna_type, name, recorder)
    _tag_financial_data(row, sienna_type, name, recorder)
    if row.get(SiennaSupplyTechnologyCol.OPERATION_COSTS) is not None:
        row[SiennaSupplyTechnologyCol.OPERATION_COSTS] = _build_operation_costs(
            row[SiennaSupplyTechnologyCol.OPERATION_COSTS], sienna_type, name, recorder
        )
    return row


def _tag_financial_data(
    row: dict[str, Any],
    sienna_type: SiennaInvestmentsComponent,
    name: str,
    recorder: ScopedRecorder,
) -> None:
    """Name the type the reader builds the rates from, which it cannot infer from the fields."""
    financial_data = row.get(SiennaSupplyTechnologyCol.FINANCIAL_DATA)
    if financial_data is None:
        return
    row[SiennaSupplyTechnologyCol.FINANCIAL_DATA] = {
        **financial_data,
        PortfolioEnvelope.METADATA_KEY: {
            PortfolioEnvelope.MODULE: PSIP_MODULE,
            PortfolioEnvelope.TYPE: TECHNOLOGY_FINANCIAL_DATA_TYPE,
        },
    }
    record_translation(
        recorder,
        component=str(sienna_type),
        name=name,
        source_field=SiennaSupplyTechnologyCol.FINANCIAL_DATA,
        source_value=financial_data,
        destination_field=(
            f"{SiennaSupplyTechnologyCol.FINANCIAL_DATA}.{PortfolioEnvelope.METADATA_KEY}"
        ),
        destination_value=TECHNOLOGY_FINANCIAL_DATA_TYPE,
        derivation="the reader picks a concrete type by the tag, not by the fields",
    )


def _fill_required(
    row: dict[str, Any],
    sienna_type: SiennaInvestmentsComponent,
    name: str,
    recorder: ScopedRecorder,
) -> None:
    """State an empty value where the source states none, because the reader rejects a null."""
    for field, empty in _REQUIRED_EMPTY.get(sienna_type, ()):
        if row.get(field) is not None:
            continue
        row[field] = empty
        record_default(
            recorder,
            component=str(sienna_type),
            name=name,
            field=field,
            value=empty,
            derivation="the destination rejects a null here, so nothing states an empty value",
        )
    for field, default in _PACKAGE_DEFAULTS.get(sienna_type, ()):
        stated = row.get(field)
        if stated is not None and not _is_partial_limit(stated, default):
            continue
        row[field] = _fill_bounds(stated, default)
        record_default(
            recorder,
            component=str(sienna_type),
            name=name,
            field=field,
            value=row[field],
            derivation="the destination rejects a null here, so it takes the package's default",
        )


def _is_partial_limit(stated: Any, default: Any) -> bool:
    """Whether a limit states one bound only, where the reader indexes both by name."""
    return (
        isinstance(stated, dict)
        and isinstance(default, dict)
        and not default.keys() <= {key for key, value in stated.items() if value is not None}
    )


def _fill_bounds(stated: Any, default: Any) -> Any:
    """The stated bounds of a limit, and the package's default for each bound it leaves out."""
    if not isinstance(stated, dict):
        return default
    return {**default, **{key: value for key, value in stated.items() if value is not None}}


def _map_capital_costs(
    row: dict[str, Any],
    sienna_type: SiennaInvestmentsComponent,
    name: str,
    recorder: ScopedRecorder,
) -> None:
    """The package's fields are value curves, where the schema wraps them in one struct."""
    rule = _CAPITAL_COST_RULES.get(sienna_type)
    if rule is None:
        return
    wrapper = row.pop(SiennaSupplyTechnologyCol.CAPITAL_COSTS, None) or {}
    for source_field, destination_field in rule.fields:
        row[destination_field] = _build_value_curve(wrapper.get(source_field))
        record_translation(
            recorder,
            component=str(sienna_type),
            name=name,
            source_field=f"{SiennaSupplyTechnologyCol.CAPITAL_COSTS}.{source_field}",
            source_value=wrapper.get(source_field),
            destination_field=destination_field,
            destination_value=row[destination_field],
            derivation=rule.derivation,
        )
    _report_interconnection_cost(wrapper, str(sienna_type), name, recorder)


def _convert_minute_limits(
    row: dict[str, Any],
    sienna_type: SiennaInvestmentsComponent,
    name: str,
    recorder: ScopedRecorder,
) -> None:
    """The bounds of each limit in hours, where SiennaSchemas states them in minutes."""
    for field in _MINUTE_LIMITS.get(sienna_type, ()):
        minutes = row.get(field)
        if minutes is None:
            continue
        hours = {
            bound: None if value is None else value / MINUTES_PER_HOUR
            for bound, value in minutes.items()
        }
        row[field] = hours
        record_translation(
            recorder,
            component=str(sienna_type),
            name=name,
            source_field=f"{field} (min)",
            source_value=minutes,
            destination_field=f"{field} (h)",
            destination_value=hours,
            derivation=f"{field} in minutes ÷ 60 min/h, because the package reads hours",
        )


def _report_interconnection_cost(
    wrapper: dict[str, Any], component: str, name: str, recorder: ScopedRecorder
) -> None:
    """The cost of joining a candidate to the network, which the package has no field for."""
    interconnection_cost = wrapper.get(SiennaCapitalCostField.INTERCONNECTION_COST)
    if interconnection_cost is None:
        return
    record_not_mapped(
        recorder,
        component=component,
        name=name,
        field=f"capital_costs.{SiennaCapitalCostField.INTERCONNECTION_COST}",
        value=interconnection_cost,
        derivation="the destination states one capital cost per capacity and no second cost",
    )


def _build_value_curve(curve: dict[str, Any] | None) -> dict[str, Any]:
    """A value curve the package can pick a concrete type for, zero where the source states none."""
    return PSInputOutputCurve.model_validate(curve or {}).model_dump()


def _build_operation_costs(
    cost: dict[str, Any],
    sienna_type: SiennaInvestmentsComponent,
    name: str,
    recorder: ScopedRecorder,
) -> Any:
    """The fixed and variable cost of running a candidate, in the shape the package reads."""
    prepared = dict(cost)
    variable = prepared.pop(SiennaOperationCostField.VARIABLE_OPERATION_COST, None)
    if variable is not None:
        prepared[SiennaStructField.VARIABLE] = variable
        record_translation(
            recorder,
            component=str(sienna_type),
            name=name,
            source_field=(
                f"{SiennaSupplyTechnologyCol.OPERATION_COSTS}."
                f"{SiennaOperationCostField.VARIABLE_OPERATION_COST}"
            ),
            source_value=variable,
            destination_field=(
                f"{SiennaSupplyTechnologyCol.OPERATION_COSTS}.{SiennaStructField.VARIABLE}"
            ),
            destination_value=variable,
            derivation="variable_operation_cost -> variable (field rename)",
        )
    _fill_operation_cost(prepared, sienna_type, name, recorder)
    return build_operation_cost(prepared, recorder, str(sienna_type), name)


def _fill_operation_cost(
    cost: dict[str, Any],
    sienna_type: SiennaInvestmentsComponent,
    name: str,
    recorder: ScopedRecorder,
) -> None:
    """A price that the package's cost requires and SiennaSchemas does not state, such as the
    price a StorageCost states for spilling and for falling short."""
    for field in _OPERATION_COST_DEFAULTS.get(sienna_type, ()):
        cost.setdefault(field, _NO_COST)
        record_default(
            recorder,
            component=str(sienna_type),
            name=name,
            field=f"{SiennaSupplyTechnologyCol.OPERATION_COSTS}.{field}",
            value=_NO_COST,
            derivation="the destination requires the field and the source states no price",
        )
