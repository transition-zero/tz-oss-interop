"""Step: shape a SiennaSchemas portfolio into what PowerSystemsInvestmentsPortfolios reads.

Three things differ between the two documents, and this step settles all three. A region the
portfolio names by id becomes a Zone the package resolves that id against. A capital cost the
schema wraps in a struct becomes the value curve the package's field holds. A cost structure
gains the ``__metadata__`` block the package picks a concrete type by, at every depth.

The flat component list and the per-component ``__metadata__`` block are sink formatting.
"""

from __future__ import annotations

from typing import Any, ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.power_simulations_schema import PSInputOutputCurve
from interop.plugins.shared.power_systems_investments_schema import (
    PSIP_MODULE,
    TECHNOLOGY_FINANCIAL_DATA_TYPE,
    PortfolioColumn,
    PortfolioComponent,
    PortfolioEnvelope,
)
from interop.plugins.shared.sienna_constants import (
    SIENNA_NAME_COLUMN,
    SIENNA_REGION_COLUMN,
    SiennaACBusCol,
    SiennaComponent,
    SiennaStructField,
    SiennaTable,
)
from interop.plugins.shared.sienna_investments_constants import (
    PORTFOLIO_FINANCIAL_DATA_TABLE,
    SiennaCapitalCostField,
    SiennaDemandRequirementCol,
    SiennaInvestmentsComponent,
    SiennaOperationCostField,
    SiennaStorageCapitalCostField,
    SiennaStorageTechnologyCol,
    SiennaSupplyTechnologyCol,
)
from interop.plugins.steps.sienna_to_powersimulations._cost_events import build_operation_cost
from interop.plugins.steps.sienna_to_powersystemsinvestments._events import (
    record_default,
    record_not_mapped,
    record_translation,
)
from interop.plugins.steps.sienna_to_powersystemsinvestments._series import derive_series

# The types the step carries over, in the order the document lists them.
_TECHNOLOGY_TYPES: tuple[SiennaInvestmentsComponent, ...] = (
    SiennaInvestmentsComponent.SUPPLY_TECHNOLOGY,
    SiennaInvestmentsComponent.STORAGE_TECHNOLOGY,
    SiennaInvestmentsComponent.DEMAND_REQUIREMENT,
    SiennaInvestmentsComponent.CARBON_CAPS,
)

# Where a storage technology's one capital cost struct goes: the package holds a separate
# value curve per thing a plan may add.
_STORAGE_CAPITAL_COST_FIELDS: tuple[tuple[str, str], ...] = (
    (SiennaStorageCapitalCostField.CHARGE_CAPITAL_COST, "capital_costs_charge"),
    (SiennaStorageCapitalCostField.DISCHARGE_CAPITAL_COST, "capital_costs_discharge"),
    (SiennaStorageCapitalCostField.ENERGY_CAPITAL_COST, "capital_costs_energy"),
)

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
    SiennaInvestmentsComponent.DEMAND_REQUIREMENT: (
        (SIENNA_REGION_COLUMN, []),
        (SiennaDemandRequirementCol.REQUIREMENTS, []),
        # The model at the pinned revision reads neither, so neither enters a result.
        (SiennaDemandRequirementCol.VALUE_OF_LOST_LOAD, _NO_COST),
        (SiennaDemandRequirementCol.UNSERVED_DEMAND_CURVE, _zero_value_curve()),
    ),
}

# What a StorageCost requires and no SiennaSchemas storage cost states.
_STORAGE_COST_DEFAULTS: tuple[str, ...] = ("energy_shortage_cost", "energy_surplus_cost")


class SiennaToPowerSystemsInvestmentsMapTechnologies(TranslationStep):
    name: ClassVar[str] = "sienna_to_powersystemsinvestments_map_technologies"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def run(self, state: State, params: BaseModel | None) -> State:
        _map_zones(state, self._recorder)
        _map_financial_data(state)
        for sienna_type in _TECHNOLOGY_TYPES:
            _map_technologies(state, sienna_type, self._recorder)
        derive_series(state, self._recorder)
        return state


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
        name = area[SiennaACBusCol.NAME]
        rows.append({PortfolioColumn.NAME: name, PortfolioColumn.ID: area[SiennaACBusCol.ID]})
        record_translation(
            recorder,
            component=SiennaComponent.AREA.value,
            name=name,
            source_field=SiennaACBusCol.ID,
            source_value=area[SiennaACBusCol.ID],
            destination_field=PortfolioColumn.ID,
            destination_value=area[SiennaACBusCol.ID],
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


def _map_technologies(
    state: State, sienna_type: SiennaInvestmentsComponent, recorder: ScopedRecorder
) -> None:
    """Carry one type over, reshaping the two fields whose shape differs."""
    source = state.source_topology.get(sienna_type)
    if source is None:
        return
    rows = [
        _map_one(dict(row), sienna_type, recorder) for row in source.collect().iter_rows(named=True)
    ]
    state.destination_tables[str(sienna_type)] = pl.DataFrame(rows)


def _map_one(
    row: dict[str, Any], sienna_type: SiennaInvestmentsComponent, recorder: ScopedRecorder
) -> dict[str, Any]:
    name = row[SIENNA_NAME_COLUMN]
    if sienna_type is SiennaInvestmentsComponent.STORAGE_TECHNOLOGY:
        _split_storage_capital_costs(row, name, recorder)
    elif SiennaSupplyTechnologyCol.CAPITAL_COSTS in row:
        _unwrap_capital_costs(row, sienna_type, name, recorder)
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


def _unwrap_capital_costs(
    row: dict[str, Any],
    sienna_type: SiennaInvestmentsComponent,
    name: str,
    recorder: ScopedRecorder,
) -> None:
    """The package's field is one value curve, where the schema wraps it beside a second cost."""
    wrapper = row.pop(SiennaSupplyTechnologyCol.CAPITAL_COSTS, None) or {}
    row[SiennaSupplyTechnologyCol.CAPITAL_COSTS] = _build_value_curve(
        wrapper.get(SiennaCapitalCostField.CAPITAL_COST)
    )
    record_translation(
        recorder,
        component=str(sienna_type),
        name=name,
        source_field=f"{SiennaSupplyTechnologyCol.CAPITAL_COSTS}."
        f"{SiennaCapitalCostField.CAPITAL_COST}",
        source_value=wrapper.get(SiennaCapitalCostField.CAPITAL_COST),
        destination_field=SiennaSupplyTechnologyCol.CAPITAL_COSTS,
        destination_value=row[SiennaSupplyTechnologyCol.CAPITAL_COSTS],
        derivation="CapitalCost -> the value curve the field holds, tagged InputOutputCurve",
    )
    _report_interconnection_cost(wrapper, str(sienna_type), name, recorder)


def _split_storage_capital_costs(row: dict[str, Any], name: str, recorder: ScopedRecorder) -> None:
    """One struct becomes three value curves, one per thing a plan may add to a store."""
    wrapper = row.pop(SiennaStorageTechnologyCol.CAPITAL_COSTS, None) or {}
    for source_field, destination_field in _STORAGE_CAPITAL_COST_FIELDS:
        row[destination_field] = _build_value_curve(wrapper.get(source_field))
        record_translation(
            recorder,
            component=SiennaInvestmentsComponent.STORAGE_TECHNOLOGY.value,
            name=name,
            source_field=f"{SiennaStorageTechnologyCol.CAPITAL_COSTS}.{source_field}",
            source_value=wrapper.get(source_field),
            destination_field=destination_field,
            destination_value=row[destination_field],
            derivation="StorageCapitalCost -> one value curve per capacity a plan may add",
        )
    _report_interconnection_cost(
        wrapper, SiennaInvestmentsComponent.STORAGE_TECHNOLOGY.value, name, recorder
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
    _fill_storage_cost(prepared, sienna_type, name, recorder)
    return build_operation_cost(prepared, recorder, str(sienna_type), name)


def _fill_storage_cost(
    cost: dict[str, Any],
    sienna_type: SiennaInvestmentsComponent,
    name: str,
    recorder: ScopedRecorder,
) -> None:
    """A StorageCost states a price for spilling and for falling short; SiennaSchemas does not."""
    if sienna_type is not SiennaInvestmentsComponent.STORAGE_TECHNOLOGY:
        return
    for field in _STORAGE_COST_DEFAULTS:
        cost.setdefault(field, _NO_COST)
        record_default(
            recorder,
            component=str(sienna_type),
            name=name,
            field=f"{SiennaStorageTechnologyCol.OPERATION_COSTS}.{field}",
            value=_NO_COST,
            derivation="the destination requires the field and the source states no price",
        )
