"""The operating modes of one technology, and the one mode that its Sienna component runs.

A Sienna component runs one operating mode and holds the cost, the flows and the emissions of
that mode itself. So the sidecar states each other mode of the technology in full, and states
the mode that the component runs with its bounds alone. The leg reads the held mode back from
that shape, and names it after the first mode name that no entry claims where the shape does
not state it.
"""

from __future__ import annotations

from collections.abc import Sequence

from interop.core.extensions import GeneratorExtension, OperatingMode

# The record field that the modes of a technology come from.
MODE_MAPPED_FIELDS = ("operating_modes",)
# The name of the first operating mode of a model, which OSeMOSYS numbers from 1.
FIRST_MODE_NUMBER = 1


def list_mode_records(record: GeneratorExtension) -> list[OperatingMode]:
    """Each mode that the sidecar states for the technology of one record."""
    return list(record.operating_modes or [])


def build_held_mode(modes: Sequence[OperatingMode]) -> str:
    """The name of the mode that the Sienna component runs.

    An entry that states an activity ratio is a mode that the component does not run, because
    the forward leg kept the flows of the held mode out of the sidecar.
    """
    for mode in modes:
        if mode.input_ratios is None and mode.output_ratios is None:
            return mode.mode
    return _build_unclaimed_mode({mode.mode for mode in modes})


def _build_unclaimed_mode(claimed: set[str]) -> str:
    number = FIRST_MODE_NUMBER
    while str(number) in claimed:
        number += 1
    return str(number)
