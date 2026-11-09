"""OSeMOSYS emission limits, renewable targets and reserve margins -> extensions.json."""

from __future__ import annotations

from typing import ClassVar

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.osemosys_sienna_translations import (
    OperationsMapping,
    OperationsYear,
    add_built_records,
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
        add_built_records(state, policies.built, self._recorder)
        report_policy_changes(policies, self._recorder)
        set_policies_persisted(state, policies)
