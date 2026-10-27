"""pytest-bdd Given steps for the output of a PowerSystemsInvestments.jl expansion solve.

``Given an expansion solve output in "<dir>"`` creates the ``expansion_solve_builder`` fixture,
``Given a series document "<path>"`` creates the ``series_document_builder`` fixture, and
``Given a portfolio "<path>"`` creates the ``portfolio_builder`` fixture.
"""

from __future__ import annotations

from pathlib import Path

from pytest_bdd import given, parsers

from interop_testing.builders.power_systems_investments_results import (
    ExpansionSolveBuilder,
    PortfolioBuilder,
    SeriesDocumentBuilder,
)


@given(
    parsers.parse('an expansion solve output in "{directory}"'),
    target_fixture="expansion_solve_builder",
)
def given_expansion_solve_output(directory: str) -> ExpansionSolveBuilder:
    return ExpansionSolveBuilder(Path(directory))


@given(parsers.parse('the expansion solve wrote the variable "{file_stem}" with the rows:'))
def given_expansion_variable(
    expansion_solve_builder: ExpansionSolveBuilder, file_stem: str, datatable: list[list[str]]
) -> None:
    expansion_solve_builder.add_variable(file_stem, datatable)


@given(parsers.parse('the expansion solve wrote the expression "{file_stem}" with the rows:'))
def given_expansion_expression(
    expansion_solve_builder: ExpansionSolveBuilder, file_stem: str, datatable: list[list[str]]
) -> None:
    expansion_solve_builder.add_expression(file_stem, datatable)


@given(parsers.parse("the expansion solve has the objective value {value:g}"))
def given_expansion_objective(expansion_solve_builder: ExpansionSolveBuilder, value: float) -> None:
    expansion_solve_builder.set_objective(value)


@given(
    parsers.parse('a series document "{path}" with one period for each of the years "{years}"'),
    target_fixture="series_document_builder",
)
def given_series_document(path: str, years: str) -> SeriesDocumentBuilder:
    builder = SeriesDocumentBuilder(Path(path))
    builder.set_periods([int(year) for year in years.split()])
    return builder


@given(
    parsers.parse(
        'the series document has the representative day {rep_day:d} of the year "{year}" from '
        '"{first_hour}" of {hours:d} hours with weight {weight:g}'
    )
)
def given_series_day(
    series_document_builder: SeriesDocumentBuilder,
    rep_day: int,
    year: str,
    first_hour: str,
    hours: int,
    weight: float,
) -> None:
    series_document_builder.add_day(year, rep_day, first_hour, hours, weight)


@given(parsers.parse('a portfolio "{path}"'), target_fixture="portfolio_builder")
def given_portfolio(path: str) -> PortfolioBuilder:
    return PortfolioBuilder(Path(path))


@given(
    parsers.parse(
        'the portfolio has the {component_type} "{name}" with the {unit_size_field} {size:g}'
    )
)
def given_portfolio_technology(
    portfolio_builder: PortfolioBuilder,
    component_type: str,
    name: str,
    unit_size_field: str,
    size: float,
) -> None:
    portfolio_builder.add_technology(component_type, name, unit_size_field, size)
