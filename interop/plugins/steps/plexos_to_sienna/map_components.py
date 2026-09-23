"""The one pipeline node that translates a staged PLEXOS model into Sienna tables."""

from __future__ import annotations

import logging
from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.plexos_sienna_translations import CarrierTargets
from interop.plugins.shared.plexos_sienna_user_mappings import PlexosSiennaCarrierMappings
from interop.plugins.steps.plexos_to_sienna.map_buses import PlexosToSiennaMapBuses
from interop.plugins.steps.plexos_to_sienna.map_generators import (
    PlexosToSiennaMapGenerators,
)
from interop.plugins.steps.plexos_to_sienna.map_loads import PlexosToSiennaMapLoads
from interop.plugins.steps.plexos_to_sienna.map_transmission import (
    PlexosToSiennaMapTransmission,
)

log = logging.getLogger(__name__)


class PlexosToSiennaMapComponents(TranslationStep):
    """Single pipeline node that runs the per-component PLEXOS -> Sienna sub-steps.

    Each component group has a sibling module holding its own ``TranslationStep``, built
    here inside its own ``ScopedRecorder`` so its decisions attribute to that sub-step
    rather than to this composite.

    Sub-steps run in dependency order: buses first, then everything that names a bus.

    The step reads the user's PLEXOS mappings file itself. Declaring the schema on
    ``__init__`` is what makes ``UserMappingsLoader`` ask for the file in PLEXOS words.
    """

    name: ClassVar[str] = "plexos_to_sienna_map_components"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(
        self,
        recorder: ScopedRecorder,
        plexos_sienna_mappings: PlexosSiennaCarrierMappings,
    ) -> None:
        targets = CarrierTargets(plexos_sienna_mappings)
        self._sub_steps: tuple[TranslationStep, ...] = (
            PlexosToSiennaMapBuses(_scoped(recorder, PlexosToSiennaMapBuses.name)),
            PlexosToSiennaMapLoads(_scoped(recorder, PlexosToSiennaMapLoads.name)),
            PlexosToSiennaMapGenerators(
                _scoped(recorder, PlexosToSiennaMapGenerators.name), targets
            ),
            PlexosToSiennaMapTransmission(_scoped(recorder, PlexosToSiennaMapTransmission.name)),
        )

    def run(self, state: State, params: BaseModel | None) -> State:
        for sub_step in self._sub_steps:
            state = sub_step.run(state, params)
        return state


def _scoped(recorder: ScopedRecorder, step_name: str) -> ScopedRecorder:
    """A recorder that stamps every event it takes with the sub-step that raised it."""
    return ScopedRecorder(recorder, step=step_name)
