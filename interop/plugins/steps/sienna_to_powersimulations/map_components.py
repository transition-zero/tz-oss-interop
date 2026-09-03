"""Step: assign PowerSystems.jl UUIDs and resolve integer FK columns.

All SiennaSchemas integer IDs are replaced with UUID strings. Integer FK columns
(bus, arc) become UUID columns. The fuel_type column is renamed to fuel on
ThermalStandard rows. Arc components are derived from line/link topology.
Operation cost dicts and HVDC loss curves are converted from Sienna format to PS.jl
format (including nested __metadata__ type tags) with full translation events.
Top-level component __metadata__ and PS.jl envelope fields are not added here —
that is sink formatting.
"""

from __future__ import annotations

import uuid as _uuid
from typing import Any, ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import Framework
from interop.plugins.shared.power_simulations_schema import (
    PowerSimulationsCol,
    PSInputOutputCurve,
    PSLinearFunctionData,
)
from interop.plugins.shared.sienna_constants import (
    ACBusType,
    SiennaACBusCol,
    SiennaArcCol,
    SiennaAreaCol,
    SiennaComponent,
    SiennaCurveType,
    SiennaFunctionType,
    SiennaGeneratorCol,
    SiennaLineCol,
    SiennaLinkCol,
    SiennaRenewableGeneratorCol,
    SiennaStructField,
    SiennaTable,
)
from interop.plugins.steps.sienna_to_powersimulations._cost_events import build_operation_cost
from interop.ports.outbound.reporting import (
    DestinationField,
    EventKind,
    SourceField,
    TranslationEvent,
)

_FK_DERIVATION = "integer id -> uuid"
_BUS_FK_DERIVATION = "integer bus id -> bus uuid"
_ARC_FK_DERIVATION = "integer arc id -> arc uuid"
_FUEL_RENAME_DERIVATION = "fuel_type -> fuel (field rename)"
_PER_UNIT_SCALING_DERIVATION = "natural-unit MW / base_power MVA -> per-unit for PS.jl"
_THERMAL_MUST_RUN_DEFAULT = False
_THERMAL_TIME_AT_STATUS_DEFAULT = 10000.0
_RENEWABLE_POWER_FACTOR_DEFAULT = 1.0

# Per-unit fields by component type: (scalar_fields, dict_fields).
# PS.jl stores all :mva-tagged fields divided by the component's own base_power.
_PER_UNIT_FIELDS: dict[SiennaComponent, tuple[tuple[str, ...], tuple[str, ...]]] = {
    SiennaComponent.POWER_LOAD: (
        ("active_power", "max_active_power", "reactive_power", "max_reactive_power"),
        (),
    ),
    SiennaComponent.INTERRUPTIBLE_POWER_LOAD: (
        ("active_power", "max_active_power", "reactive_power", "max_reactive_power"),
        (),
    ),
    SiennaComponent.THERMAL_STANDARD: (
        ("active_power", "reactive_power", "rating"),
        ("active_power_limits", "reactive_power_limits", "ramp_limits"),
    ),
    SiennaComponent.RENEWABLE_DISPATCH: (
        ("active_power", "reactive_power", "rating"),
        ("reactive_power_limits",),
    ),
    SiennaComponent.RENEWABLE_NON_DISPATCH: (
        ("active_power", "reactive_power", "rating"),
        ("reactive_power_limits",),
    ),
    SiennaComponent.HYDRO_DISPATCH: (
        ("active_power", "reactive_power", "rating"),
        ("active_power_limits", "reactive_power_limits", "ramp_limits"),
    ),
    SiennaComponent.ENERGY_RESERVOIR_STORAGE: (
        # active_power / reactive_power are in natural-unit MW (always 0.0 in practice).
        # rating, storage_capacity, input/output_active_power_limits are already in
        # per-unit of base_power (or hours) in SiennaSchemas — do NOT divide again.
        ("active_power", "reactive_power"),
        (),
    ),
}

_ARC_BACKED_TEMP_COLS = (
    SiennaLineCol.SIENNA_TYPE,
    SiennaLineCol.ARC,
    SiennaLineCol.BUS0,
    SiennaLineCol.BUS1,
)

_COST_BEARING_TYPES: frozenset[SiennaComponent] = frozenset(
    {
        SiennaComponent.THERMAL_STANDARD,
        SiennaComponent.RENEWABLE_DISPATCH,
        SiennaComponent.RENEWABLE_NON_DISPATCH,
        SiennaComponent.HYDRO_DISPATCH,
        SiennaComponent.ENERGY_RESERVOIR_STORAGE,
        SiennaComponent.INTERRUPTIBLE_POWER_LOAD,
    }
)

_NULLABLE_FIELDS_BY_TYPE: dict[SiennaComponent, tuple[str, ...]] = {
    SiennaComponent.THERMAL_STANDARD: ("reactive_power_limits", "ramp_limits", "time_limits"),
    SiennaComponent.RENEWABLE_DISPATCH: ("reactive_power_limits", "operation_cost"),
    SiennaComponent.RENEWABLE_NON_DISPATCH: ("reactive_power_limits", "operation_cost"),
    SiennaComponent.HYDRO_DISPATCH: ("reactive_power_limits", "ramp_limits", "time_limits"),
    SiennaComponent.ENERGY_RESERVOIR_STORAGE: ("reactive_power_limits",),
}


class _UuidRegistry:
    """Two-pass UUID registry: assign in pass 1, resolve in pass 2."""

    def __init__(self) -> None:
        self._by_type_id: dict[tuple[str, int], str] = {}
        self._by_area_name: dict[str, str] = {}

    def assign(self, component: SiennaComponent, int_id: int) -> str:
        key = (component.value, int_id)
        if key not in self._by_type_id:
            self._by_type_id[key] = str(_uuid.uuid4())
        return self._by_type_id[key]

    def get(self, component: SiennaComponent, int_id: int) -> str:
        return self._by_type_id[(component.value, int_id)]

    def assign_area(self, area_name: str) -> str:
        if area_name not in self._by_area_name:
            self._by_area_name[area_name] = str(_uuid.uuid4())
        return self._by_area_name[area_name]

    def get_area(self, area_name: str) -> str:
        return self._by_area_name[area_name]


class SiennaToPowerSimulationsMapComponents(TranslationStep):
    name: ClassVar[str] = "sienna_to_powersimulations_map_components"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def run(self, state: State, params: BaseModel | None) -> State:
        registry = _UuidRegistry()

        # Pass 1: assign UUIDs to every component
        _assign_bus_uuids(state, registry)
        _assign_area_uuids(state, registry)
        _assign_typed_uuids(state, registry, SiennaTable.GENERATORS)
        _assign_typed_uuids(state, registry, SiennaTable.STORAGE)
        _assign_typed_uuids(state, registry, SiennaTable.LOADS)
        _assign_line_arc_uuids(state, registry, SiennaTable.LINES)
        _assign_line_arc_uuids(state, registry, SiennaTable.LINKS)

        # Pass 2: build destination tables
        _map_buses(state, registry, self._recorder)
        _map_areas(state, registry, self._recorder)
        _map_arcs(state, registry, self._recorder)
        _map_bus_backed_component(state, registry, self._recorder, SiennaTable.GENERATORS)
        _map_bus_backed_component(state, registry, self._recorder, SiennaTable.STORAGE)
        _map_bus_backed_component(state, registry, self._recorder, SiennaTable.LOADS)
        _map_arc_backed_component(state, registry, self._recorder, SiennaTable.LINES)
        _map_arc_backed_component(state, registry, self._recorder, SiennaTable.LINKS)

        return state


# ---------------------------------------------------------------------------
# Pass 1: UUID assignment
# ---------------------------------------------------------------------------


def _assign_bus_uuids(state: State, registry: _UuidRegistry) -> None:
    source = state.source_topology.get(SiennaTable.BUSES)
    if source is None:
        return
    for row in source.collect().iter_rows(named=True):
        registry.assign(SiennaComponent.AC_BUS, row[SiennaACBusCol.ID])


def _assign_area_uuids(state: State, registry: _UuidRegistry) -> None:
    source = state.source_topology.get(SiennaTable.BUSES)
    if source is None:
        return
    for row in source.collect().iter_rows(named=True):
        area = row.get(SiennaACBusCol.AREA)
        if area is not None:
            registry.assign_area(area)


def _assign_typed_uuids(state: State, registry: _UuidRegistry, table_key: str) -> None:
    source = state.source_topology.get(table_key)
    if source is None:
        return
    for row in source.collect().iter_rows(named=True):
        sienna_type = SiennaComponent(row[SiennaGeneratorCol.SIENNA_TYPE])
        registry.assign(sienna_type, row[SiennaGeneratorCol.ID])


def _assign_line_arc_uuids(state: State, registry: _UuidRegistry, table_key: str) -> None:
    source = state.source_topology.get(table_key)
    if source is None:
        return
    for row in source.collect().iter_rows(named=True):
        sienna_type = SiennaComponent(row[SiennaLineCol.SIENNA_TYPE])
        registry.assign(sienna_type, row[SiennaLineCol.ID])
        registry.assign(SiennaComponent.ARC, row[SiennaLineCol.ARC])


# ---------------------------------------------------------------------------
# Pass 2: per-unit scaling
# ---------------------------------------------------------------------------


def _record_per_unit_event(
    recorder: ScopedRecorder,
    sienna_type: SiennaComponent,
    component_name: str,
    field: str,
    natural_val: Any,
    per_unit_val: Any,
) -> None:
    recorder.append(
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                SourceField(Framework.SIENNA, sienna_type.value, component_name, field, natural_val)
            ],
            destinations=[
                DestinationField(
                    Framework.POWER_SIMULATIONS,
                    sienna_type.value,
                    component_name,
                    field,
                    per_unit_val,
                )
            ],
            derivation=_PER_UNIT_SCALING_DERIVATION,
        )
    )


def _normalise_power_fields_to_per_unit(
    dest_row: dict[str, Any],
    sienna_type: SiennaComponent,
    component_name: str,
    recorder: ScopedRecorder,
) -> None:
    """Divide all :mva-tagged power fields by base_power before writing to the destination table.

    PS.jl stores every field marked :mva in per-unit (divided by the component's own
    base_power). SiennaSchemas carries those fields in natural units (MW/MVA), so we must
    scale them here or PS.jl will multiply by base_power a second time on read, producing
    values that are base_power× too large (e.g. 200 MW stored as 200 pu → read back as
    200 × 200 = 40 000 MW).
    """
    if sienna_type not in _PER_UNIT_FIELDS:
        return
    base_power = float(dest_row.get(SiennaGeneratorCol.BASE_POWER) or 1.0)
    scalars, dicts = _PER_UNIT_FIELDS[sienna_type]
    for field in scalars:
        v = dest_row.get(field)
        if v is None:
            continue
        natural_val = float(v)
        per_unit_val = natural_val / base_power
        dest_row[field] = per_unit_val
        _record_per_unit_event(
            recorder, sienna_type, component_name, field, natural_val, per_unit_val
        )
    for field in dicts:
        v = dest_row.get(field)
        if not isinstance(v, dict):
            continue
        natural_dict = {k: float(w) for k, w in v.items()}
        per_unit_dict = {k: w / base_power for k, w in natural_dict.items()}
        dest_row[field] = per_unit_dict
        _record_per_unit_event(
            recorder, sienna_type, component_name, field, natural_dict, per_unit_dict
        )


# ---------------------------------------------------------------------------
# Pass 2: recording helpers
# ---------------------------------------------------------------------------


def _uuid_event(
    sienna_type: str, name: str, id_attr: str, int_id: int, uuid_str: str
) -> TranslationEvent:
    return TranslationEvent(
        kind=EventKind.VALUE_DERIVED,
        sources=[SourceField(Framework.SIENNA, sienna_type, name, id_attr, int_id)],
        destinations=[
            DestinationField(
                Framework.POWER_SIMULATIONS, sienna_type, name, PowerSimulationsCol.UUID, uuid_str
            )
        ],
        derivation=_FK_DERIVATION,
    )


def record_bus_translation(
    recorder: ScopedRecorder,
    bus_name: str,
    bus_id: int,
    bus_uuid: str,
    area_name: str | None,
    area_uuid: str | None,
    bustype_defaulted: bool,
) -> None:
    recorder.append(
        _uuid_event(SiennaComponent.AC_BUS.value, bus_name, SiennaACBusCol.ID, bus_id, bus_uuid)
    )
    if area_name is not None and area_uuid is not None:
        recorder.append(
            TranslationEvent(
                kind=EventKind.VALUE_DERIVED,
                sources=[
                    SourceField(
                        Framework.SIENNA,
                        SiennaComponent.AC_BUS.value,
                        bus_name,
                        SiennaACBusCol.AREA,
                        area_name,
                    )
                ],
                destinations=[
                    DestinationField(
                        Framework.POWER_SIMULATIONS,
                        SiennaComponent.AC_BUS.value,
                        bus_name,
                        PowerSimulationsCol.AREA,
                        area_uuid,
                    )
                ],
                derivation="area name -> area uuid",
            )
        )
    if bustype_defaulted:
        recorder.append(
            TranslationEvent(
                kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
                sources=[
                    SourceField(
                        Framework.SIENNA,
                        SiennaComponent.AC_BUS.value,
                        bus_name,
                        SiennaACBusCol.BUSTYPE,
                        None,
                    )
                ],
                destinations=[
                    DestinationField(
                        Framework.POWER_SIMULATIONS,
                        SiennaComponent.AC_BUS.value,
                        bus_name,
                        SiennaACBusCol.BUSTYPE,
                        ACBusType.PQ,
                    )
                ],
                derivation="bustype not specified, defaulting to PQ",
            )
        )


def record_area_translation(
    recorder: ScopedRecorder,
    area_name: str,
    area_uuid: str,
) -> None:
    recorder.append(
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                SourceField(
                    Framework.SIENNA,
                    SiennaComponent.AREA.value,
                    area_name,
                    SiennaAreaCol.NAME,
                    area_name,
                )
            ],
            destinations=[
                DestinationField(
                    Framework.POWER_SIMULATIONS,
                    SiennaComponent.AREA.value,
                    area_name,
                    PowerSimulationsCol.UUID,
                    area_uuid,
                )
            ],
            derivation="area name -> uuid",
        )
    )
    for field in ("load_response", "peak_active_power", "peak_reactive_power"):
        recorder.append(
            TranslationEvent(
                kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
                sources=[
                    SourceField(
                        Framework.SIENNA,
                        SiennaComponent.AREA.value,
                        area_name,
                        field,
                        None,
                    )
                ],
                destinations=[
                    DestinationField(
                        Framework.POWER_SIMULATIONS,
                        SiennaComponent.AREA.value,
                        area_name,
                        field,
                        0.0,
                    )
                ],
                derivation="field absent in SiennaSchemas source, defaulting to 0.0",
            )
        )


def record_arc_translation(
    recorder: ScopedRecorder,
    arc_name: str,
    arc_id: int,
    arc_uuid: str,
    bus0_id: int,
    bus0_uuid: str,
    bus1_id: int,
    bus1_uuid: str,
) -> None:
    recorder.append(
        _uuid_event(SiennaComponent.ARC.value, arc_name, SiennaArcCol.ID, arc_id, arc_uuid)
    )
    recorder.append(
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                SourceField(
                    Framework.SIENNA,
                    SiennaComponent.ARC.value,
                    arc_name,
                    SiennaLineCol.BUS0,
                    bus0_id,
                )
            ],
            destinations=[
                DestinationField(
                    Framework.POWER_SIMULATIONS,
                    SiennaComponent.ARC.value,
                    arc_name,
                    PowerSimulationsCol.FROM_BUS,
                    bus0_uuid,
                )
            ],
            derivation=_BUS_FK_DERIVATION,
        )
    )
    recorder.append(
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                SourceField(
                    Framework.SIENNA,
                    SiennaComponent.ARC.value,
                    arc_name,
                    SiennaLineCol.BUS1,
                    bus1_id,
                )
            ],
            destinations=[
                DestinationField(
                    Framework.POWER_SIMULATIONS,
                    SiennaComponent.ARC.value,
                    arc_name,
                    PowerSimulationsCol.TO_BUS,
                    bus1_uuid,
                )
            ],
            derivation=_BUS_FK_DERIVATION,
        )
    )


def record_bus_backed_translation(
    recorder: ScopedRecorder,
    sienna_type: str,
    comp_name: str,
    comp_id: int,
    comp_uuid: str,
    bus_id: int,
    bus_uuid: str,
    fuel: str | None = None,
) -> None:
    recorder.append(_uuid_event(sienna_type, comp_name, SiennaGeneratorCol.ID, comp_id, comp_uuid))
    recorder.append(
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                SourceField(
                    Framework.SIENNA, sienna_type, comp_name, SiennaGeneratorCol.BUS, bus_id
                )
            ],
            destinations=[
                DestinationField(
                    Framework.POWER_SIMULATIONS,
                    sienna_type,
                    comp_name,
                    PowerSimulationsCol.BUS,
                    bus_uuid,
                )
            ],
            derivation=_BUS_FK_DERIVATION,
        )
    )
    if fuel is not None:
        recorder.append(
            TranslationEvent(
                kind=EventKind.VALUE_DERIVED,
                sources=[
                    SourceField(
                        Framework.SIENNA, sienna_type, comp_name, SiennaGeneratorCol.FUEL_TYPE, fuel
                    )
                ],
                destinations=[
                    DestinationField(
                        Framework.POWER_SIMULATIONS,
                        sienna_type,
                        comp_name,
                        PowerSimulationsCol.FUEL,
                        fuel,
                    )
                ],
                derivation=_FUEL_RENAME_DERIVATION,
            )
        )


def record_arc_backed_translation(
    recorder: ScopedRecorder,
    sienna_type: str,
    comp_name: str,
    comp_id: int,
    comp_uuid: str,
    arc_id: int,
    arc_uuid: str,
) -> None:
    recorder.append(_uuid_event(sienna_type, comp_name, SiennaLineCol.ID, comp_id, comp_uuid))
    recorder.append(
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                SourceField(Framework.SIENNA, sienna_type, comp_name, SiennaLineCol.ARC, arc_id)
            ],
            destinations=[
                DestinationField(
                    Framework.POWER_SIMULATIONS,
                    sienna_type,
                    comp_name,
                    PowerSimulationsCol.ARC,
                    arc_uuid,
                )
            ],
            derivation=_ARC_FK_DERIVATION,
        )
    )


# ---------------------------------------------------------------------------
# Pass 2: destination table builders
# ---------------------------------------------------------------------------


def _map_buses(state: State, registry: _UuidRegistry, recorder: ScopedRecorder) -> None:
    source = state.source_topology.get(SiennaTable.BUSES)
    if source is None:
        return
    rows: list[dict[str, Any]] = []
    for row in source.collect().iter_rows(named=True):
        bus_id = row[SiennaACBusCol.ID]
        bus_name = row[SiennaACBusCol.NAME]
        bus_uuid = registry.get(SiennaComponent.AC_BUS, bus_id)
        area_name = row.get(SiennaACBusCol.AREA)
        area_uuid = registry.get_area(area_name) if area_name is not None else None

        out = dict(row)
        out.pop(SiennaACBusCol.AREA, None)
        out[PowerSimulationsCol.UUID] = bus_uuid
        out[PowerSimulationsCol.AREA] = area_uuid

        bustype_defaulted = out.get(SiennaACBusCol.BUSTYPE) is None
        if bustype_defaulted:
            out[SiennaACBusCol.BUSTYPE] = ACBusType.PQ

        record_bus_translation(
            recorder, bus_name, bus_id, bus_uuid, area_name, area_uuid, bustype_defaulted
        )
        rows.append(out)

    if rows:
        state.destination_tables[SiennaComponent.AC_BUS] = pl.DataFrame(rows)


def _map_areas(state: State, registry: _UuidRegistry, recorder: ScopedRecorder) -> None:
    source = state.source_topology.get(SiennaTable.BUSES)
    if source is None:
        return
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for row in source.collect().iter_rows(named=True):
        area_name = row.get(SiennaACBusCol.AREA)
        if area_name is None or area_name in seen:
            continue
        seen.add(area_name)
        area_uuid = registry.get_area(area_name)
        record_area_translation(recorder, area_name, area_uuid)
        rows.append(
            {
                "name": area_name,
                PowerSimulationsCol.UUID: area_uuid,
                "load_response": 0.0,
                "peak_active_power": 0.0,
                "peak_reactive_power": 0.0,
            }
        )

    if rows:
        state.destination_tables[SiennaComponent.AREA] = pl.DataFrame(rows)


def _map_arcs(state: State, registry: _UuidRegistry, recorder: ScopedRecorder) -> None:
    seen: set[int] = set()
    rows: list[dict[str, Any]] = []

    for table_key in (SiennaTable.LINES, SiennaTable.LINKS):
        source = state.source_topology.get(table_key)
        if source is None:
            continue
        for row in source.collect().iter_rows(named=True):
            arc_id = row[SiennaLineCol.ARC]
            if arc_id in seen:
                continue
            seen.add(arc_id)
            arc_uuid = registry.get(SiennaComponent.ARC, arc_id)
            bus0_id = row[SiennaLineCol.BUS0]
            bus1_id = row[SiennaLineCol.BUS1]
            bus0_uuid = registry.get(SiennaComponent.AC_BUS, bus0_id)
            bus1_uuid = registry.get(SiennaComponent.AC_BUS, bus1_id)

            record_arc_translation(
                recorder, str(arc_id), arc_id, arc_uuid, bus0_id, bus0_uuid, bus1_id, bus1_uuid
            )
            rows.append(
                {
                    "id": arc_id,
                    PowerSimulationsCol.UUID: arc_uuid,
                    PowerSimulationsCol.FROM_BUS: bus0_uuid,
                    PowerSimulationsCol.TO_BUS: bus1_uuid,
                }
            )

    if rows:
        state.destination_tables[SiennaComponent.ARC] = pl.DataFrame(rows)


def _map_bus_backed_component(
    state: State, registry: _UuidRegistry, recorder: ScopedRecorder, table_key: str
) -> None:
    source = state.source_topology.get(table_key)
    if source is None:
        return
    by_type: dict[SiennaComponent, list[dict[str, Any]]] = {}

    for row in source.collect().iter_rows(named=True):
        sienna_type = SiennaComponent(row[SiennaGeneratorCol.SIENNA_TYPE])
        comp_id = row[SiennaGeneratorCol.ID]
        comp_name = row[SiennaGeneratorCol.NAME]
        bus_id = row[SiennaGeneratorCol.BUS]
        comp_uuid = registry.get(sienna_type, comp_id)
        bus_uuid = registry.get(SiennaComponent.AC_BUS, bus_id)

        out = {
            k: v
            for k, v in row.items()
            if k not in (SiennaGeneratorCol.SIENNA_TYPE, SiennaGeneratorCol.BUS)
        }
        out[PowerSimulationsCol.UUID] = comp_uuid
        out[PowerSimulationsCol.BUS] = bus_uuid

        fuel: str | None = None
        if sienna_type == SiennaComponent.THERMAL_STANDARD:
            fuel = out.pop(SiennaGeneratorCol.FUEL_TYPE, None)
            out[PowerSimulationsCol.FUEL] = fuel
            if "must_run" not in out:
                out["must_run"] = _THERMAL_MUST_RUN_DEFAULT
                recorder.append(
                    TranslationEvent(
                        kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
                        sources=[
                            SourceField(
                                Framework.SIENNA,
                                SiennaComponent.THERMAL_STANDARD.value,
                                comp_name,
                                "must_run",
                                None,
                            )
                        ],
                        destinations=[
                            DestinationField(
                                Framework.POWER_SIMULATIONS,
                                SiennaComponent.THERMAL_STANDARD.value,
                                comp_name,
                                "must_run",
                                _THERMAL_MUST_RUN_DEFAULT,
                            )
                        ],
                        derivation="field absent in SiennaSchemas source, defaulting to false",
                    )
                )
            if "time_at_status" not in out:
                out["time_at_status"] = _THERMAL_TIME_AT_STATUS_DEFAULT
                recorder.append(
                    TranslationEvent(
                        kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
                        sources=[
                            SourceField(
                                Framework.SIENNA,
                                SiennaComponent.THERMAL_STANDARD.value,
                                comp_name,
                                "time_at_status",
                                None,
                            )
                        ],
                        destinations=[
                            DestinationField(
                                Framework.POWER_SIMULATIONS,
                                SiennaComponent.THERMAL_STANDARD.value,
                                comp_name,
                                "time_at_status",
                                _THERMAL_TIME_AT_STATUS_DEFAULT,
                            )
                        ],
                        derivation="absent in SiennaSchemas, default INFINITE_TIME (10000.0)",
                    )
                )

        if sienna_type in (
            SiennaComponent.RENEWABLE_DISPATCH,
            SiennaComponent.RENEWABLE_NON_DISPATCH,
        ) and (
            SiennaRenewableGeneratorCol.POWER_FACTOR not in out
            or out[SiennaRenewableGeneratorCol.POWER_FACTOR] is None
        ):
            out[SiennaRenewableGeneratorCol.POWER_FACTOR] = _RENEWABLE_POWER_FACTOR_DEFAULT
            recorder.append(
                TranslationEvent(
                    kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
                    sources=[
                        SourceField(
                            Framework.SIENNA,
                            sienna_type.value,
                            comp_name,
                            SiennaRenewableGeneratorCol.POWER_FACTOR,
                            None,
                        )
                    ],
                    destinations=[
                        DestinationField(
                            Framework.POWER_SIMULATIONS,
                            sienna_type.value,
                            comp_name,
                            SiennaRenewableGeneratorCol.POWER_FACTOR,
                            _RENEWABLE_POWER_FACTOR_DEFAULT,
                        )
                    ],
                    derivation="field absent in SiennaSchemas source, defaulting to 1.0 (unity power factor)",  # noqa: E501
                )
            )

        if sienna_type in _COST_BEARING_TYPES and SiennaGeneratorCol.OPERATION_COST in out:
            out[SiennaGeneratorCol.OPERATION_COST] = build_operation_cost(
                out[SiennaGeneratorCol.OPERATION_COST],
                recorder,
                sienna_type.value,
                comp_name,
            )

        for field in _NULLABLE_FIELDS_BY_TYPE.get(sienna_type, ()):
            out.setdefault(field, None)

        _normalise_power_fields_to_per_unit(out, sienna_type, comp_name, recorder)

        record_bus_backed_translation(
            recorder, sienna_type.value, comp_name, comp_id, comp_uuid, bus_id, bus_uuid, fuel
        )
        by_type.setdefault(sienna_type, []).append(out)

    for sienna_type, rows in by_type.items():
        state.destination_tables[sienna_type] = pl.DataFrame(rows)


def _convert_hvdc_loss(
    loss: dict[str, Any] | None,
    sienna_type: str,
    comp_name: str,
    recorder: ScopedRecorder,
) -> dict[str, Any]:
    """Convert a SiennaSchemas loss curve to the PS.jl InputOutputCurve format.

    Julia cannot deserialize Union{LinearCurve, PiecewiseIncrementalCurve} without a
    __metadata__ type tag to pick the concrete type. We add it here.
    """
    if loss is None:
        ps_loss = PSInputOutputCurve(
            function_data=PSLinearFunctionData(proportional_term=0.0, constant_term=0.0)
        )
        recorder.append(
            TranslationEvent(
                kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
                sources=[
                    SourceField(Framework.SIENNA, sienna_type, comp_name, SiennaLinkCol.LOSS, None)
                ],
                destinations=[
                    DestinationField(
                        Framework.POWER_SIMULATIONS,
                        sienna_type,
                        comp_name,
                        PowerSimulationsCol.LOSS,
                        ps_loss.model_dump(),
                    )
                ],
                derivation="loss absent in source, defaulting to zero LinearCurve",
            )
        )
        return ps_loss.model_dump()

    curve_type = loss.get(SiennaStructField.CURVE_TYPE)
    if curve_type != SiennaCurveType.INPUT_OUTPUT:
        raise ValueError(
            f"Unsupported loss curve_type {curve_type!r} for {sienna_type} {comp_name!r}. "
            f"Only INPUT_OUTPUT curves are currently supported for TwoTerminalGenericHVDCLine."
        )
    fd = loss.get(SiennaStructField.FUNCTION_DATA, {})
    if not isinstance(fd, dict):
        raise ValueError(
            f"Expected dict for loss.function_data on {sienna_type} {comp_name!r}, "
            f"got {type(fd).__name__}"
        )
    function_type = fd.get(SiennaStructField.FUNCTION_TYPE)
    if function_type != SiennaFunctionType.LINEAR:
        raise ValueError(
            f"Unsupported loss function_type {function_type!r} for {sienna_type} {comp_name!r}. "
            f"Only LINEAR function data is currently supported."
        )
    ps_loss = PSInputOutputCurve(
        function_data=PSLinearFunctionData(
            proportional_term=float(fd.get(SiennaStructField.PROPORTIONAL_TERM, 0.0)),
            constant_term=float(fd.get(SiennaStructField.CONSTANT_TERM, 0.0)),
        ),
        input_at_zero=loss.get(SiennaStructField.INPUT_AT_ZERO),
    )
    recorder.append(
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                SourceField(Framework.SIENNA, sienna_type, comp_name, SiennaLinkCol.LOSS, loss)
            ],
            destinations=[
                DestinationField(
                    Framework.POWER_SIMULATIONS,
                    sienna_type,
                    comp_name,
                    PowerSimulationsCol.LOSS,
                    ps_loss.model_dump(),
                )
            ],
            derivation="Sienna InputOutputCurve{LinearFunctionData} -> PS.jl LinearCurve with __metadata__",  # noqa: E501
        )
    )
    return ps_loss.model_dump()


def _map_arc_backed_component(
    state: State, registry: _UuidRegistry, recorder: ScopedRecorder, table_key: str
) -> None:
    source = state.source_topology.get(table_key)
    if source is None:
        return
    by_type: dict[SiennaComponent, list[dict[str, Any]]] = {}

    for row in source.collect().iter_rows(named=True):
        sienna_type = SiennaComponent(row[SiennaLineCol.SIENNA_TYPE])
        comp_id = row[SiennaLineCol.ID]
        comp_name = row[SiennaLineCol.NAME]
        arc_id = row[SiennaLineCol.ARC]
        comp_uuid = registry.get(sienna_type, comp_id)
        arc_uuid = registry.get(SiennaComponent.ARC, arc_id)

        out = {k: v for k, v in row.items() if k not in _ARC_BACKED_TEMP_COLS}
        out[PowerSimulationsCol.UUID] = comp_uuid
        out[PowerSimulationsCol.ARC] = arc_uuid

        if sienna_type in (SiennaComponent.LINE, SiennaComponent.MONITORED_LINE):
            out.setdefault("rating_b", None)
            out.setdefault("rating_c", None)

        if sienna_type == SiennaComponent.TWO_TERMINAL_GENERIC_HVDC_LINE:
            out[PowerSimulationsCol.LOSS] = _convert_hvdc_loss(
                out.get(SiennaLinkCol.LOSS), sienna_type.value, comp_name, recorder
            )

        record_arc_backed_translation(
            recorder, sienna_type.value, comp_name, comp_id, comp_uuid, arc_id, arc_uuid
        )
        by_type.setdefault(sienna_type, []).append(out)

    for sienna_type, rows in by_type.items():
        state.destination_tables[sienna_type] = pl.DataFrame(rows)
