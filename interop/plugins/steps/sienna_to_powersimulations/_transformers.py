"""A Sienna TwoWindingTransformer, which the PowerSimulations system does not hold.

The step writes a Line and a TwoTerminalGenericHVDCLine, and no transformer, so a branch
that steps voltage reaches no solve. Each one leaves the translation with an event and a
warning, rather than disappearing from the system in silence.
"""

from __future__ import annotations

import logging

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import Framework
from interop.plugins.shared.sienna_constants import (
    SIENNA_NAME_COLUMN,
    SiennaComponent,
    SiennaTable,
)
from interop.plugins.shared.warning_text import name_a_few
from interop.ports.outbound.reporting import EventKind, SourceField, TranslationEvent

log = logging.getLogger(__name__)

_TRANSFORMER_NOTE = (
    "the PowerSimulations system holds no transformer, so the branch and the voltage step "
    "it states stay out of the solve"
)
_TRANSFORMER_WARNING = (
    "power-simulations: %d TwoWindingTransformer(s) have no counterpart in the "
    "PowerSimulations system, so each is left out: %s"
)


def report_unmapped_transformers(state: State, recorder: ScopedRecorder) -> None:
    """Record each TwoWindingTransformer the system leaves out, and warn once naming a few."""
    transformers = state.source_topology.get(SiennaTable.TRANSFORMERS)
    if transformers is None:
        return
    names: list[str] = transformers.select(SIENNA_NAME_COLUMN).collect().to_series().to_list()
    if not names:
        return
    for name in names:
        recorder.append(
            TranslationEvent(
                kind=EventKind.COMPONENT_SKIPPED,
                sources=[
                    SourceField(
                        Framework.SIENNA,
                        SiennaComponent.TWO_WINDING_TRANSFORMER.value,
                        name,
                        None,
                        None,
                    )
                ],
                note=_TRANSFORMER_NOTE,
            )
        )
    log.warning(_TRANSFORMER_WARNING, len(names), name_a_few(sorted(names)))
