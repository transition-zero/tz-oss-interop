from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.extensions import (
    ExtensionKind,
    ExtensionLookup,
    ExtensionReader,
    StorageCompanionCol,
    StorageExtension,
)
from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import UNSCALED
from interop.plugins.shared.pypsa_constants import (
    STORAGE_UNITS_DESTINATION_SCHEMA,
    PyPSACarrier,
    PyPSADestinationTable,
    PyPSAStorageUnitCol,
)
from interop.plugins.shared.pypsa_time_series import (
    append_metadata,
    metadata_row,
    series_components,
    series_timing,
)
from interop.plugins.shared.sienna_constants import (
    PrimeMover,
    SiennaComponent,
    SiennaGeneratorCol,
    SiennaSeriesName,
    SiennaStorageCol,
    SiennaStructField,
    SiennaTable,
)
from interop.plugins.shared.sienna_pypsa_translations.companion_series import (
    CompanionColumn,
    stage_companion_columns,
)
from interop.plugins.shared.sienna_pypsa_translations.constants import (
    ASSUMED_HYDRO_EFFICIENCY_DISPATCH,
    DEFAULT_HYDRO_MAX_HOURS,
    DEFAULT_STORAGE_EFFICIENCY,
    pypsa_carrier,
)
from interop.plugins.shared.sienna_pypsa_translations.mapped_fields import (
    HYDRO_CARRIED,
    HYDRO_MAPPED_FIELDS,
    STORAGE_CARRIED,
    STORAGE_CARRIER,
    STORAGE_EXTENDABLE,
    STORAGE_INFLOW,
    STORAGE_MAPPED_FIELDS,
    build_carried_values,
    record_carried_fields,
    record_carried_value,
)
from interop.plugins.shared.sienna_pypsa_translations.mapping import (
    CapacityFloor,
    bus_id_to_name,
    choose_p_nom_min,
    per_unit_of,
    record_p_nom_min,
    variable_proportional_term,
)
from interop.plugins.shared.sienna_pypsa_translations.overnight_cost import (
    STORAGE_OVERNIGHT_COST,
    UnpricedCost,
    find_overnight_cost,
    find_unpriced_cost,
    report_unpriced_costs,
)
from interop.plugins.shared.sienna_pypsa_translations.relay import relay_records
from interop.plugins.shared.sienna_pypsa_translations.reporters import StorageUnitReporter

_OUTPUT_LIMITS_MAX = f"{SiennaStorageCol.OUTPUT_ACTIVE_POWER_LIMITS}.{SiennaStructField.MAX}"
# PyPSA's own state_of_charge_initial: a reservoir that starts empty.
_EMPTY_RESERVOIR = 0.0

# What the storage companion parquet holds. Sienna names no field for an inflow or for a
# rating that changes, so both arrive beside the sidecar rather than in the system file.
_COMPANION_COLUMNS: tuple[CompanionColumn, ...] = (
    CompanionColumn(
        StorageCompanionCol.INFLOW_MW,
        PyPSADestinationTable.STORAGE_UNITS,
        PyPSAStorageUnitCol.INFLOW,
    ),
    CompanionColumn(
        StorageCompanionCol.RATING_PU,
        PyPSADestinationTable.STORAGE_UNITS,
        PyPSAStorageUnitCol.P_MAX_PU,
    ),
)


class SiennaToPypsaMapStorageUnits(TranslationStep):
    name: ClassVar[str] = "sienna_to_pypsa_map_storage_units"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder, extensions: ExtensionReader) -> None:
        self._recorder = recorder
        self._extensions = extensions

    def run(self, state: State, params: BaseModel | None) -> State:
        bus_names = bus_id_to_name(state)
        reporter = StorageUnitReporter(self._recorder)
        rows: list[dict[str, Any]] = []
        hydro_base_power: dict[str, float] = {}

        generators = state.source_topology.get(SiennaTable.GENERATORS)
        if generators is not None:
            for row in generators.collect().iter_rows(named=True):
                if SiennaComponent(row[SiennaGeneratorCol.SIENNA_TYPE]) is (
                    SiennaComponent.HYDRO_DISPATCH
                ):
                    hydro = _derive_hydro(row, bus_names, self._extensions)
                    _record_hydro(reporter, hydro)
                    rows.append(_hydro_row(hydro))
                    hydro_base_power[hydro.name] = hydro.base_power

        storage = state.source_topology.get(SiennaTable.STORAGE)
        unpriced: list[UnpricedCost] = []
        if storage is not None:
            extensions = self._extensions.read(ExtensionKind.STORAGE)
            for row in storage.collect().iter_rows(named=True):
                if SiennaComponent(row[SiennaStorageCol.SIENNA_TYPE]) is (
                    SiennaComponent.ENERGY_RESERVOIR_STORAGE
                ):
                    phs = _derive_phs(row, bus_names, extensions)
                    _record_phs(reporter, phs)
                    rows.append(_phs_row(phs))
                    if phs.unpriced_cost is not None:
                        unpriced.append(phs.unpriced_cost)
        report_unpriced_costs(reporter, unpriced)

        if rows:
            state.destination_tables[PyPSADestinationTable.STORAGE_UNITS] = pl.DataFrame(
                rows, schema=STORAGE_UNITS_DESTINATION_SCHEMA
            )
            self._record_hydro_inflow(state, hydro_base_power)
            stage_companion_columns(
                state,
                ExtensionKind.STORAGE,
                _COMPANION_COLUMNS,
                dict.fromkeys((row[PyPSAStorageUnitCol.NAME] for row in rows), UNSCALED),
            )
            self._carry_on(
                state, [row[PyPSAStorageUnitCol.NAME] for row in rows], list(hydro_base_power)
            )
        return state

    def _carry_on(self, state: State, names: list[str], hydro_names: list[str]) -> None:
        """Pass on each unmapped field of a unit's records, with a hydro unit's generator record."""
        relay_records(state, self._extensions.read(ExtensionKind.STORAGE), names, self._recorder)
        generators = self._extensions.read(ExtensionKind.GENERATOR)
        relay_records(state, generators, hydro_names, self._recorder)

    def _record_hydro_inflow(self, state: State, hydro_base_power: dict[str, float]) -> None:
        frame = state.source_time_series.get(
            (SiennaComponent.HYDRO_DISPATCH, SiennaSeriesName.HYDRO_BUDGET)
        )
        if frame is None:
            return
        timing = series_timing(frame)
        metadata_rows: list[dict[str, Any]] = []
        for component in series_components(frame):
            base_power = hydro_base_power[component]
            # efficiency_dispatch is assumed unity (folded into hydro_budget and lost), so the
            # division is documentary and its operator mutation is a no-op.
            scaling_factor = base_power / ASSUMED_HYDRO_EFFICIENCY_DISPATCH  # pragma: no mutate
            metadata_rows.append(
                metadata_row(
                    component_table=PyPSADestinationTable.STORAGE_UNITS,
                    component_name=component,
                    attribute=PyPSAStorageUnitCol.INFLOW,
                    source_owner_type=SiennaComponent.HYDRO_DISPATCH,
                    source_series_name=SiennaSeriesName.HYDRO_BUDGET,
                    scaling_factor=scaling_factor,
                    timing=timing,
                )
            )
        append_metadata(state, metadata_rows)


def _record_inflow(
    reporter: StorageUnitReporter, sienna_type: SiennaComponent, name: str, inflow: float
) -> None:
    """A reservoir that states an inflow refills at it; one that states none refills at zero."""
    if inflow:
        record_carried_value(reporter, sienna_type, name, STORAGE_INFLOW, inflow)
    else:
        reporter.record_inflow_default(name)


@dataclass(frozen=True)
class _HydroMapping:
    """Values derived from one Sienna HydroDispatch row, before events and the output row."""

    name: str
    bus_id: int
    bus_name: str
    prime_mover: PrimeMover
    carrier: PyPSACarrier
    base_power: float
    rating: float
    active_power_min: float
    p_min_pu: float
    marginal_cost: float
    # Sienna's HydroDispatch states no reservoir, so the storage record of the unit states it.
    ext: StorageExtension
    inflow_mw: float


def _derive_hydro(
    row: dict[str, Any], bus_names: dict[int, str], extensions: ExtensionReader
) -> _HydroMapping:
    base_power = float(row[SiennaGeneratorCol.BASE_POWER])
    carried = extensions.read(ExtensionKind.STORAGE).get_fields(
        str(row[SiennaGeneratorCol.NAME]), HYDRO_MAPPED_FIELDS
    )
    active_power_min = float(row[SiennaGeneratorCol.ACTIVE_POWER_LIMITS][SiennaStructField.MIN])
    prime_mover = PrimeMover(row[SiennaGeneratorCol.PRIME_MOVER_TYPE])
    bus_id = row[SiennaGeneratorCol.BUS]
    return _HydroMapping(
        name=row[SiennaGeneratorCol.NAME],
        bus_id=bus_id,
        bus_name=bus_names[bus_id],
        prime_mover=prime_mover,
        carrier=pypsa_carrier(SiennaComponent.HYDRO_DISPATCH, prime_mover, None),
        base_power=base_power,
        rating=float(row[SiennaGeneratorCol.RATING]),
        active_power_min=active_power_min,
        p_min_pu=per_unit_of(active_power_min, base_power),
        marginal_cost=variable_proportional_term(
            row[SiennaGeneratorCol.OPERATION_COST], SiennaStructField.VARIABLE
        ),
        ext=carried,
        inflow_mw=float(carried.inflow_mw or 0.0),
    )


def _fill_hydro_defaults(carried: dict[str, object]) -> dict[str, object]:
    """The reservoir that the storage record states, with PyPSA's default where it states none."""
    defaults = {
        PyPSAStorageUnitCol.MAX_HOURS: DEFAULT_HYDRO_MAX_HOURS,
        PyPSAStorageUnitCol.STATE_OF_CHARGE_INITIAL: _EMPTY_RESERVOIR,
    }
    return {
        column: defaults[column] if value is None else value for column, value in carried.items()
    }


def _record_hydro(reporter: StorageUnitReporter, m: _HydroMapping) -> None:
    sienna_type = SiennaComponent.HYDRO_DISPATCH
    reporter.record_bus(sienna_type, m.name, m.bus_id, m.bus_name)
    reporter.record_p_nom(sienna_type, m.name, m.base_power)
    reporter.record_p_max_pu(
        sienna_type, m.name, SiennaGeneratorCol.RATING, m.rating, m.rating, "rating -> p_max_pu"
    )
    reporter.record_p_min_pu_from_active_power_limits(m.name, m.active_power_min, m.p_min_pu)
    reporter.record_marginal_cost(sienna_type, m.name, m.marginal_cost)
    reporter.record_carrier_from_prime_mover(sienna_type, m.name, m.prime_mover, m.carrier)
    record_carried_fields(reporter, sienna_type, m.ext, HYDRO_CARRIED)
    # Sienna states no reservoir for a HydroDispatch, so a field the storage record does not
    # state falls back to a PyPSA default. Lossy.
    if m.ext.max_hours is None:
        reporter.record_max_hours_default(m.name, DEFAULT_HYDRO_MAX_HOURS)
    if m.ext.state_of_charge_initial is None:
        reporter.record_state_of_charge_initial_default(m.name)
    reporter.record_efficiency_default(m.name, DEFAULT_STORAGE_EFFICIENCY)
    reporter.record_cyclic_default(m.name)
    reporter.record_p_nom_extendable_default(m.name)
    _record_inflow(reporter, SiennaComponent.HYDRO_DISPATCH, m.name, m.inflow_mw)


def _hydro_row(m: _HydroMapping) -> dict[str, Any]:
    return {
        PyPSAStorageUnitCol.NAME: m.name,
        PyPSAStorageUnitCol.BUS: m.bus_name,
        PyPSAStorageUnitCol.CARRIER: m.carrier,
        PyPSAStorageUnitCol.P_NOM: m.base_power,
        PyPSAStorageUnitCol.P_MIN_PU: m.p_min_pu,
        PyPSAStorageUnitCol.P_MAX_PU: m.rating,
        **_fill_hydro_defaults(build_carried_values(m.ext, HYDRO_CARRIED)),
        PyPSAStorageUnitCol.EFFICIENCY_STORE: DEFAULT_STORAGE_EFFICIENCY,
        PyPSAStorageUnitCol.EFFICIENCY_DISPATCH: DEFAULT_STORAGE_EFFICIENCY,
        PyPSAStorageUnitCol.MARGINAL_COST: m.marginal_cost,
        PyPSAStorageUnitCol.INFLOW: m.inflow_mw,
        PyPSAStorageUnitCol.CYCLIC_STATE_OF_CHARGE: False,
        # HydroDispatch is sourced from a PyPSA Generator and carries no extensions sidecar,
        # so p_nom_extendable is not recoverable; falls back to the PyPSA default. Lossy.
        PyPSAStorageUnitCol.P_NOM_EXTENDABLE: False,
    }


@dataclass(frozen=True)
class _PhsMapping:
    """Values derived from one EnergyReservoirStorage row, before events and the output row."""

    name: str
    bus_id: int
    bus_name: str
    prime_mover: PrimeMover
    carrier: PyPSACarrier
    # The sidecar names a carrier that a prime mover cannot, such as an OSeMOSYS category.
    ext_carrier: str | None
    base_power: float
    output_max: float
    input_max: float
    p_min_pu: float
    storage_capacity: float
    initial_level: float
    state_of_charge_initial: float
    efficiency_store: float
    efficiency_dispatch: float
    marginal_cost: float
    cyclic: bool
    p_nom_extendable: bool
    p_nom_extendable_from_ext: bool
    floor: CapacityFloor
    # Sienna states one rating, no build, no inflow and no cycle, so each of these reaches a
    # PyPSA storage unit only through the sidecar.
    ext: StorageExtension
    overnight_cost: float | None
    # The network leaves out a cost that the record states with no discount rate.
    unpriced_cost: UnpricedCost | None
    inflow_mw: float


def _derive_phs(
    row: dict[str, Any],
    bus_names: dict[int, str],
    extensions: ExtensionLookup[StorageExtension],
) -> _PhsMapping:
    base_power = float(row[SiennaStorageCol.BASE_POWER])
    ext = extensions.get_fields(row[SiennaStorageCol.NAME], STORAGE_MAPPED_FIELDS)
    storage_capacity = float(row[SiennaStorageCol.STORAGE_CAPACITY])
    initial_level = float(row[SiennaStorageCol.INITIAL_STORAGE_CAPACITY_LEVEL])
    input_max = float(row[SiennaStorageCol.INPUT_ACTIVE_POWER_LIMITS][SiennaStructField.MAX])
    efficiency = row[SiennaStorageCol.EFFICIENCY]
    operation_cost = row[SiennaStorageCol.OPERATION_COST]
    prime_mover = PrimeMover(row[SiennaStorageCol.PRIME_MOVER_TYPE])
    bus_id = row[SiennaStorageCol.BUS]
    return _PhsMapping(
        name=row[SiennaStorageCol.NAME],
        bus_id=bus_id,
        bus_name=bus_names[bus_id],
        prime_mover=prime_mover,
        carrier=pypsa_carrier(SiennaComponent.ENERGY_RESERVOIR_STORAGE, prime_mover, None),
        ext_carrier=ext.carrier,
        base_power=base_power,
        output_max=float(row[SiennaStorageCol.OUTPUT_ACTIVE_POWER_LIMITS][SiennaStructField.MAX]),
        input_max=input_max,
        p_min_pu=-input_max,
        storage_capacity=storage_capacity,
        initial_level=initial_level,
        state_of_charge_initial=initial_level * base_power * storage_capacity,
        efficiency_store=float(efficiency[SiennaStructField.IN]),
        efficiency_dispatch=float(efficiency[SiennaStructField.OUT]),
        marginal_cost=variable_proportional_term(
            operation_cost, SiennaStructField.DISCHARGE_VARIABLE_COST
        ),
        cyclic=float(operation_cost.get(SiennaStructField.ENERGY_SHORTAGE_COST, 0.0)) > 0.0,
        ext=ext,
        overnight_cost=find_overnight_cost(extensions, ext),
        unpriced_cost=find_unpriced_cost(SiennaComponent.ENERGY_RESERVOIR_STORAGE, ext),
        inflow_mw=float(ext.inflow_mw or 0.0),
        p_nom_extendable=ext.p_nom_extendable is True,
        p_nom_extendable_from_ext=ext.p_nom_extendable is not None,
        floor=choose_p_nom_min(ext.p_nom_min, base_power, ext.p_nom_extendable),
    )


def _record_phs(reporter: StorageUnitReporter, m: _PhsMapping) -> None:
    sienna_type = SiennaComponent.ENERGY_RESERVOIR_STORAGE
    reporter.record_bus(sienna_type, m.name, m.bus_id, m.bus_name)
    reporter.record_p_nom(sienna_type, m.name, m.base_power)
    reporter.record_max_hours(m.name, m.storage_capacity)
    reporter.record_p_max_pu(
        sienna_type,
        m.name,
        _OUTPUT_LIMITS_MAX,
        m.output_max,
        m.output_max,
        "output_active_power_limits.max -> p_max_pu",
    )
    reporter.record_p_min_pu_negate_input(m.name, m.input_max, m.p_min_pu)
    reporter.record_efficiency(m.name, m.efficiency_store, m.efficiency_dispatch)
    reporter.record_marginal_cost(sienna_type, m.name, m.marginal_cost)
    reporter.record_state_of_charge_initial(m.name, m.initial_level, m.state_of_charge_initial)
    reporter.record_cyclic(m.name, m.cyclic)
    if m.ext_carrier is not None:
        record_carried_value(reporter, sienna_type, m.name, STORAGE_CARRIER, m.ext_carrier)
    else:
        reporter.record_carrier_from_prime_mover(sienna_type, m.name, m.prime_mover, m.carrier)
    if m.p_nom_extendable_from_ext:
        record_carried_value(reporter, sienna_type, m.name, STORAGE_EXTENDABLE, m.p_nom_extendable)
    else:
        reporter.record_p_nom_extendable_default(m.name)
    _record_inflow(reporter, sienna_type, m.name, m.inflow_mw)
    record_p_nom_min(reporter, sienna_type, m.name, m.floor)
    record_carried_fields(reporter, sienna_type, m.ext, STORAGE_CARRIED)
    if m.overnight_cost is not None:
        record_carried_value(
            reporter, sienna_type, m.name, STORAGE_OVERNIGHT_COST, m.overnight_cost
        )


def _phs_row(m: _PhsMapping) -> dict[str, Any]:
    return {
        PyPSAStorageUnitCol.NAME: m.name,
        PyPSAStorageUnitCol.BUS: m.bus_name,
        PyPSAStorageUnitCol.CARRIER: m.ext_carrier if m.ext_carrier is not None else m.carrier,
        PyPSAStorageUnitCol.P_NOM: m.base_power,
        PyPSAStorageUnitCol.P_MIN_PU: m.p_min_pu,
        PyPSAStorageUnitCol.P_MAX_PU: m.output_max,
        PyPSAStorageUnitCol.MAX_HOURS: m.storage_capacity,
        PyPSAStorageUnitCol.EFFICIENCY_STORE: m.efficiency_store,
        PyPSAStorageUnitCol.EFFICIENCY_DISPATCH: m.efficiency_dispatch,
        PyPSAStorageUnitCol.MARGINAL_COST: m.marginal_cost,
        PyPSAStorageUnitCol.STATE_OF_CHARGE_INITIAL: m.state_of_charge_initial,
        PyPSAStorageUnitCol.CYCLIC_STATE_OF_CHARGE: m.cyclic,
        PyPSAStorageUnitCol.P_NOM_EXTENDABLE: m.p_nom_extendable,
        PyPSAStorageUnitCol.P_NOM_MIN: m.floor.value,
        PyPSAStorageUnitCol.OVERNIGHT_COST: m.overnight_cost,
        **build_carried_values(m.ext, STORAGE_CARRIED),
        PyPSAStorageUnitCol.INFLOW: m.inflow_mw,
    }
