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
# The character between the parts of a source name, such as `technologies.GAS.capex`.
NAME_SEPARATOR = "."

RAW_DIRECTORY = "raw"
CANONICAL_DIRECTORY = "canonical"
# The parameter tables before the absent-member rule, written so that each computes once.
PLANNED_DIRECTORY = "planned"
PARQUET_SUFFIX = ".parquet"
DECLARATIONS_TABLE = "declarations"

# A raw set table also holds its members in this column.
RAW_VALUE_COL = "VALUE"
# A canonical set table also holds its members in this column.
VALUE_COL = "value"

# The column name of a second region in a key, as otoole and the TZ format write it.
OSEMOSYS_SECOND_REGION = "_REGION"

REGION = "region"
TECHNOLOGY = "technology"
FUEL = "fuel"
POLLUTANT = "pollutant"
STORAGE = "storage"
OPERATING_MODE = "operating_mode"
YEAR = "year"
TIMESLICE = "timeslice"
SEASON = "season"
DAY_TYPE = "day_type"
DAILY_TIME_BRACKET = "daily_time_bracket"
REGION_GROUP = "region_group"
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
    DEFAULT_FROM = "default_from"
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
