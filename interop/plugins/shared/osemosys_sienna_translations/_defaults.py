"""A flow or emission parameter whose default is not zero, which the translation does not apply.

Such a default gives every technology the ratio for every fuel or pollutant and every mode, so
the translation reads only the rows that the model states, and records that it did.
"""

from __future__ import annotations

import logging

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import ALL_COMPONENTS
from interop.plugins.shared.osemosys_canonical.constants import FlowParameter
from interop.plugins.shared.osemosys_sienna_constants import (
    OSEMOSYS_TO_SIENNA_PIPELINE,
    SupplyParameter,
)
from interop.plugins.shared.osemosys_sienna_translations._canonical import (
    find_parameter_default,
)
from interop.plugins.shared.osemosys_sienna_translations._events import build_osemosys_field
from interop.ports.outbound.reporting import EventKind, TranslationEvent

log = logging.getLogger(__name__)

_DEFAULT_ATTRIBUTE = "default"
# The parameters that the translation reads only where the model states a row.
_STATED_ROWS_ONLY = (
    FlowParameter.INPUT_ACTIVITY_RATIO,
    FlowParameter.OUTPUT_ACTIVITY_RATIO,
    SupplyParameter.EMISSION_RATE,
)
_NOTE = (
    "a default other than zero would give every technology this value for every fuel or "
    "pollutant and every mode, so the translation reads only the rows that the model states"
)


def report_unread_defaults(state: State, recorder: ScopedRecorder) -> None:
    for parameter in _STATED_ROWS_ONLY:
        default = find_parameter_default(state, parameter)
        if default:
            recorder.append(_build_event(parameter, default))
            log.warning(
                "%s: %s has the default %g, which the translation does not apply. It reads "
                "only the rows that the model states.",
                OSEMOSYS_TO_SIENNA_PIPELINE,
                parameter,
                default,
            )


def _build_event(parameter: str, default: float) -> TranslationEvent:
    return TranslationEvent(
        kind=EventKind.NOT_MAPPED,
        sources=[build_osemosys_field(parameter, ALL_COMPONENTS, _DEFAULT_ATTRIBUTE, default)],
        note=_NOTE,
    )
