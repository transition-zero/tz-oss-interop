from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel

from interop.core.extensions import ExtensionKind, ExtensionReader
from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import Framework
from interop.plugins.shared.pypsa_time_series import drop_profiles_off_the_window
from interop.plugins.shared.sienna_pypsa_translations.link_bounds import report_link_bounds
from interop.plugins.shared.sienna_pypsa_translations.relay import relay_records
from interop.plugins.shared.sienna_pypsa_translations.reporters import ProfileReporter
from interop.plugins.shared.staged_samples import choose_ensemble_samples
from interop.plugins.steps.sienna_to_pypsa.map_buses import map_buses
from interop.plugins.steps.sienna_to_pypsa.map_conversions import SiennaToPypsaMapConversions
from interop.plugins.steps.sienna_to_pypsa.map_generators import SiennaToPypsaMapGenerators
from interop.plugins.steps.sienna_to_pypsa.map_loads import SiennaToPypsaMapLoads
from interop.plugins.steps.sienna_to_pypsa.map_snapshot_weightings import (
    SnapshotWeightingMapper,
    find_snapshot_window,
)
from interop.plugins.steps.sienna_to_pypsa.map_storage_units import SiennaToPypsaMapStorageUnits
from interop.plugins.steps.sienna_to_pypsa.map_transmission import SiennaToPypsaMapTransmission

_DROP_PROFILES_OFF_THE_WINDOW = "drop_profiles_off_the_window"
_CHOOSE_ENSEMBLE_SAMPLES = "choose_ensemble_samples"
_MAP_SNAPSHOT_WEIGHTINGS = "sienna_to_pypsa_map_snapshot_weightings"
_REPORT_LINK_BOUNDS = "sienna_to_pypsa_report_link_bounds"

# The kinds that travel on whole. PyPSA states none of them, other than the weights of the
# representative periods, which also become the snapshot weightings.
_RELAYED_KINDS: tuple[ExtensionKind, ...] = (
    ExtensionKind.RESERVE,
    ExtensionKind.CONSTRAINT,
    ExtensionKind.NETWORK,
    ExtensionKind.REPRESENTATIVE_PERIOD,
    ExtensionKind.TECHNOLOGY,
)

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
    """

    name: ClassVar[str] = "sienna_to_pypsa_map_components"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder
        self._off_window_recorder = ScopedRecorder(recorder, step=_DROP_PROFILES_OFF_THE_WINDOW)
        self._ensemble_recorder = ScopedRecorder(recorder, step=_CHOOSE_ENSEMBLE_SAMPLES)
        self._weighting_recorder = ScopedRecorder(recorder, step=_MAP_SNAPSHOT_WEIGHTINGS)

    def run(self, state: State, params: BaseModel | None) -> State:
        reader = state.extension_reader(self._recorder)
        map_buses(state, self._recorder, reader)
        for sub_step in self._sub_steps(reader):
            state = sub_step.run(state, params)
        report_link_bounds(state, reader, self._scoped(_REPORT_LINK_BOUNDS))
        self._drop_profiles_off_the_window(state)
        choose_ensemble_samples(state, self._ensemble_recorder, Framework.SIENNA)
        self._map_snapshot_weightings(state, reader)
        self._relay_unread(state, reader)
        return state

    def _map_snapshot_weightings(self, state: State, reader: ExtensionReader) -> None:
        """Weight the snapshots by the representative period that holds each."""
        weightings = SnapshotWeightingMapper(self._weighting_recorder)
        weightings.map_weightings(state, reader, find_snapshot_window(state))

    def _relay_unread(self, state: State, reader: ExtensionReader) -> None:
        """Carry each kind that travels on whole to the destination sidecar."""
        for kind in _RELAYED_KINDS:
            relay_records(state, kind, reader.relay(kind), self._recorder)

    def _sub_steps(self, reader: ExtensionReader) -> tuple[TranslationStep, ...]:
        return (
            SiennaToPypsaMapGenerators(self._scoped(SiennaToPypsaMapGenerators.name), reader),
            SiennaToPypsaMapStorageUnits(self._scoped(SiennaToPypsaMapStorageUnits.name), reader),
            SiennaToPypsaMapLoads(self._scoped(SiennaToPypsaMapLoads.name), reader),
            SiennaToPypsaMapTransmission(self._scoped(SiennaToPypsaMapTransmission.name), reader),
            SiennaToPypsaMapConversions(self._scoped(SiennaToPypsaMapConversions.name), reader),
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
