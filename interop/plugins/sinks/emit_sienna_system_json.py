from __future__ import annotations

from typing import Any, ClassVar, NamedTuple

import polars as pl
from pydantic import BaseModel, Field

from interop.core.pipeline import Sink, State
from interop.plugins.shared.sienna_constants import (
    SIENNA_ID_COLUMN,
    SIENNA_NAME_COLUMN,
    SiennaACBusCol,
    SiennaArcCol,
    SiennaAttributeAssociationCol,
    SiennaComponent,
    SiennaEnergyReservoirStorageCol,
    SiennaForcedOutageCol,
    SiennaHydroGeneratorCol,
    SiennaLineCol,
    SiennaLoadCol,
    SiennaRenewableGeneratorCol,
    SiennaSchemasSystem,
    SiennaSupplementalAttribute,
    SiennaThermalGeneratorCol,
)
from interop.plugins.sinks._sienna_files import (
    build_system_contents,
    serialise_system_document,
    validate_refs,
)
from interop.ports.outbound.filesystem import FilesystemPort, Location

# A service names no bus, so its row reaches the document as the step wrote it.
_SERVICE_TYPES: tuple[SiennaComponent, ...] = (
    SiennaComponent.ONLINE_RESERVE,
    SiennaComponent.OFFLINE_RESERVE,
)


def _list_rows(table: pl.DataFrame | None) -> list[dict[str, Any]]:
    return [] if table is None else table.to_dicts()


class _BusReferences(NamedTuple):
    """The ids that a bus names its area and its load zone by, keyed by name."""

    area_ids: dict[str, int]
    load_zone_ids: dict[str, int]

    def list_checks(self) -> list[tuple[str, dict[str, int], str]]:
        return [
            (SiennaACBusCol.AREA, self.area_ids, "buses -> areas"),
            (SiennaACBusCol.LOAD_ZONE, self.load_zone_ids, "buses -> load zones"),
        ]

    def build_bus_component(self, row: dict[str, Any]) -> dict[str, Any]:
        """The bus as the document states it, with its area and load zone names as ids."""
        component = dict(row)
        area_name = row[SiennaACBusCol.AREA]
        load_zone_name = row.get(SiennaACBusCol.LOAD_ZONE)
        component[SiennaACBusCol.AREA] = self.area_ids[area_name] if area_name else None
        component[SiennaACBusCol.LOAD_ZONE] = (
            self.load_zone_ids[load_zone_name] if load_zone_name else None
        )
        return component


def build_forced_outage_attributes(
    table: pl.DataFrame | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Each forced outage as a supplemental attribute, and the row that joins it to its unit."""
    if table is None:
        return [], []
    rows = list(table.iter_rows(named=True))
    attributes = [
        {column: row[column] for column in _FORCED_OUTAGE_ATTRIBUTE_COLUMNS} for row in rows
    ]
    associations = [
        {
            SiennaAttributeAssociationCol.COMPONENT_ID: row[SiennaForcedOutageCol.COMPONENT_ID],
            SiennaAttributeAssociationCol.COMPONENT_TYPE: row[SiennaForcedOutageCol.COMPONENT_TYPE],
            SiennaAttributeAssociationCol.ATTRIBUTE_ID: row[SiennaForcedOutageCol.ID],
            SiennaAttributeAssociationCol.ATTRIBUTE_TYPE: (
                SiennaSupplementalAttribute.GEOMETRIC_DISTRIBUTION_FORCED_OUTAGE.value
            ),
        }
        for row in rows
    ]
    return attributes, associations


# The columns a forced outage attribute states; the rest name the unit it describes.
_FORCED_OUTAGE_ATTRIBUTE_COLUMNS = (
    SiennaForcedOutageCol.ID,
    SiennaForcedOutageCol.MEAN_TIME_TO_RECOVERY,
    SiennaForcedOutageCol.OUTAGE_TRANSITION_PROBABILITY,
    SiennaForcedOutageCol.MONITORED_COMPONENTS,
    SiennaForcedOutageCol.IDENTIFIER,
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
        serialised = serialise_system_document(
            build_system_contents(payload, []), None, params.indent
        )
        self._fs.write_bytes(params.output_path, serialised)

    @staticmethod
    def build_payload(state: State) -> dict[str, Any]:
        area_components, area_ids = EmitSiennaSystemJson._build_named_components(
            state.destination_tables.get(SiennaComponent.AREA)
        )
        load_zone_components, load_zone_ids = EmitSiennaSystemJson._build_named_components(
            state.destination_tables.get(SiennaComponent.LOAD_ZONE)
        )
        bus_components, bus_ids = EmitSiennaSystemJson._build_bus_components(
            state.destination_tables.get(SiennaComponent.AC_BUS),
            _BusReferences(area_ids, load_zone_ids),
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
        turbine_components = EmitSiennaSystemJson._build_bus_attached_components(
            state.destination_tables.get(SiennaComponent.HYDRO_TURBINE),
            bus_ids,
            SiennaHydroGeneratorCol.BUS_NAME,
            SiennaHydroGeneratorCol.BUS,
            "hydro turbines -> buses",
        )
        reservoir_components = EmitSiennaSystemJson._build_plain_components(
            state.destination_tables.get(SiennaComponent.HYDRO_RESERVOIR)
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
        components: dict[str, Any] = {}
        if area_components:
            components[SiennaComponent.AREA] = area_components
        if load_zone_components:
            components[SiennaComponent.LOAD_ZONE] = load_zone_components
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
        if turbine_components:
            components[SiennaComponent.HYDRO_TURBINE] = turbine_components
        if reservoir_components:
            components[SiennaComponent.HYDRO_RESERVOIR] = reservoir_components
        if storage_components:
            components[SiennaComponent.ENERGY_RESERVOIR_STORAGE] = storage_components
        if line_components:
            components[SiennaComponent.LINE] = line_components
        if hvdc_components:
            components[SiennaComponent.TWO_TERMINAL_GENERIC_HVDC_LINE] = hvdc_components
        for service_type in _SERVICE_TYPES:
            service_components = _list_rows(state.destination_tables.get(service_type))
            if service_components:
                components[service_type] = service_components

        attributes, associations = build_forced_outage_attributes(
            state.destination_tables.get(
                SiennaSupplementalAttribute.GEOMETRIC_DISTRIBUTION_FORCED_OUTAGE
            )
        )
        return {
            SiennaSchemasSystem.COMPONENTS: components,
            SiennaSchemasSystem.SERVICE_ASSOCIATIONS: _list_rows(
                state.destination_tables.get(SiennaSchemasSystem.SERVICE_ASSOCIATIONS)
            ),
            SiennaSchemasSystem.SUPPLEMENTAL_ATTRIBUTES: attributes,
            SiennaSchemasSystem.SUPPLEMENTAL_ATTRIBUTE_ASSOCIATIONS: associations,
        }

    @staticmethod
    def _build_named_components(
        table: pl.DataFrame | None,
    ) -> tuple[list[dict[str, Any]], dict[str, int]]:
        """Each row as a component, and each component id by name, for a table buses name."""
        if table is None:
            return [], {}
        components = [dict(row) for row in table.iter_rows(named=True)]
        ids = {row[SIENNA_NAME_COLUMN]: row[SIENNA_ID_COLUMN] for row in components}
        return components, ids

    @staticmethod
    def _build_bus_components(
        buses_df: pl.DataFrame | None,
        references: _BusReferences,
    ) -> tuple[list[dict[str, Any]], dict[str, int]]:
        if buses_df is None:
            return [], {}
        for column, ids, context in references.list_checks():
            referenced = buses_df[column].drop_nulls().unique().to_list()
            validate_refs(column, referenced, set(ids), context)
        components: list[dict[str, Any]] = []
        bus_ids: dict[str, int] = {}
        for row in buses_df.iter_rows(named=True):
            bus_ids[row[SiennaACBusCol.NAME]] = row[SiennaACBusCol.ID]
            components.append(references.build_bus_component(row))
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
        validate_refs(name_col, df[name_col].unique().to_list(), set(bus_ids), context)
        components: list[dict[str, Any]] = []
        for row in df.iter_rows(named=True):
            component: dict[str, Any] = {k: v for k, v in row.items() if k != name_col}
            component[ref_col] = bus_ids[row[name_col]]
            components.append(component)
        return components

    @staticmethod
    def _build_plain_components(df: pl.DataFrame | None) -> list[dict[str, Any]]:
        """A component that names no bus, written as its table holds it."""
        return [] if df is None else [dict(row) for row in df.iter_rows(named=True)]

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
        validate_refs(
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
