from __future__ import annotations

import json
from pathlib import Path

import polars as pl
from pytest_bdd import given, parsers, then

from interop_testing.builders.otoole_models import VALUE_COLUMN, OtooleModelBuilder
from interop_testing.builders.tz_osemosys_models import TzOsemosysModelBuilder

_DEFAULTS_TABLE = Path("metadata") / "defaults.parquet"
_KIND_COLUMN = "kind"
_PARAMETER_COLUMN = "parameter"
_PARAMETER_KIND = "parameter"
_EXTENSION_KIND = "extension"
_DEFAULT_COLUMN = "default"
_EMPTY_STRING_CELL = '""'


@given("an otoole model", target_fixture="otoole_model_builder")
def given_otoole_model() -> OtooleModelBuilder:
    return OtooleModelBuilder()


@given(parsers.parse('the otoole set "{name}" holds "{members}"'))
def given_otoole_set(otoole_model_builder: OtooleModelBuilder, name: str, members: str) -> None:
    otoole_model_builder.set_members(name, members.split())


@given(parsers.parse('the otoole set "{name}" is declared with no file'))
def given_otoole_set_without_file(otoole_model_builder: OtooleModelBuilder, name: str) -> None:
    otoole_model_builder.set_members(name, [], has_file=False)


@given(parsers.parse('the otoole set "{name}" file pads each member with spaces'))
def given_otoole_set_padding(otoole_model_builder: OtooleModelBuilder, name: str) -> None:
    otoole_model_builder.set_member_padding(name)


@given(
    parsers.parse(
        'the otoole parameter "{name}" keyed by "{key}" with default {default:g} has the rows:'
    )
)
def given_otoole_parameter_rows(
    otoole_model_builder: OtooleModelBuilder,
    name: str,
    key: str,
    default: float,
    datatable: list[list[str]],
) -> None:
    header, *rows = datatable
    columns = [*key.split(), VALUE_COLUMN]
    assert header == columns, f"the table of {name} must have the header {columns}, not {header}"
    otoole_model_builder.set_parameter(name, key.split(), default, rows)


@given(
    parsers.parse(
        'the otoole parameter "{name}" keyed by "{key}" with default {default:g} has no file'
    )
)
def given_otoole_parameter_without_file(
    otoole_model_builder: OtooleModelBuilder, name: str, key: str, default: float
) -> None:
    otoole_model_builder.set_parameter(name, key.split(), default, [], has_file=False)


@given(parsers.parse('the otoole parameter "{name}" has the short name "{short_name}"'))
def given_otoole_short_name(
    otoole_model_builder: OtooleModelBuilder, name: str, short_name: str
) -> None:
    otoole_model_builder.set_short_name(name, short_name)


@given(parsers.parse('the otoole parameter "{name}" file has the header "{columns}"'))
def given_otoole_file_header(
    otoole_model_builder: OtooleModelBuilder, name: str, columns: str
) -> None:
    otoole_model_builder.set_header(name, columns.split())


@given(parsers.parse('the otoole result "{name}" keyed by "{key}"'))
def given_otoole_result(otoole_model_builder: OtooleModelBuilder, name: str, key: str) -> None:
    otoole_model_builder.set_result(name, key.split())


@given(
    parsers.parse('the otoole model is written to config "{config_path}" and directory "{csv_dir}"')
)
def given_otoole_model_written(
    otoole_model_builder: OtooleModelBuilder, config_path: str, csv_dir: str
) -> None:
    otoole_model_builder.write(Path(config_path), Path(csv_dir))


@given("a TZ-format model", target_fixture="tz_model_builder")
def given_tz_model() -> TzOsemosysModelBuilder:
    return TzOsemosysModelBuilder()


@given(parsers.parse('the TZ-format model has the regions "{region_ids}"'))
def given_tz_regions(tz_model_builder: TzOsemosysModelBuilder, region_ids: str) -> None:
    for region_id in region_ids.split():
        tz_model_builder.add_region(region_id)


@given(parsers.parse('the TZ-format model has the years "{years}"'))
def given_tz_years(tz_model_builder: TzOsemosysModelBuilder, years: str) -> None:
    tz_model_builder.add_years([int(year) for year in years.split()])


@given(parsers.parse('the TZ-format model has the timeslices "{timeslices}"'))
def given_tz_timeslices(tz_model_builder: TzOsemosysModelBuilder, timeslices: str) -> None:
    tz_model_builder.add_timeslices(timeslices.split())


@given(parsers.parse('the TZ-format model has the commodities "{commodity_ids}"'))
def given_tz_commodities(tz_model_builder: TzOsemosysModelBuilder, commodity_ids: str) -> None:
    for commodity_id in commodity_ids.split():
        tz_model_builder.set_commodity(commodity_id)


@given(parsers.parse('the TZ-format model has the field "{name}" set to {value}'))
def given_tz_model_field(tz_model_builder: TzOsemosysModelBuilder, name: str, value: str) -> None:
    tz_model_builder.set_model_field(name, json.loads(value))


@given(parsers.parse('the TZ-format time definition has the field "{name}" set to {value}'))
def given_tz_time_field(tz_model_builder: TzOsemosysModelBuilder, name: str, value: str) -> None:
    tz_model_builder.set_time_field(name, json.loads(value))


@given(parsers.parse('the TZ-format commodity "{object_id}" has the field "{name}" set to {value}'))
def given_tz_commodity_field(
    tz_model_builder: TzOsemosysModelBuilder, object_id: str, name: str, value: str
) -> None:
    tz_model_builder.set_commodity(object_id, **{name: json.loads(value)})


@given(
    parsers.parse('the TZ-format technology "{object_id}" has the field "{name}" set to {value}')
)
def given_tz_technology_field(
    tz_model_builder: TzOsemosysModelBuilder, object_id: str, name: str, value: str
) -> None:
    tz_model_builder.set_technology(object_id, **{name: json.loads(value)})


@given(parsers.parse('the TZ-format storage "{object_id}" has the field "{name}" set to {value}'))
def given_tz_storage_field(
    tz_model_builder: TzOsemosysModelBuilder, object_id: str, name: str, value: str
) -> None:
    tz_model_builder.set_storage(object_id, **{name: json.loads(value)})


@given(
    parsers.parse(
        'the TZ-format trade "{object_id}" of the commodity "{commodity}" '
        'has the field "{name}" set to {value}'
    )
)
def given_tz_trade_field(
    tz_model_builder: TzOsemosysModelBuilder, object_id: str, commodity: str, name: str, value: str
) -> None:
    tz_model_builder.set_trade(object_id, commodity, **{name: json.loads(value)})


@given(parsers.parse('the TZ-format model is written to "{path}"'))
def given_tz_model_written(tz_model_builder: TzOsemosysModelBuilder, path: str) -> None:
    tz_model_builder.write(Path(path))


@then(parsers.parse('the canonical table "{path}" has the rows:'))
def assert_canonical_rows(path: str, datatable: list[list[str]]) -> None:
    """Compare the rows in any order. A whole number has no decimal point, an empty cell is a null,
    and `""` is an empty string."""
    expected_header, *expected_rows = datatable
    table = pl.read_parquet(Path(path))
    assert table.columns == expected_header, f"expected columns {expected_header} in {path}"
    actual_rows = [[_format_cell(cell) for cell in row] for row in table.rows()]
    assert sorted(actual_rows) == sorted(expected_rows), (
        f"expected rows {expected_rows} in {path}, got {actual_rows}"
    )


@then(parsers.parse('the column "{column}" of the canonical table "{path}" has the type "{dtype}"'))
def assert_canonical_column_type(column: str, path: str, dtype: str) -> None:
    actual = pl.read_parquet(Path(path)).schema[column]
    assert str(actual) == dtype, f"expected {column} in {path} to be {dtype}, got {actual}"


@then(parsers.parse('the canonical default of "{parameter}" in "{directory}" is {expected:g}'))
def assert_canonical_default(parameter: str, directory: str, expected: float) -> None:
    actual = _read_default(Path(directory), _PARAMETER_KIND, parameter)
    assert actual == expected, f"expected the default of {parameter} to be {expected}, got {actual}"


@then(
    parsers.parse(
        'the canonical default of extension "{extension}" in "{directory}" is {expected:g}'
    )
)
def assert_extension_default(extension: str, directory: str, expected: float) -> None:
    actual = _read_default(Path(directory), _EXTENSION_KIND, extension)
    assert actual == expected, f"expected the default of {extension} to be {expected}, got {actual}"


def _read_default(directory: Path, kind: str, name: str) -> object:
    defaults = pl.read_parquet(directory / _DEFAULTS_TABLE)
    matching = defaults.filter((pl.col(_KIND_COLUMN) == kind) & (pl.col(_PARAMETER_COLUMN) == name))
    assert matching.height == 1, f"expected one {kind} default for {name}, got {matching.height}"
    return matching.item(0, _DEFAULT_COLUMN)


def _format_cell(cell: object) -> str:
    if cell is None:
        return ""
    if cell == "":
        return _EMPTY_STRING_CELL
    return _format_number(cell) if isinstance(cell, float) else str(cell)


def _format_number(number: float) -> str:
    return str(int(number)) if number.is_integer() else repr(number)
