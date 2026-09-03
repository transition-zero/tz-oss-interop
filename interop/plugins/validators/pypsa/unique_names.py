from __future__ import annotations

from typing import ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import State, Validator
from interop.plugins.shared.pypsa_constants import (
    PYPSA_COMPONENT_NAMING,
    PYPSA_NAME_COLUMN,
    PyPSAComponentNaming,
)
from interop.ports.outbound.validation import ValidationSeverity

_OCCURRENCES = "occurrences"


class PypsaUniqueNames(Validator):
    """Flag components that share a name with another component of the same class.

    PyPSA has no global name registry: each class is its own table, and a class's names are
    only meaningful if unique within it. A within-class duplicate breaks translation (Sienna
    ids are assigned by row position, so two components collapse onto one name Sienna rejects)
    and makes bus-reference resolution ambiguous. Every staged class is checked, not only the
    ones the translator consumes, so the source network is validated as a whole. Each
    duplicated name is reported once, as CRITICAL.
    """

    name: ClassVar[str] = "pypsa_unique_names"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def validate(self, state: State, params: BaseModel | None) -> None:
        for table_key, table in state.source_topology.items():
            if PYPSA_NAME_COLUMN not in table.collect_schema().names():
                continue
            naming = PYPSA_COMPONENT_NAMING.get(
                table_key, PyPSAComponentNaming(table_key, table_key, table_key)
            )
            duplicated_names = (
                table.select(PYPSA_NAME_COLUMN)
                .group_by(PYPSA_NAME_COLUMN)
                .agg(pl.len().alias(_OCCURRENCES))
                .filter(pl.col(_OCCURRENCES) > 1)
                .collect()
            )
            for row in duplicated_names.iter_rows(named=True):
                duplicated_name = row[PYPSA_NAME_COLUMN]
                self.emit_validation_error(
                    state,
                    ValidationSeverity.CRITICAL,
                    naming.display,
                    duplicated_name,
                    f"'{duplicated_name}' is not a unique name for a {naming.singular}",
                    attribute=PYPSA_NAME_COLUMN,
                    value=duplicated_name,
                )
