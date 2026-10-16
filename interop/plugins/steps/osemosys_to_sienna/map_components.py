"""The one pipeline node that translates the canonical OSeMOSYS stage into a Sienna system."""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, Field

from interop.core.extensions import ExtensionKind, append_extensions
from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.osemosys_sienna_translations import (
    OperationsMapping,
    OperationsYear,
    build_calendar,
    build_representative_periods,
    parse_units,
    read_operations_mode,
    report_calendar,
    require_model_year,
    set_operations_year,
)
from interop.plugins.shared.osemosys_sienna_user_mappings import OsemosysSiennaCarrierMappings
from interop.plugins.steps.osemosys_to_sienna.map_buses import OsemosysToSiennaMapBuses
from interop.plugins.steps.osemosys_to_sienna.map_generators import (
    OsemosysToSiennaMapGenerators,
)
from interop.plugins.steps.osemosys_to_sienna.map_loads import OsemosysToSiennaMapLoads
from interop.plugins.steps.osemosys_to_sienna.map_storage import OsemosysToSiennaMapStorage
from interop.plugins.steps.osemosys_to_sienna.map_transport import OsemosysToSiennaMapTransport
from interop.plugins.steps.osemosys_to_sienna.report_left_out import OsemosysToSiennaReportLeftOut

# The calendar is a concern of the whole year, so its decisions name a step of their own.
_BUILD_CALENDAR = "osemosys_to_sienna_build_calendar"


class OsemosysToSiennaMapComponentsParams(BaseModel):
    year: int | Literal["earliest"] = Field(
        description="the model year of the fleet and the demand, or earliest"
    )


class OsemosysToSiennaMapComponents(TranslationStep):
    """Runs the component groups of one operations year, each inside its own ScopedRecorder.

    The groups run in dependency order: buses first, then each group that names a bus.
    Declaring the carrier mappings on ``__init__`` makes ``UserMappingsLoader`` ask for the
    file.
    """

    name: ClassVar[str] = "osemosys_to_sienna_map_components"
    params_schema: ClassVar[type[BaseModel] | None] = OsemosysToSiennaMapComponentsParams

    def __init__(
        self,
        recorder: ScopedRecorder,
        osemosys_sienna_mappings: OsemosysSiennaCarrierMappings,
    ) -> None:
        self._calendar_recorder = ScopedRecorder(recorder, step=_BUILD_CALENDAR)
        self._mappings: tuple[OperationsMapping, ...] = (
            OsemosysToSiennaMapBuses(_scoped(recorder, OsemosysToSiennaMapBuses.step_name)),
            OsemosysToSiennaMapLoads(_scoped(recorder, OsemosysToSiennaMapLoads.step_name)),
            OsemosysToSiennaMapGenerators(
                _scoped(recorder, OsemosysToSiennaMapGenerators.step_name),
                osemosys_sienna_mappings,
            ),
            OsemosysToSiennaMapStorage(
                _scoped(recorder, OsemosysToSiennaMapStorage.step_name),
                osemosys_sienna_mappings,
            ),
            OsemosysToSiennaMapTransport(_scoped(recorder, OsemosysToSiennaMapTransport.step_name)),
            OsemosysToSiennaReportLeftOut(
                _scoped(recorder, OsemosysToSiennaReportLeftOut.step_name)
            ),
        )

    def run(self, state: State, params: BaseModel | None) -> State:
        if not isinstance(params, OsemosysToSiennaMapComponentsParams):
            raise TypeError(
                f"{type(self).__name__} requires {OsemosysToSiennaMapComponentsParams.__name__}, "
                f"got {type(params).__name__}"
            )
        operations = self._build_operations_year(state, params)
        set_operations_year(state, operations.year)
        for mapping in self._mappings:
            mapping.map_components(state, operations)
        append_extensions(
            state.destination_extensions,
            ExtensionKind.REPRESENTATIVE_PERIOD,
            build_representative_periods(operations.calendar),
        )
        return state

    def _build_operations_year(
        self, state: State, params: OsemosysToSiennaMapComponentsParams
    ) -> OperationsYear:
        year = require_model_year(state, params.year)
        units = parse_units(state)
        calendar = build_calendar(state, year)
        report_calendar(calendar, self._calendar_recorder)
        return OperationsYear(year, units, calendar, read_operations_mode(state))


def _scoped(recorder: ScopedRecorder, step_name: str) -> ScopedRecorder:
    """A recorder that stamps each event that it takes with the group that raised it."""
    return ScopedRecorder(recorder, step=step_name)
