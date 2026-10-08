"""pytest-bdd vocabulary for an OSeMOSYS model and the canonical stage files that it stages into."""

from __future__ import annotations

from pathlib import Path

import polars as pl
from pytest_bdd import given, parsers, then

from interop_testing.builders.otoole_models import VALUE_COLUMN, OtooleModelBuilder

_DEFAULTS_TABLE = Path("metadata") / "defaults.parquet"
_PARAMETER_COLUMN = "parameter"
_DEFAULT_COLUMN = "default"


@given("an otoole model", target_fixture="otoole_model_builder")
def given_otoole_model() -> OtooleModelBuilder:
    return OtooleModelBuilder()


@given(parsers.parse('the otoole set "{name}" holds "{members}"'))
def given_otoole_set(otoole_model_builder: OtooleModelBuilder, name: str, members: str) -> None:
    otoole_model_builder.add_set(name, members.split())


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
    otoole_model_builder.add_parameter(name, key.split(), default, rows)


@given(
    parsers.parse(
        'the otoole parameter "{name}" keyed by "{key}" with default {default:g} has no file'
    )
)
def given_otoole_parameter_without_file(
    otoole_model_builder: OtooleModelBuilder, name: str, key: str, default: float
) -> None:
    otoole_model_builder.add_parameter(name, key.split(), default, [], has_file=False)


@given(
    parsers.parse('the otoole model is written to config "{config_path}" and directory "{csv_dir}"')
)
def given_otoole_model_written(
    otoole_model_builder: OtooleModelBuilder, config_path: str, csv_dir: str
) -> None:
    otoole_model_builder.write(Path(config_path), Path(csv_dir))


@then(parsers.parse('the canonical table "{path}" has the rows:'))
def assert_canonical_rows(path: str, datatable: list[list[str]]) -> None:
    """Compare the rows in any order, and each number in its shortest form."""
    expected_header, *expected_rows = datatable
    table = pl.read_parquet(Path(path))
    assert table.columns == expected_header, f"expected columns {expected_header} in {path}"
    actual_rows = [[_format_cell(cell) for cell in row] for row in table.rows()]
    assert sorted(actual_rows) == sorted(expected_rows), (
        f"expected rows {expected_rows} in {path}, got {actual_rows}"
    )


@then(parsers.parse('the canonical table "{path}" has {count:d} rows'))
def assert_canonical_row_count(path: str, count: int) -> None:
    height = pl.read_parquet(Path(path)).height
    assert height == count, f"expected {count} rows in {path}, got {height}"


@then(parsers.parse('the canonical table "{path}" has the columns "{columns}"'))
def assert_canonical_columns(path: str, columns: str) -> None:
    actual = pl.read_parquet(Path(path)).columns
    assert actual == columns.split(), f"expected columns {columns.split()} in {path}, got {actual}"


@then(parsers.parse('the column "{column}" of the canonical table "{path}" has the type "{dtype}"'))
def assert_canonical_column_type(column: str, path: str, dtype: str) -> None:
    actual = pl.read_parquet(Path(path)).schema[column]
    assert str(actual) == dtype, f"expected {column} in {path} to be {dtype}, got {actual}"


@then(parsers.parse('the canonical default of "{parameter}" in "{directory}" is {expected:g}'))
def assert_canonical_default(parameter: str, directory: str, expected: float) -> None:
    defaults = pl.read_parquet(Path(directory) / _DEFAULTS_TABLE)
    matching = defaults.filter(pl.col(_PARAMETER_COLUMN) == parameter)
    assert matching.height == 1, f"expected one default for {parameter}, got {matching.height}"
    actual = matching.item(0, _DEFAULT_COLUMN)
    assert actual == expected, f"expected the default of {parameter} to be {expected}, got {actual}"


def _format_cell(cell: object) -> str:
    return f"{cell:g}" if isinstance(cell, float) else str(cell)
