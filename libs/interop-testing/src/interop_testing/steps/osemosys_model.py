from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import polars as pl
import yaml
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
_PARQUET_GLOB = "**/*.parquet"
_CONFIG_TYPE_KEY = "type"
_CONFIG_INDICES_KEY = "indices"
_CONFIG_DTYPE_KEY = "dtype"
_CONFIG_DEFAULT_KEY = "default"
_PARAM_TYPE = "param"
_SET_TYPE = "set"
_FLOAT_DTYPE = "float"
_STRING_DTYPE = "str"
# A sum over many rows of a share of a year carries the rounding of each row.
_SUM_TOLERANCE = 1e-9


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


@given(
    parsers.parse('the otoole parameter "{name}" keyed by "{key}" with no default has the rows:')
)
def given_otoole_parameter_rows_without_default(
    otoole_model_builder: OtooleModelBuilder, name: str, key: str, datatable: list[list[str]]
) -> None:
    header, *rows = datatable
    columns = [*key.split(), VALUE_COLUMN]
    assert header == columns, f"the table of {name} must have the header {columns}, not {header}"
    otoole_model_builder.set_parameter(name, key.split(), None, rows)


@given(parsers.parse('the otoole parameter "{name}" is not declared'))
def given_otoole_parameter_undeclared(otoole_model_builder: OtooleModelBuilder, name: str) -> None:
    otoole_model_builder.drop_parameter(name)


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


@then(parsers.parse('the otoole CSV file "{path}" has the rows:'))
def assert_otoole_csv_rows(path: str, datatable: list[list[str]]) -> None:
    """Compare the rows in any order. A whole number has no decimal point, as the canonical
    table assertion writes one."""
    expected_header, *expected_rows = datatable
    header, *rows = _read_csv_rows(Path(path))
    assert header == expected_header, f"expected the header {expected_header} in {path}"
    actual = [[_format_csv_cell(cell) for cell in row] for row in rows]
    assert sorted(actual) == sorted(expected_rows), (
        f"expected rows {expected_rows} in {path}, got {actual}"
    )


@then(parsers.parse('the otoole CSV file "{path}" has {count:d} rows'))
def assert_otoole_csv_row_count(path: str, count: int) -> None:
    _header, *rows = _read_csv_rows(Path(path))
    assert len(rows) == count, f"expected {count} rows in {path}, got {len(rows)}"


@then(
    parsers.parse(
        'the otoole CSV file "{path}" sums the VALUE column to {expected:g} for each "{column}"'
    )
)
def assert_otoole_csv_sum_by_column(path: str, expected: float, column: str) -> None:
    """One total for each value of `column`, so a parameter keyed by the year is checked per
    year."""
    totals = _build_sums_by_column(Path(path), column)
    assert totals, f"expected {path} to hold rows keyed by {column}"
    for key, total in sorted(totals.items()):
        assert math.isclose(total, expected, rel_tol=_SUM_TOLERANCE), (
            f"expected the VALUE column of {path} to sum to {expected} at {column} {key}, "
            f"got {total}"
        )


def _build_sums_by_column(path: Path, column: str) -> dict[str, float]:
    header, *rows = _read_csv_rows(path)
    assert column in header, f"expected the column {column} in {path}, got {header}"
    key_index = header.index(column)
    value_index = header.index(VALUE_COLUMN)
    totals: dict[str, float] = {}
    for row in rows:
        totals[row[key_index]] = totals.get(row[key_index], 0.0) + float(row[value_index])
    return totals


@then(
    parsers.parse(
        'the otoole config "{path}" declares the parameter "{name}" '
        'indexed by "{indices}" with default {expected:g}'
    )
)
def assert_otoole_config_parameter(path: str, name: str, indices: str, expected: float) -> None:
    entry = _read_config_entry(Path(path), name)
    assert entry[_CONFIG_TYPE_KEY] == _PARAM_TYPE, f"expected {name} to be a {_PARAM_TYPE}"
    assert entry[_CONFIG_INDICES_KEY] == indices.split(), f"expected {name} indexed by {indices}"
    assert entry[_CONFIG_DTYPE_KEY] == _FLOAT_DTYPE, f"expected {name} to be a {_FLOAT_DTYPE}"
    assert entry[_CONFIG_DEFAULT_KEY] == expected, (
        f"expected the default of {name} to be {expected}"
    )


@then(parsers.parse('the otoole config "{path}" declares the set "{name}"'))
def assert_otoole_config_set(path: str, name: str) -> None:
    entry = _read_config_entry(Path(path), name)
    assert entry[_CONFIG_TYPE_KEY] == _SET_TYPE, f"expected {name} to be a {_SET_TYPE}"
    assert entry[_CONFIG_DTYPE_KEY] == _STRING_DTYPE, f"expected {name} to be a {_STRING_DTYPE}"


@then(parsers.parse('the canonical stage "{actual}" holds the same tables as "{expected}"'))
def assert_canonical_stage_matches(actual: str, expected: str) -> None:
    actual_tables = _list_stage_tables(Path(actual))
    expected_tables = _list_stage_tables(Path(expected))
    assert sorted(actual_tables) == sorted(expected_tables), (
        f"{actual} holds the tables {sorted(actual_tables)}, not {sorted(expected_tables)}"
    )
    for name in sorted(expected_tables):
        _assert_table_matches(name, actual_tables[name], expected_tables[name])


def _list_stage_tables(directory: Path) -> dict[str, Path]:
    assert directory.is_dir(), f"the canonical stage {directory} is not a directory"
    return {
        str(path.relative_to(directory)): path for path in sorted(directory.glob(_PARQUET_GLOB))
    }


def _assert_table_matches(name: str, actual_path: Path, expected_path: Path) -> None:
    actual = pl.read_parquet(actual_path)
    expected = pl.read_parquet(expected_path)
    assert actual.columns == expected.columns, (
        f"{name} holds the columns {actual.columns}, not {expected.columns}"
    )
    assert sorted(actual.rows()) == sorted(expected.rows()), (
        f"{name} holds the rows {actual.rows()}, not {expected.rows()}"
    )


def _read_config_entry(path: Path, name: str) -> dict[str, object]:
    entries = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert name in entries, f"the config {path} declares {sorted(entries)}, not {name}"
    entry: dict[str, object] = entries[name]
    return entry


def _read_csv_rows(path: Path) -> list[list[str]]:
    assert path.is_file(), f"the CSV file {path} does not exist"
    with path.open(encoding="utf-8", newline="") as stream:
        return [row for row in csv.reader(stream) if row]


def _format_csv_cell(cell: str) -> str:
    """A number that otoole writes as `1.0` reads as the whole number `1`."""
    try:
        return _format_number(float(cell))
    except ValueError:
        return cell
