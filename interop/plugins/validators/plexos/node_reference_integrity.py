"""Every membership must name an object the model states."""

from __future__ import annotations

from typing import ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import State, Validator
from interop.plugins.shared.plexos_constants import (
    PlexosClass,
    PlexosMembershipCol,
    PlexosObjectCol,
    PlexosResolvedTable,
)
from interop.ports.outbound.validation import ValidationSeverity

# The classes a translation resolves a reference against. A membership naming an object no
# staged table holds leaves the component that names it with nothing to connect to.
_REFERENCED_CLASSES: tuple[PlexosClass, ...] = (
    PlexosClass.NODE,
    PlexosClass.REGION,
    PlexosClass.FUEL,
    PlexosClass.STORAGE,
)


class PlexosNodeReferenceIntegrity(Validator):
    """Flag a membership that names an object no staged table holds.

    PLEXOS relates two objects by name, so an export that loses an object leaves every
    membership naming it pointing at nothing. A generator on a missing Node has no bus, and
    a turbine on a missing Storage has no reservoir, so each dangling reference is CRITICAL.
    """

    name: ClassVar[str] = "plexos_node_reference_integrity"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def validate(self, state: State, params: BaseModel | None) -> None:
        memberships = state.source_topology.get(PlexosResolvedTable.MEMBERSHIPS)
        if memberships is None:
            return
        rows = memberships.collect()
        for plexos_class in _REFERENCED_CLASSES:
            known = self._names_of(state, plexos_class)
            if known is None:
                continue
            dangling = rows.filter(
                (pl.col(PlexosMembershipCol.CHILD_CLASS) == str(plexos_class))
                & ~pl.col(PlexosMembershipCol.CHILD_OBJECT).is_in(list(known))
            )
            for row in dangling.iter_rows(named=True):
                self._report(state, plexos_class, row)

    def _names_of(self, state: State, plexos_class: PlexosClass) -> set[str] | None:
        table = state.source_topology.get(plexos_class)
        if table is None:
            return None
        return set(table.select(PlexosObjectCol.NAME).collect()[PlexosObjectCol.NAME])

    def _report(self, state: State, plexos_class: PlexosClass, row: dict[str, object]) -> None:
        child = row[PlexosMembershipCol.CHILD_OBJECT]
        self.emit_validation_error(
            state,
            ValidationSeverity.CRITICAL,
            str(row[PlexosMembershipCol.PARENT_CLASS]),
            str(row[PlexosMembershipCol.PARENT_OBJECT]),
            f"names a {plexos_class} '{child}' the model does not state",
            attribute=str(row[PlexosMembershipCol.COLLECTION]),
            value=child,
        )
