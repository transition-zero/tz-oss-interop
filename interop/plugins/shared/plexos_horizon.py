"""What a PLEXOS Model says about the window every profile has to fit.

PLEXOS keeps the chronology on a Horizon object the Model relates to. A run narrows the
profiles to one Model's Horizon, so naming the Models that declare one is what tells a
caller how to settle a window the profiles disagree on.
"""

from __future__ import annotations

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.plexos_constants import (
    PlexosClass,
    PlexosMembershipCol,
    PlexosResolvedTable,
)

# The class name is the source's own vocabulary and is not among the classes a mapping reads.
HORIZON_CLASS = "Horizon"

_MODELS_NAMED = 6


def horizon_advice(state: State) -> str:
    """What would settle one window for every profile."""
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
        & (pl.col(PlexosMembershipCol.CHILD_CLASS) == HORIZON_CLASS)
    ).select(PlexosMembershipCol.PARENT_OBJECT)
    return sorted(set(related.collect()[PlexosMembershipCol.PARENT_OBJECT].to_list()))
