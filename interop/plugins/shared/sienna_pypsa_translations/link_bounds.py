"""The annual energy bounds of a sidecar record that becomes a PyPSA Link.

A PyPSA Link has no `e_sum_min` or `e_sum_max`, so each bound travels on in the sidecar and binds
nothing. Each one gets a NOT_MAPPED event, and one warning names three.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence

from interop.core.extensions import ActivityExtension
from interop.plugins.shared.warning_text import name_a_few

log = logging.getLogger(__name__)

_BOUND_FIELDS = ("e_sum_min", "e_sum_max")
_BOUND_WARNING = (
    "%d annual energy bound(s) of a link stay in extensions.json and bind nothing, because a "
    "PyPSA Link has no e_sum_min or e_sum_max: %s"
)

# Records one bound that a link does not hold: the name of the record and the field.
BoundRecorder = Callable[[str, str], None]


def report_link_bounds(records: Sequence[ActivityExtension], record: BoundRecorder) -> None:
    """Record each annual bound of `records`, and warn once."""
    labels = [
        f"{entry.name}.{field_name}"
        for entry in records
        for field_name in _BOUND_FIELDS
        if getattr(entry, field_name)
    ]
    for label in labels:
        name, _, field_name = label.rpartition(".")
        record(name, field_name)
    if labels:
        log.warning(_BOUND_WARNING, len(labels), name_a_few(labels))
