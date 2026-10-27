"""OSeMOSYS emission limits, renewable targets and reserve margins -> extensions.json."""

from __future__ import annotations

from typing import ClassVar

from interop.core.extensions import ExtensionKind, append_extensions
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.osemosys_sienna_translations import (
    OperationsMapping,
    OperationsYear,
    build_policies,
    list_model_years,
    report_policy_changes,
    set_policies_persisted,
)


class OsemosysToSiennaMapPolicies(OperationsMapping):
    """Writes one constraint record for each policy of the model, over every year in scope."""

    step_name: ClassVar[str] = "osemosys_to_sienna_map_policies"

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def map_components(self, state: State, operations: OperationsYear) -> None:
        policies = build_policies(state, list_model_years(state), operations.units)
        append_extensions(state.destination_extensions, ExtensionKind.CONSTRAINT, policies.records)
        for event in policies.events:
            self._recorder.append(event)
        report_policy_changes(policies, self._recorder)
        set_policies_persisted(state, policies)
