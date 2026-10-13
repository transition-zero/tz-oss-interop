from __future__ import annotations

from typing import NamedTuple

import polars as pl

from interop.core.reporting import EventRecorder
from interop.plugins.shared.osemosys_canonical.constants import (
    MetadataColumn,
    MetadataTable,
    TableKind,
)
from interop.plugins.shared.osemosys_canonical.events import (
    AppliedDefault,
    TableNames,
    record_default_applied,
)
from interop.plugins.shared.osemosys_canonical.mapping_inputs import MappingInputs
from interop.plugins.shared.osemosys_canonical.mappings import Units
from interop.plugins.shared.osemosys_canonical.parameter_mapping import MappedParameters
from interop.plugins.shared.osemosys_canonical.schema import CanonicalParameter, CanonicalSchema

_DEFAULTS_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    MetadataColumn.KIND: pl.Utf8,
    MetadataColumn.PARAMETER: pl.Utf8,
    MetadataColumn.DEFAULT: pl.Float64,
    MetadataColumn.DEFAULT_FROM: pl.Utf8,
}
_UNITS_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    MetadataColumn.QUANTITY: pl.Utf8,
    MetadataColumn.UNIT: pl.Utf8,
}
_SCHEMA_VERSION_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    MetadataColumn.SCHEMA_VERSION: pl.Int64,
}
_SCHEMA_DEFAULT_NOTE = (
    "the model declares no default, so the canonical stage takes the default of the canonical "
    "schema"
)
_DEFAULT_FROM_NOTE = (
    "the model declares no default, so the default is the value of {source} at the same key "
    "columns, which a consumer joins"
)


class CanonicalDefault(NamedTuple):
    """`default_from` names the parameter whose value at the same key columns is the default."""

    default: float | None = None
    default_from: str | None = None
    is_inferred: bool = False


def map_metadata(
    inputs: MappingInputs, parameters: MappedParameters, recorder: EventRecorder
) -> dict[str, pl.LazyFrame]:
    defaults = _choose_defaults(inputs.schema, parameters)
    _record_inferred_defaults(inputs.schema, defaults, recorder)
    return {
        MetadataTable.DEFAULTS: _build_defaults_table(defaults, parameters).lazy(),
        MetadataTable.UNITS: _build_units_table(inputs.mappings.units).lazy(),
        MetadataTable.SCHEMA: _build_schema_table(inputs.schema).lazy(),
    }


def _choose_defaults(
    schema: CanonicalSchema, parameters: MappedParameters
) -> dict[str, CanonicalDefault]:
    return {
        name: _choose_default(entry, parameters.parameter_defaults.get(name))
        for name, entry in schema.parameters.items()
    }


def _choose_default(entry: CanonicalParameter, declared: float | None) -> CanonicalDefault:
    if declared is not None:
        return CanonicalDefault(declared)
    if entry.default is not None:
        return CanonicalDefault(entry.default, is_inferred=True)
    return CanonicalDefault(
        default_from=entry.default_from, is_inferred=entry.default_from is not None
    )


def _record_inferred_defaults(
    schema: CanonicalSchema, defaults: dict[str, CanonicalDefault], recorder: EventRecorder
) -> None:
    for name, found in defaults.items():
        if found.is_inferred:
            names = TableNames(schema.parameters[name].osemosys_name, name)
            record_default_applied(recorder, _build_applied_default(names, found))


def _build_applied_default(names: TableNames, found: CanonicalDefault) -> AppliedDefault:
    if found.default_from is None:
        return AppliedDefault(names, MetadataColumn.DEFAULT, found.default, _SCHEMA_DEFAULT_NOTE)
    note = _DEFAULT_FROM_NOTE.format(source=found.default_from)
    return AppliedDefault(names, MetadataColumn.DEFAULT_FROM, found.default_from, note)


def _build_defaults_table(
    defaults: dict[str, CanonicalDefault], parameters: MappedParameters
) -> pl.DataFrame:
    extensions = {
        name: CanonicalDefault(default) for name, default in parameters.extension_defaults.items()
    }
    rows = [
        *_build_default_rows(TableKind.PARAMETER, defaults),
        *_build_default_rows(TableKind.EXTENSION, extensions),
    ]
    return pl.DataFrame(rows, schema=_DEFAULTS_SCHEMA)


def _build_default_rows(
    kind: TableKind, defaults: dict[str, CanonicalDefault]
) -> list[dict[str, object]]:
    return [
        {
            MetadataColumn.KIND: kind,
            MetadataColumn.PARAMETER: name,
            MetadataColumn.DEFAULT: found.default,
            MetadataColumn.DEFAULT_FROM: found.default_from,
        }
        for name, found in defaults.items()
    ]


def _build_units_table(units: Units) -> pl.DataFrame:
    rows = [
        {MetadataColumn.QUANTITY: quantity, MetadataColumn.UNIT: str(unit)}
        for quantity, unit in units.model_dump(exclude_none=True).items()
    ]
    return pl.DataFrame(rows, schema=_UNITS_SCHEMA)


def _build_schema_table(schema: CanonicalSchema) -> pl.DataFrame:
    row = {MetadataColumn.SCHEMA_VERSION: schema.schema_version}
    return pl.DataFrame([row], schema=_SCHEMA_VERSION_SCHEMA)
