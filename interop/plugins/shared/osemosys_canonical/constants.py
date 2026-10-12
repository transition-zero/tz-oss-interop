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

# The column of a raw set table, and the value column of a raw parameter table.
RAW_VALUE_COL = "VALUE"
# The column of a canonical set table, and the value column of a canonical table.
VALUE_COL = "value"

# The OSeMOSYS names of the sets, which the raw stage keeps.
OSEMOSYS_REGION = "REGION"
OSEMOSYS_TECHNOLOGY = "TECHNOLOGY"
OSEMOSYS_FUEL = "FUEL"
OSEMOSYS_EMISSION = "EMISSION"
OSEMOSYS_MODE_OF_OPERATION = "MODE_OF_OPERATION"
OSEMOSYS_STORAGE = "STORAGE"
OSEMOSYS_YEAR = "YEAR"
OSEMOSYS_TIMESLICE = "TIMESLICE"
OSEMOSYS_SEASON = "SEASON"
OSEMOSYS_DAYTYPE = "DAYTYPE"
OSEMOSYS_DAILYTIMEBRACKET = "DAILYTIMEBRACKET"
OSEMOSYS_REGIONGROUP = "REGIONGROUP"
# The column name of a second region in a key, as otoole and the TZ format write it.
OSEMOSYS_SECOND_REGION = "_REGION"

# The canonical names of the sets and key columns that the engine reads.
REGION = "region"
TECHNOLOGY = "technology"
FUEL = "fuel"
STORAGE = "storage"
OPERATING_MODE = "operating_mode"
TIMESLICE = "timeslice"
# The two regions of a pair, each of which holds a member of the region set.
START_REGION = "start_region"
END_REGION = "end_region"


class DeclarationColumn(StrEnum):
    """The columns of the raw declarations table."""

    NAME = "name"
    KEY = "key"
    DEFAULT = "default"


class MetadataTable(StrEnum):
    """The tables of the canonical metadata."""

    DEFAULTS = "defaults"
    UNITS = "units"
    SCHEMA = "schema"


class MetadataColumn(StrEnum):
    """The columns of the canonical metadata tables."""

    KIND = "kind"
    PARAMETER = "parameter"
    DEFAULT = "default"
    QUANTITY = "quantity"
    UNIT = "unit"
    SCHEMA_VERSION = "schema_version"


# The note of a table or a set that the engine maps with no row of the user mappings file.
AUTOMATIC_MATCH_NOTE = "matched by name and key"


class TechnologyKind(StrEnum):
    """What a technology is, from a closed list; the first kind that fits wins, in this order.

    A value is a Sienna type name when Sienna has the type."""

    STORAGE_TECHNOLOGY = "StorageTechnology"
    AGGREGATE_TRANSPORT_TECHNOLOGY = "AggregateTransportTechnology"
    SUPPLY_TECHNOLOGY = "SupplyTechnology"
    FUEL_SUPPLY = "fuel_supply"
    EXPORT = "export"
    CONVERSION = "conversion"


class OtooleEntryType(StrEnum):
    """The `type` of one entry of an otoole config YAML."""

    SET = "set"
    PARAM = "param"
    RESULT = "result"


CSV_SUFFIX = ".csv"
YAML_SUFFIXES = (".yaml", ".yml")


class RemoveRule(StrEnum):
    """How a `remove_column` operation turns the values of an extra set into one value."""

    CHOOSE = "choose"
    MEAN = "mean"
    SUM = "sum"
    MIN = "min"
    MAX = "max"


# The hidden column that names the raw table of each row while the engine merges raw tables.
RAW_TABLE_COL = "__raw_table"
# How a message names the `parameters:` part and the `sets:` part of a user mappings file.
PARAMETERS_PART = "`parameters:`"
SETS_PART = "`sets:`"
# The hidden column that counts the rows a summary describes.
ROW_COUNT_COL = "__row_count"

# How a message names one list of the `objects:` part of a user mappings file.
OBJECT_PART_LABEL = "`objects: {part}`"


class ObjectPart(StrEnum):
    """The lists of the `objects:` part, one for each annotated set."""

    TECHNOLOGIES = "technologies"
    FUELS = "fuels"
    STORAGES = "storages"
    REGIONS = "regions"


class AnnotationColumn(StrEnum):
    """The annotation columns that follow the key of an annotation table."""

    KIND = "kind"
    CATEGORY = "category"
    CARRIER = "carrier"
    LOCATION = "location"


# The set that each list of `objects:` annotates, in the order the engine annotates them.
OBJECT_PART_SETS: dict[ObjectPart, str] = {
    ObjectPart.REGIONS: REGION,
    ObjectPart.FUELS: FUEL,
    ObjectPart.STORAGES: STORAGE,
    ObjectPart.TECHNOLOGIES: TECHNOLOGY,
}

# The annotation columns of each list of `objects:`, which are also its annotation table's.
OBJECT_PART_COLUMNS: dict[ObjectPart, tuple[AnnotationColumn, ...]] = {
    ObjectPart.REGIONS: (AnnotationColumn.LOCATION,),
    ObjectPart.FUELS: (AnnotationColumn.CARRIER, AnnotationColumn.LOCATION),
    ObjectPart.STORAGES: (AnnotationColumn.LOCATION,),
    ObjectPart.TECHNOLOGIES: (
        AnnotationColumn.KIND,
        AnnotationColumn.CATEGORY,
        AnnotationColumn.LOCATION,
    ),
}

# The carrier whose fuels the kind inference counts as electricity.
ELECTRICITY_CARRIER = "electricity"
# The character between the two locations of a technology that touches two locations.
LOCATION_SEPARATOR = "~"
# The character between the region and the member in the name of an annotation event.
ANNOTATION_NAME_SEPARATOR = "/"


class FlowParameter(StrEnum):
    """The canonical parameters whose rows show what a technology takes in and puts out."""

    INPUT_ACTIVITY_RATIO = "input_activity_ratio"
    OUTPUT_ACTIVITY_RATIO = "output_activity_ratio"
    TECHNOLOGY_TO_STORAGE = "technology_to_storage"
    TECHNOLOGY_FROM_STORAGE = "technology_from_storage"
