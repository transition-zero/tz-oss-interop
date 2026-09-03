from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel

from interop.core.extensions import ExtensionReader
from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import Framework
from interop.plugins.shared.pypsa_time_series import drop_profiles_off_the_window
from interop.plugins.shared.sienna_pypsa_translations.reporters import ProfileReporter
from interop.plugins.steps.sienna_to_pypsa.map_buses import map_buses
from interop.plugins.steps.sienna_to_pypsa.map_generators import SiennaToPypsaMapGenerators
from interop.plugins.steps.sienna_to_pypsa.map_loads import SiennaToPypsaMapLoads
from interop.plugins.steps.sienna_to_pypsa.map_storage_units import SiennaToPypsaMapStorageUnits
from interop.plugins.steps.sienna_to_pypsa.map_transmission import SiennaToPypsaMapTransmission

_DROP_PROFILES_OFF_THE_WINDOW = "drop_profiles_off_the_window"

_WINDOW_ADVICE = (
    "Every TimeSeriesAssociation in one system has to cover the same snapshots, so check "
    "the HDF5 companion for the ones that do not."
)


class SiennaToPypsaMapComponents(TranslationStep):
    """Single pipeline node that maps buses and runs the generator/storage sub-steps.

    Bus decisions are recorded under this composite's own recorder so they attribute to
    ``sienna_to_pypsa_map_components``. Each sub-step is wrapped in its own ScopedRecorder
    so its decisions stay attributed to its own name even though they run under this
    composite. The inner scope wins because ScopedRecorder keeps an event's existing step
    over its own.

    Every sub-step shares one ``ExtensionReader``, so once they have all run this step can
    report the staged records no mapping consumed. Such a record is dropped rather than
    relayed onward: no record outlives the mapping that knew what it meant.
    """

    name: ClassVar[str] = "sienna_to_pypsa_map_components"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder
        self._off_window_recorder = ScopedRecorder(recorder, step=_DROP_PROFILES_OFF_THE_WINDOW)

    def run(self, state: State, params: BaseModel | None) -> State:
        reader = ExtensionReader(state.source_extensions, Framework.SIENNA)
        map_buses(state, self._recorder, reader)
        for sub_step in self._sub_steps(reader):
            state = sub_step.run(state, params)
        self._drop_profiles_off_the_window(state)
        reader.report_unconsumed(self._recorder)
        return state

    def _sub_steps(self, reader: ExtensionReader) -> tuple[TranslationStep, ...]:
        return (
            SiennaToPypsaMapGenerators(self._scoped(SiennaToPypsaMapGenerators.name), reader),
            SiennaToPypsaMapStorageUnits(self._scoped(SiennaToPypsaMapStorageUnits.name), reader),
            SiennaToPypsaMapLoads(self._scoped(SiennaToPypsaMapLoads.name), reader),
            SiennaToPypsaMapTransmission(self._scoped(SiennaToPypsaMapTransmission.name), reader),
        )

    def _scoped(self, step: str) -> ScopedRecorder:
        return ScopedRecorder(self._recorder, step=step)

    def _drop_profiles_off_the_window(self, state: State) -> None:
        """Leave a series that does not fit the snapshot window off the network, and say so."""
        dropped = drop_profiles_off_the_window(state, _WINDOW_ADVICE)
        reporter = ProfileReporter(self._off_window_recorder)
        for profile in dropped.profiles:
            reporter.record_dropped(
                profile.owner_type, profile.component, profile.series, dropped.note(profile)
            )
