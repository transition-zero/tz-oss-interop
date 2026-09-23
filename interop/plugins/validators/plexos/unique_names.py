"""Every PLEXOS object of one class must carry a name of its own."""

from __future__ import annotations

from typing import ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import State, Validator
from interop.plugins.shared.plexos_constants import PlexosObjectCol
from interop.ports.outbound.validation import ValidationSeverity

_OCCURRENCES = "occurrences"


class PlexosUniqueNames(Validator):
    """Flag PLEXOS objects that share a name with another object of the same class.

    A PLEXOS membership names its parent and its child by name, so two objects of one class
    sharing a name make every membership that names it ambiguous. The translation then
    resolves a bus, a fuel or a reservoir to whichever row it reads first. Each duplicated
    name is reported once, as CRITICAL.
    """

    name: ClassVar[str] = "plexos_unique_names"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def validate(self, state: State, params: BaseModel | None) -> None:
        for plexos_class, table in state.source_topology.items():
            if PlexosObjectCol.NAME not in table.collect_schema().names():
                continue
            duplicated = (
                table.select(PlexosObjectCol.NAME)
                .group_by(PlexosObjectCol.NAME)
                .agg(pl.len().alias(_OCCURRENCES))
                .filter(pl.col(_OCCURRENCES) > 1)
                .collect()
            )
            for row in duplicated.iter_rows(named=True):
                duplicated_name = row[PlexosObjectCol.NAME]
                self.emit_validation_error(
                    state,
                    ValidationSeverity.CRITICAL,
                    plexos_class,
                    duplicated_name,
                    f"'{duplicated_name}' is not a unique name for a {plexos_class}",
                    attribute=PlexosObjectCol.NAME,
                    value=duplicated_name,
                )
