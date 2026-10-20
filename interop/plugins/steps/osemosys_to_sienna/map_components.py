"""The one pipeline node that translates the canonical OSeMOSYS stage into a Sienna system."""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, Field

from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.osemosys_sienna_translations import (
    OperationsMapping,
    OperationsYear,
    add_built_records,
    build_calendar,
    build_period_records,
    parse_units,
    read_operations_mode,
    report_calendar,
    report_unread_defaults,
    require_model_year,
    set_days_persisted,
    set_operations_year,
)
from interop.plugins.shared.osemosys_sienna_user_mappings import OsemosysSiennaCarrierMappings
from interop.plugins.steps.osemosys_to_sienna.map_buses import OsemosysToSiennaMapBuses
from interop.plugins.steps.osemosys_to_sienna.map_conversions import (
    OsemosysToSiennaMapConversions,
)
from interop.plugins.steps.osemosys_to_sienna.map_generators import (
    OsemosysToSiennaMapGenerators,
)
from interop.plugins.steps.osemosys_to_sienna.map_loads import OsemosysToSiennaMapLoads
from interop.plugins.steps.osemosys_to_sienna.map_policies import OsemosysToSiennaMapPolicies
from interop.plugins.steps.osemosys_to_sienna.map_storage import OsemosysToSiennaMapStorage
from interop.plugins.steps.osemosys_to_sienna.map_transport import OsemosysToSiennaMapTransport
from interop.plugins.steps.osemosys_to_sienna.report_left_out import OsemosysToSiennaReportLeftOut

# The calendar and the unread defaults concern the whole model, so each names a step of its own.
_BUILD_CALENDAR = "osemosys_to_sienna_build_calendar"
_REPORT_DEFAULTS = "osemosys_to_sienna_report_defaults"


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
        self._defaults_recorder = ScopedRecorder(recorder, step=_REPORT_DEFAULTS)
        self._mappings: tuple[OperationsMapping, ...] = (
            OsemosysToSiennaMapBuses(_build_group_recorder(recorder, OsemosysToSiennaMapBuses)),
            OsemosysToSiennaMapLoads(_build_group_recorder(recorder, OsemosysToSiennaMapLoads)),
            OsemosysToSiennaMapGenerators(
                _build_group_recorder(recorder, OsemosysToSiennaMapGenerators),
                osemosys_sienna_mappings,
            ),
            OsemosysToSiennaMapStorage(
                _build_group_recorder(recorder, OsemosysToSiennaMapStorage),
                osemosys_sienna_mappings,
            ),
            OsemosysToSiennaMapTransport(
                _build_group_recorder(recorder, OsemosysToSiennaMapTransport)
            ),
            OsemosysToSiennaMapConversions(
                _build_group_recorder(recorder, OsemosysToSiennaMapConversions)
            ),
            OsemosysToSiennaMapPolicies(
                _build_group_recorder(recorder, OsemosysToSiennaMapPolicies)
            ),
            OsemosysToSiennaReportLeftOut(
                _build_group_recorder(recorder, OsemosysToSiennaReportLeftOut)
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
        report_unread_defaults(state, self._defaults_recorder)
        for mapping in self._mappings:
            mapping.map_components(state, operations)
        self._map_periods(state, operations)
        return state

    def _map_periods(self, state: State, operations: OperationsYear) -> None:
        periods = build_period_records(state, operations.year, operations.calendar)
        add_built_records(state, periods, self._calendar_recorder)
        set_days_persisted(state, periods.records)

    def _build_operations_year(
        self, state: State, params: OsemosysToSiennaMapComponentsParams
    ) -> OperationsYear:
        year = require_model_year(state, params.year)
        units = parse_units(state)
        calendar = build_calendar(state, year)
        report_calendar(calendar, self._calendar_recorder)
        return OperationsYear(year, units, calendar, read_operations_mode(state))


def _build_group_recorder(
    recorder: ScopedRecorder, group: type[OperationsMapping]
) -> ScopedRecorder:
    """A recorder that stamps each event that it takes with the group that raised it."""
    return ScopedRecorder(recorder, step=group.step_name)
