from __future__ import annotations

import logging
from typing import ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import PipelineSteps, State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.plexos_constants import (
    PlexosClass,
    PlexosMembershipCol,
    PlexosResolvedTable,
)
from interop.plugins.shared.plexos_pypsa_translations import choose_ensemble_samples
from interop.plugins.shared.plexos_pypsa_translations.decisions import (
    SourceReporter,
    SourceValue,
)
from interop.plugins.shared.pypsa_time_series import drop_profiles_off_the_window
from interop.plugins.steps.plexos_to_pypsa.map_buses import PlexosToPypsaMapBuses
from interop.plugins.steps.plexos_to_pypsa.map_constraints import PlexosToPypsaMapConstraints
from interop.plugins.steps.plexos_to_pypsa.map_generators import PlexosToPypsaMapGenerators
from interop.plugins.steps.plexos_to_pypsa.map_loads import PlexosToPypsaMapLoads
from interop.plugins.steps.plexos_to_pypsa.map_reserves import PlexosToPypsaMapReserves
from interop.plugins.steps.plexos_to_pypsa.map_storage_units import PlexosToPypsaMapStorageUnits
from interop.plugins.steps.plexos_to_pypsa.map_transmission import PlexosToPypsaMapTransmission

log = logging.getLogger(__name__)

# Stands in for a file-backed property's value, which PLEXOS states as a path.
_PROFILE = "profile"

# The two whole-network concerns that run after the sub-steps, named so their decisions
# attribute to them rather than to this composite.
_CHOOSE_ENSEMBLE_SAMPLES = "choose_ensemble_samples"
_DROP_PROFILES_OFF_THE_WINDOW = "drop_profiles_off_the_window"


class PlexosToPypsaMapComponents(TranslationStep):
    """Single pipeline node that runs the per-component PLEXOS -> PyPSA sub-steps.

    Each component has a sibling module holding its own ``TranslationStep``, constructed
    here inside its own ``ScopedRecorder`` so its decisions attribute to that sub-step
    rather than to this composite.

    The two concerns that run after them read the whole network at once, so neither belongs
    to a component. Each still takes its own ``ScopedRecorder`` under its own name.

    Sub-steps run in dependency order: buses first, then everything that references a bus.
    Reserves are the one resource with no native PyPSA home, so they are carried to the
    extensions sidecar rather than enforced. Storage units reference a bus by name, which
    the sink auto-creates, so they need no buses table to be mapped. Constraints go last
    because they only report; nothing downstream reads what they leave behind.
    """

    name: ClassVar[str] = "plexos_to_pypsa_map_components"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder, pipeline_steps: PipelineSteps) -> None:
        self._sub_steps: tuple[TranslationStep, ...] = (
            PlexosToPypsaMapBuses(_scoped(recorder, PlexosToPypsaMapBuses.name)),
            PlexosToPypsaMapLoads(_scoped(recorder, PlexosToPypsaMapLoads.name), pipeline_steps),
            PlexosToPypsaMapGenerators(_scoped(recorder, PlexosToPypsaMapGenerators.name)),
            PlexosToPypsaMapTransmission(_scoped(recorder, PlexosToPypsaMapTransmission.name)),
            PlexosToPypsaMapReserves(_scoped(recorder, PlexosToPypsaMapReserves.name)),
            PlexosToPypsaMapStorageUnits(_scoped(recorder, PlexosToPypsaMapStorageUnits.name)),
            PlexosToPypsaMapConstraints(_scoped(recorder, PlexosToPypsaMapConstraints.name)),
        )
        self._ensemble_recorder = _scoped(recorder, _CHOOSE_ENSEMBLE_SAMPLES)
        self._off_window_recorder = _scoped(recorder, _DROP_PROFILES_OFF_THE_WINDOW)

    def run(self, state: State, params: BaseModel | None) -> State:
        for sub_step in self._sub_steps:
            state = sub_step.run(state, params)
        choose_ensemble_samples(state, self._ensemble_recorder)
        _drop_profiles_off_the_window(state, self._off_window_recorder)
        return state


def _scoped(recorder: ScopedRecorder, step_name: str) -> ScopedRecorder:
    """A recorder that stamps every event it takes with the sub-step that raised it."""
    return ScopedRecorder(recorder, step=step_name)


# PLEXOS keeps the chronology on a Horizon object the Model relates to; the class name is
# the source's own vocabulary and is not among the classes a mapping reads.
_HORIZON_CLASS = "Horizon"

_MODELS_NAMED = 6


def _drop_profiles_off_the_window(state: State, recorder: ScopedRecorder) -> None:
    """Leave a profile that does not fit the snapshot window off the network, and say so.

    Reconciling the profiles needs the selected Model's Horizon, so the advice the shared
    drop closes its warning with lists the Models that declare one.
    """
    dropped = drop_profiles_off_the_window(state, _horizon_advice(state))
    reporter = SourceReporter(recorder)
    for profile in dropped.profiles:
        reporter.record_dropped(
            SourceValue(profile.owner_type, profile.component, profile.series, _PROFILE),
            dropped.note(profile),
        )


def _horizon_advice(state: State) -> str:
    return (
        "Set the source's 'model' parameter so its Horizon settles one window for every "
        f"profile: {_describe_models(state)}"
    )


def _describe_models(state: State) -> str:
    """The Models whose Horizon could settle the window, or why none can.

    A Model without a Horizon states no window, so naming it would not help; listing it
    would send the caller round the loop again.
    """
    names = _models_with_a_horizon(state)
    if not names:
        return "no Model in the file declares a Horizon, so the profiles have to agree on their own"
    shown = ", ".join(repr(name) for name in names[:_MODELS_NAMED])
    remaining = len(names) - _MODELS_NAMED
    return shown if remaining <= 0 else f"{shown}, and {remaining} more"


def _models_with_a_horizon(state: State) -> list[str]:
    memberships = state.source_topology.get(PlexosResolvedTable.MEMBERSHIPS)
    if memberships is None:
        return []
    related = memberships.filter(
        (pl.col(PlexosMembershipCol.PARENT_CLASS) == PlexosClass.MODEL)
        & (pl.col(PlexosMembershipCol.CHILD_CLASS) == _HORIZON_CLASS)
    ).select(PlexosMembershipCol.PARENT_OBJECT)
    return sorted(set(related.collect()[PlexosMembershipCol.PARENT_OBJECT].to_list()))
