"""OSeMOSYS fuels that are not electricity -> extensions.json, as a part of the operations step."""

from __future__ import annotations

from typing import ClassVar

from interop.core.extensions import ExtensionKind, GeneratorExtension
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.osemosys_sienna_translations import (
    OperationsMapping,
    OperationsYear,
    add_built_records,
    build_fuel_loads,
    build_fuel_loads_source,
    build_fuel_modes_source,
    build_fuel_records,
    report_unsupplied_fuel_buses,
    set_fuel_values_persisted,
)


class OsemosysToSiennaMapFuels(OperationsMapping):
    """Writes the buses, generators, links and loads of each fuel that is not electricity.

    Sienna holds electricity only, so each record lives in extensions.json, in PyPSA terms, for
    the Sienna to PyPSA hop to build.
    """

    step_name: ClassVar[str] = "osemosys_to_sienna_map_fuels"

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def map_components(self, state: State, operations: OperationsYear) -> None:
        modes = build_fuel_modes_source(state, operations, self._recorder)
        loads = build_fuel_loads(state, build_fuel_loads_source(state, operations, self._recorder))
        built = build_fuel_records(modes, loads.buses, operations.year)
        plants = _list_plants(state)
        report_unsupplied_fuel_buses(
            built.list_suppliers(), loads.loads.records, plants, self._recorder
        )
        add_built_records(state, built.generators, self._recorder)
        add_built_records(state, built.conversions, self._recorder)
        add_built_records(state, built.buses, self._recorder)
        add_built_records(state, loads.loads, self._recorder)
        if loads.series is not None:
            state.destination_extension_series[ExtensionKind.LOAD] = loads.series.lazy()
        if modes.height > 0:
            set_fuel_values_persisted(state, modes)


def _list_plants(state: State) -> list[GeneratorExtension]:
    """The generator records that the generators step wrote and that burn a fuel with a bus."""
    staged = state.destination_extensions.get(ExtensionKind.GENERATOR, [])
    return [
        record for record in staged if isinstance(record, GeneratorExtension) and record.fuel_buses
    ]
