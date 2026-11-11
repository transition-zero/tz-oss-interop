"""PLEXOS forced outages -> Sienna forced outage attributes, as a sub-step of the composite step."""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.plexos_sienna_translations import map_forced_outages
from interop.plugins.shared.sienna_constants import (
    SYSTEM_ATTRIBUTE_ASSOCIATIONS_TABLE,
    SYSTEM_ATTRIBUTES_TABLE,
)


class PlexosToSiennaMapOutages(TranslationStep):
    """Writes a GeometricDistributionForcedOutage for each translated unit that states one.

    It writes the attributes, and the rows that join each one to its unit.
    """

    name: ClassVar[str] = "plexos_to_sienna_map_outages"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def run(self, state: State, params: BaseModel | None) -> State:
        outages = map_forced_outages(state, self._recorder)
        if outages.attributes.height:
            state.destination_tables[SYSTEM_ATTRIBUTES_TABLE] = outages.attributes
            state.destination_tables[SYSTEM_ATTRIBUTE_ASSOCIATIONS_TABLE] = outages.associations
        return state
