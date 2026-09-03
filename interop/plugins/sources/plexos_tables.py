"""The PLEXOS XML's own table vocabulary, shared by everything that reads it.

A PLEXOS input file is a normalised relational schema: ``t_class`` names each class,
``t_object`` holds one row per object, and every other table keys off those ids. The
row types and the two id lookups here are what each staging concern reads it through.
"""

from __future__ import annotations

from typing import Any

# The parsed XML as its own tables: one list of rows per ``t_*`` table, or per class.
Rows = list[dict[str, Any]]
RowsByTable = dict[str, Rows]
RowsByClass = dict[str, Rows]

OBJECT_TABLE = "t_object"
CLASS_TABLE = "t_class"
CLASS_ID = "class_id"
OBJECT_ID = "object_id"
NAME = "name"


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
