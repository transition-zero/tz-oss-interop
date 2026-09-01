"""OSeMOSYS vocabulary shared across pipelines reading an OSeMOSYS model.

Set names and the value column are OSeMOSYS's own and are kept verbatim: they are the keys
and the columns ``stage_osemosys_csv`` stages. Only the sets the source acts on by name are
listed here. The otoole config declares every set a model has, and the source reads what the
config declares rather than a list of its own.
"""

from __future__ import annotations

from enum import StrEnum


class OsemosysSet(StrEnum):
    """The OSeMOSYS set names the source acts on by name."""

    TIMESLICE = "TIMESLICE"
    TECHNOLOGY = "TECHNOLOGY"
    FUEL = "FUEL"
    STORAGE = "STORAGE"


COMPONENT_SETS: tuple[OsemosysSet, ...] = (
    OsemosysSet.TECHNOLOGY,
    OsemosysSet.FUEL,
    OsemosysSet.STORAGE,
)
"""The sets whose members are components, so a parameter indexed by one holds their profile."""


OSEMOSYS_VALUE_COLUMN = "VALUE"
"""The last column of every otoole CSV, and the only column of a set CSV."""


OSEMOSYS_DECLARATIONS_TABLE = "declarations"
"""``State.source_topology`` key of the table stating what the config declared."""


class OsemosysDeclarationCol:
    """Columns of the ``declarations`` table.

    A CSV holds only the values that differ from the default, so a step needs ``default`` to
    read a row the file leaves out. ``is_staged`` is false where the config declared an entry
    the folder did not hold.
    """

    NAME = "name"
    ENTRY_TYPE = "entry_type"
    DTYPE = "dtype"
    INDICES = "indices"
    DEFAULT = "default"
    SHORT_NAME = "short_name"
    IS_STAGED = "is_staged"
