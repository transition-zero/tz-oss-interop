from __future__ import annotations

import json
from typing import Any, ClassVar

import polars as pl
from pydantic import BaseModel, Field

from interop.core.pipeline import Sink, State
from interop.plugins.shared.sienna_constants import (
    SiennaACBusCol,
    SiennaArcCol,
    SiennaAreaCol,
    SiennaComponent,
    SiennaEnergyReservoirStorageCol,
    SiennaHydroGeneratorCol,
    SiennaLineCol,
    SiennaLoadCol,
    SiennaRenewableGeneratorCol,
    SiennaThermalGeneratorCol,
    SiennaTimeSeriesAssociationCol,
)
from interop.ports.outbound.filesystem import FilesystemPort, Location

# Internal-only columns in TIME_SERIES_ASSOCIATION that are not part of the JSON schema.
_TS_ASSOC_INTERNAL_COLS = frozenset(
    [
        SiennaTimeSeriesAssociationCol.COMPONENT_NAME,
        SiennaTimeSeriesAssociationCol.SOURCE_TABLE,
        SiennaTimeSeriesAssociationCol.SOURCE_ATTRIBUTE,
        SiennaTimeSeriesAssociationCol.SCALING_FACTOR,
    ]
)


class EmitSiennaSystemJsonParams(BaseModel):
    output_path: Location = Field(description="the SiennaSchemas system.json to write")
    indent: int = Field(default=2, description="JSON indent width")


class EmitSiennaSystemJson(Sink):
    name: ClassVar[str] = "emit_sienna_system_json"
    params_schema: ClassVar[type[BaseModel] | None] = EmitSiennaSystemJsonParams

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def write(self, state: State, params: BaseModel | None) -> None:
        if not isinstance(params, EmitSiennaSystemJsonParams):
            raise TypeError(
                f"{type(self).__name__} requires {EmitSiennaSystemJsonParams.__name__}, "
                f"got {type(params).__name__}"
            )
        payload = self.build_payload(state)
        serialised = json.dumps(payload, indent=params.indent, default=str).encode("utf-8")
        self._fs.write_bytes(params.output_path, serialised)

    @staticmethod
    def build_payload(state: State) -> dict[str, Any]:
        area_components, area_ids = EmitSiennaSystemJson._build_area_components(
            state.destination_tables.get(SiennaComponent.AREA)
        )
        bus_components, bus_ids = EmitSiennaSystemJson._build_bus_components(
            state.destination_tables.get(SiennaComponent.AC_BUS), area_ids
        )
        load_components = EmitSiennaSystemJson._build_bus_attached_components(
            state.destination_tables.get(SiennaComponent.POWER_LOAD),
            bus_ids,
            SiennaLoadCol.BUS_NAME,
            SiennaLoadCol.BUS,
            "loads -> buses",
        )
        interruptible_load_components = EmitSiennaSystemJson._build_bus_attached_components(
            state.destination_tables.get(SiennaComponent.INTERRUPTIBLE_POWER_LOAD),
            bus_ids,
            SiennaLoadCol.BUS_NAME,
            SiennaLoadCol.BUS,
            "interruptible loads -> buses",
        )
        gen_components = EmitSiennaSystemJson._build_bus_attached_components(
            state.destination_tables.get(SiennaComponent.THERMAL_STANDARD),
            bus_ids,
            SiennaThermalGeneratorCol.BUS_NAME,
            SiennaThermalGeneratorCol.BUS,
            "generators -> buses",
        )
        renewable_components = EmitSiennaSystemJson._build_bus_attached_components(
            state.destination_tables.get(SiennaComponent.RENEWABLE_DISPATCH),
            bus_ids,
            SiennaRenewableGeneratorCol.BUS_NAME,
            SiennaRenewableGeneratorCol.BUS,
            "renewables -> buses",
        )
        renewable_nd_components = EmitSiennaSystemJson._build_bus_attached_components(
            state.destination_tables.get(SiennaComponent.RENEWABLE_NON_DISPATCH),
            bus_ids,
            SiennaRenewableGeneratorCol.BUS_NAME,
            SiennaRenewableGeneratorCol.BUS,
            "renewable non-dispatch -> buses",
        )
        hydro_components = EmitSiennaSystemJson._build_bus_attached_components(
            state.destination_tables.get(SiennaComponent.HYDRO_DISPATCH),
            bus_ids,
            SiennaHydroGeneratorCol.BUS_NAME,
            SiennaHydroGeneratorCol.BUS,
            "hydro -> buses",
        )
        storage_components = EmitSiennaSystemJson._build_bus_attached_components(
            state.destination_tables.get(SiennaComponent.ENERGY_RESERVOIR_STORAGE),
            bus_ids,
            SiennaEnergyReservoirStorageCol.BUS_NAME,
            SiennaEnergyReservoirStorageCol.BUS,
            "storage -> buses",
        )
        arc_components, arc_ids = EmitSiennaSystemJson._build_arc_components(
            state.destination_tables.get(SiennaComponent.ARC)
        )
        line_components = EmitSiennaSystemJson._build_branch_components(
            state.destination_tables.get(SiennaComponent.LINE), bus_ids, arc_ids
        )
        hvdc_components = EmitSiennaSystemJson._build_branch_components(
            state.destination_tables.get(SiennaComponent.TWO_TERMINAL_GENERIC_HVDC_LINE),
            bus_ids,
            arc_ids,
        )
        ts_associations = EmitSiennaSystemJson._build_time_series_associations(
            state.destination_tables.get(SiennaComponent.TIME_SERIES_ASSOCIATION)
        )

        components: dict[str, Any] = {}
        if area_components:
            components[SiennaComponent.AREA] = area_components
        if bus_components:
            components[SiennaComponent.AC_BUS] = bus_components
        if arc_components:
            components[SiennaComponent.ARC] = arc_components
        if load_components:
            components[SiennaComponent.POWER_LOAD] = load_components
        if interruptible_load_components:
            components[SiennaComponent.INTERRUPTIBLE_POWER_LOAD] = interruptible_load_components
        if gen_components:
            components[SiennaComponent.THERMAL_STANDARD] = gen_components
        if renewable_components:
            components[SiennaComponent.RENEWABLE_DISPATCH] = renewable_components
        if renewable_nd_components:
            components[SiennaComponent.RENEWABLE_NON_DISPATCH] = renewable_nd_components
        if hydro_components:
            components[SiennaComponent.HYDRO_DISPATCH] = hydro_components
        if storage_components:
            components[SiennaComponent.ENERGY_RESERVOIR_STORAGE] = storage_components
        if line_components:
            components[SiennaComponent.LINE] = line_components
        if hvdc_components:
            components[SiennaComponent.TWO_TERMINAL_GENERIC_HVDC_LINE] = hvdc_components

        return {
            "components": components,
            "time_series_associations": ts_associations,
        }

    @staticmethod
    def _build_area_components(
        areas_df: pl.DataFrame | None,
    ) -> tuple[list[dict[str, Any]], dict[str, int]]:
        if areas_df is None:
            return [], {}
        components: list[dict[str, Any]] = []
        area_ids: dict[str, int] = {}
        for row in areas_df.iter_rows(named=True):
            name: str = row[SiennaAreaCol.NAME]
            area_id: int = row[SiennaAreaCol.ID]
            area_ids[name] = area_id
            components.append(
                {
                    "id": area_id,
                    "name": name,
                    "peak_active_power": 0.0,
                    "peak_reactive_power": 0.0,
                    "load_response": 0.0,
                }
            )
        return components, area_ids

    @staticmethod
    def _build_bus_components(
        buses_df: pl.DataFrame | None,
        area_ids: dict[str, int],
    ) -> tuple[list[dict[str, Any]], dict[str, int]]:
        if buses_df is None:
            return [], {}
        referenced_areas = buses_df[SiennaACBusCol.AREA].drop_nulls().unique().to_list()
        _validate_refs(SiennaACBusCol.AREA, referenced_areas, set(area_ids), "buses -> areas")
        components: list[dict[str, Any]] = []
        bus_ids: dict[str, int] = {}
        for row in buses_df.iter_rows(named=True):
            name: str = row[SiennaACBusCol.NAME]
            bus_ids[name] = row[SiennaACBusCol.ID]
            area_name: str | None = row[SiennaACBusCol.AREA]
            component: dict[str, Any] = {k: v for k, v in row.items() if k != SiennaACBusCol.AREA}
            component["area"] = area_ids[area_name] if area_name else None
            components.append(component)
        return components, bus_ids

    @staticmethod
    def _build_bus_attached_components(
        df: pl.DataFrame | None,
        bus_ids: dict[str, int],
        name_col: str,
        ref_col: str,
        context: str,
    ) -> list[dict[str, Any]]:
        """Resolve a static injection's bus name to an integer id, dropping the name column.

        Shared by PowerLoad and ThermalStandard, which both carry the bus endpoint as a
        ``bus_name`` string resolved to a ``bus`` id reference.
        """
        if df is None:
            return []
        _validate_refs(name_col, df[name_col].unique().to_list(), set(bus_ids), context)
        components: list[dict[str, Any]] = []
        for row in df.iter_rows(named=True):
            component: dict[str, Any] = {k: v for k, v in row.items() if k != name_col}
            component[ref_col] = bus_ids[row[name_col]]
            components.append(component)
        return components

    @staticmethod
    def _build_arc_components(
        arcs_df: pl.DataFrame | None,
    ) -> tuple[list[dict[str, Any]], dict[tuple[int, int], int]]:
        if arcs_df is None:
            return [], {}
        components: list[dict[str, Any]] = []
        arc_ids: dict[tuple[int, int], int] = {}
        for row in arcs_df.iter_rows(named=True):
            endpoints = (row[SiennaArcCol.FROM], row[SiennaArcCol.TO])
            arc_ids[endpoints] = row[SiennaArcCol.ID]
            components.append(
                {
                    SiennaArcCol.ID: row[SiennaArcCol.ID],
                    SiennaArcCol.FROM: row[SiennaArcCol.FROM],
                    SiennaArcCol.TO: row[SiennaArcCol.TO],
                }
            )
        return components, arc_ids

    @staticmethod
    def _build_branch_components(
        branch_df: pl.DataFrame | None,
        bus_ids: dict[str, int],
        arc_ids: dict[tuple[int, int], int],
    ) -> list[dict[str, Any]]:
        """Resolve a branch table's bus0/bus1 names to the shared Arc and drop the names.

        Shared by Line and TwoTerminalGenericHVDCLine, which carry the same bus0/bus1/arc
        endpoint columns.
        """
        if branch_df is None:
            return []
        referenced_buses = (
            pl.concat([branch_df[SiennaLineCol.BUS0], branch_df[SiennaLineCol.BUS1]])
            .unique()
            .to_list()
        )
        _validate_refs(
            f"{SiennaLineCol.BUS0}/{SiennaLineCol.BUS1}",
            referenced_buses,
            set(bus_ids),
            "branches -> buses",
        )
        components: list[dict[str, Any]] = []
        for row in branch_df.iter_rows(named=True):
            endpoints = (bus_ids[row[SiennaLineCol.BUS0]], bus_ids[row[SiennaLineCol.BUS1]])
            if endpoints not in arc_ids:
                raise ValueError(f"branches -> arcs: no Arc for bus pair {endpoints}")
            component: dict[str, Any] = {
                k: v for k, v in row.items() if k not in (SiennaLineCol.BUS0, SiennaLineCol.BUS1)
            }
            component[SiennaLineCol.ARC] = arc_ids[endpoints]
            components.append(component)
        return components

    @staticmethod
    def _build_time_series_associations(
        ts_df: pl.DataFrame | None,
    ) -> list[dict[str, Any]]:
        if ts_df is None:
            return []
        emit_cols = [c for c in ts_df.columns if c not in _TS_ASSOC_INTERNAL_COLS]
        return list(
            ts_df.select(emit_cols)
            .with_row_index(name=SiennaTimeSeriesAssociationCol.ID, offset=1)
            .iter_rows(named=True)
        )


def _validate_refs(
    ref_col: str,
    needed: list[str],
    available: set[str],
    context: str,
) -> None:
    missing = set(needed) - available
    if missing:
        raise ValueError(
            f"{context}: {len(missing)} reference(s) in {ref_col!r} "
            f"not found in parent table: {sorted(missing)}"
        )
