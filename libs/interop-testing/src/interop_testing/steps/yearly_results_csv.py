from __future__ import annotations

from pathlib import Path

from pytest_bdd import given, parsers

from interop_testing.builders.yearly_results_csv import YearlyResultsCsvBuilder


@given("a results CSV with one column for each year", target_fixture="yearly_results_builder")
def given_yearly_results_csv() -> YearlyResultsCsvBuilder:
    return YearlyResultsCsvBuilder()


@given(
    parsers.parse(
        'the results CSV has the row "{variable}" in "{region}" for "{index}" '
        'with the values "{values}"'
    )
)
def given_yearly_results_row(
    yearly_results_builder: YearlyResultsCsvBuilder,
    variable: str,
    region: str,
    index: str,
    values: str,
) -> None:
    yearly_results_builder.add_row(variable, region, index.split(), values.split())


@given(
    parsers.parse(
        'the results CSV has the row "{variable}" in "{region}" with no index '
        'and the values "{values}"'
    )
)
def given_yearly_results_row_without_index(
    yearly_results_builder: YearlyResultsCsvBuilder, variable: str, region: str, values: str
) -> None:
    yearly_results_builder.add_row(variable, region, [], values.split())


@given(parsers.parse('the results CSV has the row "{variable}" with the one value "{value}"'))
def given_yearly_results_scalar_row(
    yearly_results_builder: YearlyResultsCsvBuilder, variable: str, value: str
) -> None:
    yearly_results_builder.add_scalar_row(variable, value)


@given(parsers.parse('the results CSV is written to "{path}"'))
def given_yearly_results_written(
    yearly_results_builder: YearlyResultsCsvBuilder, path: str
) -> None:
    yearly_results_builder.write(Path(path))
