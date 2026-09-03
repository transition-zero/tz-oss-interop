"""Which replications a Monte Carlo translation emits."""

from __future__ import annotations

import logging

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.plexos_constants import PlexosClass
from interop.plugins.shared.plexos_pypsa_translations.decisions import (
    SourceReporter,
    SourceValue,
)
from interop.plugins.shared.staged_samples import (
    ensemble_samples,
    record_ensemble_samples,
    staged_sample_sets,
)

log = logging.getLogger(__name__)

_NO_NETWORKS_NOTE = "the ensemble pipeline will write no networks"


def choose_ensemble_samples(state: State, recorder: ScopedRecorder) -> None:
    """Record the replications every sampled profile carries, skipping any that is partial.

    Records nothing, rather than an empty table, when there is nothing to emit; the ensemble
    sink then writes zero files, which would otherwise be a silent success, so both ways a
    model ends up with no shared replication are logged.
    """
    per_profile = staged_sample_sets(state)
    if not per_profile:
        log.warning("plexos: no sampled profile is staged; %s", _NO_NETWORKS_NOTE)
        return
    shared = ensemble_samples(per_profile)
    reporter = SourceReporter(recorder)
    for dropped in sorted(set.union(*per_profile) - set(shared), key=int):
        reporter.record_skipped(
            SourceValue(PlexosClass.DATA_FILE, dropped, None, dropped),
            f"replication {dropped} is missing from at least one sampled profile, so an "
            "ensemble network built from it would mix real data with a gap",
        )
    if not shared:
        log.warning(
            "plexos: no replication is common to every sampled profile; %s", _NO_NETWORKS_NOTE
        )
        return
    record_ensemble_samples(state, shared)
