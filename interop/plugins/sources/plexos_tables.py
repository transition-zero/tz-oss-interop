"""The PLEXOS XML's own table vocabulary, shared by everything that reads it.

A PLEXOS input file is a normalised relational schema: ``t_class`` names each class,
``t_object`` holds one row per object, and every other table keys off those ids. The
row types, the table and column names, and the id lookups here are what each staging
concern reads it through.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from interop.ports.outbound.validation import EnergyModelValidationError, ValidationSeverity

# The parsed XML as its own tables: one list of rows per ``t_*`` table, or per class.
Rows = list[dict[str, Any]]
RowsByTable = dict[str, Rows]
RowsByClass = dict[str, Rows]

OBJECT_TABLE = "t_object"
CLASS_TABLE = "t_class"
MEMBERSHIP_TABLE = "t_membership"
DATA_TABLE = "t_data"
PROPERTY_TABLE = "t_property"
TAG_TABLE = "t_tag"
TEXT_TABLE = "t_text"
CLASS_ID = "class_id"
OBJECT_ID = "object_id"
MEMBERSHIP_ID = "membership_id"
DATA_ID = "data_id"
PROPERTY_ID = "property_id"
CHILD_OBJECT_ID = "child_object_id"
NAME = "name"
# The raw payload column that t_data, t_text and t_attribute_data each carry.
VALUE = "value"


def objects_of_class(tables: RowsByTable, class_name: str) -> set[str]:
    """The object ids of every object of one PLEXOS class."""
    class_id = class_id_of(tables, class_name)
    return {row[OBJECT_ID] for row in tables.get(OBJECT_TABLE, []) if row[CLASS_ID] == class_id}


def class_id_of(tables: RowsByTable, class_name: str) -> str | None:
    """The id ``t_class`` gives one class name, or None where the file names no such class."""
    for row in tables.get(CLASS_TABLE, []):
        if row[NAME] == class_name:
            return str(row[CLASS_ID])
    return None


def build_child_by_membership(tables: RowsByTable) -> dict[Any, Any]:
    """The child object id of each membership, by the membership's id."""
    return {row[MEMBERSHIP_ID]: row[CHILD_OBJECT_ID] for row in tables.get(MEMBERSHIP_TABLE, [])}


@dataclass(frozen=True)
class Lookup:
    """One table's values by id, and the table's name for reporting."""

    table: str
    by_id: dict[Any, Any]


def build_name_lookup(tables: RowsByTable, table: str, id_column: str) -> Lookup:
    """One table's ``name`` column by id, to resolve the references into it."""
    return Lookup(table, {row[id_column]: row[NAME] for row in tables.get(table, [])})


@dataclass(frozen=True)
class Reference:
    """One row's pointer at another table: where it came from and the id it points at."""

    table: str
    row_id: Any
    column: str
    value: Any


def build_data_reference(data: dict[str, Any], column: str) -> Reference:
    """The pointer that one column of a ``t_data`` row holds."""
    return Reference(DATA_TABLE, data[DATA_ID], column, data[column])


class DroppedRecords:
    """Records the rows dropped for pointing at an id nothing defines.

    A PLEXOS export can be filtered or hand-edited into referring to rows it no longer
    carries. Such a row cannot be resolved, so it is left out of the staged tables and
    recorded as a validation error rather than raised: the rest of the model still stages.
    """

    def __init__(self, validator: str) -> None:
        self._validator = validator
        self._errors: list[EnergyModelValidationError] = []

    @property
    def errors(self) -> list[EnergyModelValidationError]:
        return list(self._errors)

    def resolve(self, lookup: Lookup, reference: Reference) -> Any | None:
        """The value the reference points at, or None once the dangling id is recorded."""
        if reference.value in lookup.by_id:
            return lookup.by_id[reference.value]
        self._record(lookup, reference)
        return None

    def _record(self, lookup: Lookup, reference: Reference) -> None:
        self._errors.append(
            EnergyModelValidationError(
                validator=self._validator,
                severity=ValidationSeverity.WARNING,
                component=reference.table,
                name=str(reference.row_id),
                message=(
                    f"{reference.column} {reference.value!r} is not defined "
                    f"in {lookup.table}; the row is dropped"
                ),
                attribute=reference.column,
                value=reference.value,
            )
        )
