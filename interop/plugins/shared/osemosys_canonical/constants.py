"""Names that the OSeMOSYS sources, the mappings engine and the canonical sink share."""

from __future__ import annotations

from enum import StrEnum

# The framework that a SourceField names: the model as its source file states it.
OSEMOSYS_FRAMEWORK = "osemosys"
# The framework that a DestinationField names: the canonical stage.
CANONICAL_FRAMEWORK = "osemosys-canonical"


class TableKind(StrEnum):
    """What one table of a stage holds."""

    SET = "set"
    PARAMETER = "parameter"
    EXTENSION = "extension"
    ANNOTATION = "annotation"
    METADATA = "metadata"


# The directory under a stage that holds the tables of each kind.
TABLE_DIRECTORIES: dict[TableKind, str] = {
    TableKind.SET: "sets",
    TableKind.PARAMETER: "parameters",
    TableKind.EXTENSION: "extensions",
    TableKind.ANNOTATION: "annotations",
    TableKind.METADATA: "metadata",
}

# The character between the kind and the name in a `State.source_topology` key.
TABLE_KEY_SEPARATOR = "/"

RAW_DIRECTORY = "raw"
CANONICAL_DIRECTORY = "canonical"
PARQUET_SUFFIX = ".parquet"
DECLARATIONS_TABLE = "declarations"

# The column of a set table, and the value column of a parameter table.
VALUE_COL = "VALUE"
# The column name of a second region in a key, as otoole and the TZ format write it.
SECOND_REGION = "_REGION"
TIMESLICE = "TIMESLICE"
REGION = "REGION"


class DeclarationCol(StrEnum):
    """The columns of the raw declarations table."""

    NAME = "name"
    KEY = "key"
    DEFAULT = "default"


class MetadataTable(StrEnum):
    """The tables of the canonical metadata."""

    DEFAULTS = "defaults"
    UNITS = "units"
    SCHEMA = "schema"


class MetadataCol(StrEnum):
    """The columns of the canonical metadata tables."""

    PARAMETER = "parameter"
    DEFAULT = "default"
    QUANTITY = "quantity"
    UNIT = "unit"
    SCHEMA_VERSION = "schema_version"


# The note of a table or a set that the engine maps with no row of the user mappings file.
AUTOMATIC_MATCH_NOTE = "matched by name and key"


class TechnologyKind(StrEnum):
    """What a technology is, from a closed list; the first kind that fits wins, in this order."""

    STORAGE = "storage"
    LINK = "link"
    GENERATOR = "generator"
    SUPPLY = "supply"
    EXPORT = "export"
    CONVERSION = "conversion"


class OtooleEntryType(StrEnum):
    """The `type` of one entry of an otoole config YAML."""

    SET = "set"
    PARAM = "param"
    RESULT = "result"


CSV_SUFFIX = ".csv"
