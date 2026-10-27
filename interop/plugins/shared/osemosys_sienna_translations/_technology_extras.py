"""The values of a technology that the record of its component holds and its Sienna type does not.

They are the technology values, the annual activity bounds and the values of the operating
modes. One `TechnologyExtras` reads them, notes their rows as persisted, and gives the fields
and the events of the record, so a component cannot read a value and leave out one of the rest.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.osemosys_canonical.constants import (
    OPERATING_MODE,
    REGION,
    TECHNOLOGY,
    FlowParameter,
)
from interop.plugins.shared.osemosys_sienna_translations._activity_limits import (
    LOWER_BOUND,
    UPPER_BOUND,
    build_bound_events,
    build_yearly_limits,
    enrich_activity_limits,
    set_bounds_persisted,
)
from interop.plugins.shared.osemosys_sienna_translations._operating_modes import (
    OPERATING_MODES,
    build_mode_events,
    build_operating_mode_field,
    build_operating_modes,
    set_mode_bounds_persisted,
)
from interop.plugins.shared.osemosys_sienna_translations._operations import OperationsYear
from interop.plugins.shared.osemosys_sienna_translations._technology_values import (
    TechnologyValue,
    ValueOwners,
    build_value_events,
    build_value_fields,
    enrich_technology_values,
    set_values_persisted,
)
from interop.ports.outbound.reporting import TranslationEvent

_KEYS = [REGION, TECHNOLOGY]
_HELD_KEYS = [REGION, TECHNOLOGY, OPERATING_MODE]


@dataclass(frozen=True)
class TechnologyExtras:
    """The record kind and the values of one component kind, and the flow that rates it.

    `run_parameters` are the values of a held mode that the component holds itself.
    """

    owners: ValueOwners
    values: Sequence[TechnologyValue]
    run_parameters: frozenset[str]
    rated_flow: FlowParameter

    def enrich(
        self, state: State, operations: OperationsYear, members: pl.DataFrame
    ) -> pl.DataFrame:
        """`members` with the values, the bounds and the mode values of each member.

        `members` holds `region`, `technology`, the `operating_mode` that the component runs and
        that rates it, and `rating_ratio`.
        """
        held = members.select(_HELD_KEYS)
        table = enrich_technology_values(state, operations, members, self.values)
        bounds = enrich_activity_limits(state, operations, held, self.rated_flow)
        table = table.join(bounds.drop(OPERATING_MODE), on=_KEYS, how="left")
        modes = build_operating_modes(state, operations, held, self.run_parameters)
        return modes.enrich(table)

    def set_persisted(self, state: State, members: pl.DataFrame) -> None:
        """Note that the records of the kind hold each value, bound and mode value of `members`."""
        set_values_persisted(state, self.owners, members, self.values)
        set_mode_bounds_persisted(state, self.owners, members)
        set_bounds_persisted(state, self.owners, members)

    def build_fields(self, row: dict[str, Any]) -> dict[str, Any]:
        """The fields of the record of one member that these values fill."""
        return {
            LOWER_BOUND.extension_field: build_yearly_limits(row[LOWER_BOUND.column]),
            UPPER_BOUND.extension_field: build_yearly_limits(row[UPPER_BOUND.column]),
            OPERATING_MODES: build_operating_mode_field(row),
            **build_value_fields(row, self.values),
        }

    def build_events(self, row: dict[str, Any]) -> list[TranslationEvent]:
        """One event for each bound, value and mode value that the record of one member holds."""
        return [
            *build_bound_events(row, self.owners, self.rated_flow),
            *build_value_events(row, self.values, self.owners),
            *build_mode_events(row, self.owners),
        ]
