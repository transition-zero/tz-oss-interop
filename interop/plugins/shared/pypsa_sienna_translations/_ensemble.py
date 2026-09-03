"""Which replications of a staged ensemble a translation writes a system for."""

from __future__ import annotations

import logging

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import Framework
from interop.plugins.shared.staged_samples import (
    ensemble_samples,
    record_ensemble_samples,
    staged_sample_sets,
)
from interop.plugins.shared.warning_text import name_a_few
from interop.ports.outbound.reporting import EventKind, SourceField, TranslationEvent

log = logging.getLogger(__name__)

# What a left-out replication is named as. It is no PyPSA component, but one whole network
# of the ensemble, so the report names it for what it is.
_REPLICATION = "replication"

_PARTIAL_REASON = (
    "is missing from at least one sampled profile, so a system built from it would mix real "
    "data with a gap"
)


def choose_ensemble_samples(state: State, recorder: ScopedRecorder) -> None:
    """Record the replications every sampled profile carries, reporting any that is partial.

    An ensemble writes one system per replication every sampled profile carries, so a
    replication only some of them carry is left out. Nothing is recorded where no replication
    survives, and the sink says the ensemble holds no system.

    A model whose profiles carry no replication at all is no ensemble, so it has none to
    choose between and nothing to say.
    """
    per_profile = staged_sample_sets(state)
    if not per_profile:
        return
    shared = ensemble_samples(per_profile)
    _report_partial(sorted(set.union(*per_profile) - set(shared), key=int), recorder)
    record_ensemble_samples(state, shared)


def _report_partial(partial: list[str], recorder: ScopedRecorder) -> None:
    """Say which replications no system is written for, and why."""
    if not partial:
        return
    for sample in partial:
        recorder.append(
            TranslationEvent(
                kind=EventKind.COMPONENT_SKIPPED,
                sources=[
                    SourceField(framework=Framework.PYPSA, component=_REPLICATION, name=sample)
                ],
                note=f"replication {sample} {_PARTIAL_REASON}",
            )
        )
    log.warning(
        "%s replication(s) of the ensemble %s, so no system is written for them: %s",
        len(partial),
        _PARTIAL_REASON,
        name_a_few(partial),
    )
