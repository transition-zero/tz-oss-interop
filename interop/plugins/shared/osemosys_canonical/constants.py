from __future__ import annotations

from enum import StrEnum

OSEMOSYS_FRAMEWORK = "osemosys"
CANONICAL_FRAMEWORK = "osemosys-canonical"


class TableKind(StrEnum):
    SET = "set"
    PARAMETER = "parameter"
    EXTENSION = "extension"
    ANNOTATION = "annotation"
    METADATA = "metadata"


TABLE_DIRECTORIES: dict[TableKind, str] = {
    TableKind.SET: "sets",
    TableKind.PARAMETER: "parameters",
    TableKind.EXTENSION: "extensions",
    TableKind.ANNOTATION: "annotations",
    TableKind.METADATA: "metadata",
}

TABLE_KEY_SEPARATOR = "/"

RAW_DIRECTORY = "raw"
CANONICAL_DIRECTORY = "canonical"
PARQUET_SUFFIX = ".parquet"
DECLARATIONS_TABLE = "declarations"

# A raw set table also holds its members in this column.
RAW_VALUE_COL = "VALUE"
# A canonical set table also holds its members in this column.
VALUE_COL = "value"

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

REGION = "region"
TECHNOLOGY = "technology"
FUEL = "fuel"
STORAGE = "storage"
OPERATING_MODE = "operating_mode"
TIMESLICE = "timeslice"
START_REGION = "start_region"
END_REGION = "end_region"


class DeclarationColumn(StrEnum):
    NAME = "name"
    KEY = "key"
    DEFAULT = "default"


class MetadataTable(StrEnum):
    DEFAULTS = "defaults"
    UNITS = "units"
    SCHEMA = "schema"


class MetadataColumn(StrEnum):
    KIND = "kind"
    PARAMETER = "parameter"
    DEFAULT = "default"
    QUANTITY = "quantity"
    UNIT = "unit"
    SCHEMA_VERSION = "schema_version"


AUTOMATIC_MATCH_NOTE = "matched by name and key"


class TechnologyKind(StrEnum):
    """A value that Sienna has as a type is the Sienna type name, so do not change its spelling."""

    STORAGE_TECHNOLOGY = "StorageTechnology"
    AGGREGATE_TRANSPORT_TECHNOLOGY = "AggregateTransportTechnology"
    SUPPLY_TECHNOLOGY = "SupplyTechnology"
    FUEL_SUPPLY = "fuel_supply"
    EXPORT = "export"
    CONVERSION = "conversion"


class OtooleEntryType(StrEnum):
    SET = "set"
    PARAM = "param"
    RESULT = "result"


CSV_SUFFIX = ".csv"
YAML_SUFFIXES = (".yaml", ".yml")


class RemoveRule(StrEnum):
    CHOOSE = "choose"
    MEAN = "mean"
    SUM = "sum"
    MIN = "min"
    MAX = "max"


# The leading underscores keep this temporary column from clashing with a column of the model.
RAW_TABLE_COL = "__raw_table"
PARAMETERS_PART = "`parameters:`"
SETS_PART = "`sets:`"
ROW_COUNT_COL = "__row_count"

OBJECT_PART_LABEL = "`objects: {part}`"


class ObjectPart(StrEnum):
    TECHNOLOGIES = "technologies"
    FUELS = "fuels"
    STORAGES = "storages"
    REGIONS = "regions"


class AnnotationColumn(StrEnum):
    KIND = "kind"
    CATEGORY = "category"
    CARRIER = "carrier"
    LOCATION = "location"


OBJECT_PART_SETS: dict[ObjectPart, str] = {
    ObjectPart.REGIONS: REGION,
    ObjectPart.FUELS: FUEL,
    ObjectPart.STORAGES: STORAGE,
    ObjectPart.TECHNOLOGIES: TECHNOLOGY,
}

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

ELECTRICITY_CARRIER = "electricity"
# The character between the two locations of a technology that touches two locations.
LOCATION_SEPARATOR = "~"
# The character between the region and the member in the name of an annotation event.
ANNOTATION_NAME_SEPARATOR = "/"


class FlowParameter(StrEnum):
    INPUT_ACTIVITY_RATIO = "input_activity_ratio"
    OUTPUT_ACTIVITY_RATIO = "output_activity_ratio"
    TECHNOLOGY_TO_STORAGE = "technology_to_storage"
    TECHNOLOGY_FROM_STORAGE = "technology_from_storage"
