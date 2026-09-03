"""pytest-bdd Given steps for building a Sienna solve-results fixture.

Every step operates on the ``sienna_results_builder`` fixture that ``Given Sienna
solve results`` creates.
"""

from __future__ import annotations

from pathlib import Path

from pytest_bdd import given, parsers

from interop_testing.builders.sienna_results import SiennaResultsBuilder


def _series(values: str) -> list[float]:
    return [float(v) for v in values.split()]


@given("Sienna solve results", target_fixture="sienna_results_builder")
def given_sienna_solve_results() -> SiennaResultsBuilder:
    return SiennaResultsBuilder()


@given(parsers.parse("the results cover snapshots {snapshots}"))
def given_results_snapshots(sienna_results_builder: SiennaResultsBuilder, snapshots: str) -> None:
    sienna_results_builder.set_snapshots(snapshots.split())


@given(parsers.parse('the results have ThermalStandard dispatch for "{component}" of {values}'))
def given_thermal_dispatch(
    sienna_results_builder: SiennaResultsBuilder, component: str, values: str
) -> None:
    sienna_results_builder.add_thermal_dispatch(component, _series(values))


@given(parsers.parse('the results have HydroDispatch dispatch for "{component}" of {values}'))
def given_hydro_dispatch(
    sienna_results_builder: SiennaResultsBuilder, component: str, values: str
) -> None:
    sienna_results_builder.add_hydro_dispatch(component, _series(values))


@given(
    parsers.parse('the results have EnergyReservoirStorage output for "{component}" of {values}')
)
def given_storage_output(
    sienna_results_builder: SiennaResultsBuilder, component: str, values: str
) -> None:
    sienna_results_builder.add_storage_output(component, _series(values))


@given(parsers.parse('the results have EnergyReservoirStorage input for "{component}" of {values}'))
def given_storage_input(
    sienna_results_builder: SiennaResultsBuilder, component: str, values: str
) -> None:
    sienna_results_builder.add_storage_input(component, _series(values))


@given(parsers.parse('the results have Line flow for "{component}" of {values}'))
def given_line_flow(
    sienna_results_builder: SiennaResultsBuilder, component: str, values: str
) -> None:
    sienna_results_builder.add_line_flow(component, _series(values))


@given(parsers.parse('the results have HVDC flow for "{component}" of {values}'))
def given_link_flow(
    sienna_results_builder: SiennaResultsBuilder, component: str, values: str
) -> None:
    sienna_results_builder.add_link_flow(component, _series(values))


@given(parsers.parse('the results have PowerLoad demand for "{component}" of {values}'))
def given_load(sienna_results_builder: SiennaResultsBuilder, component: str, values: str) -> None:
    sienna_results_builder.add_load(component, _series(values))


@given(parsers.parse("the results objective is {value:g}"))
def given_objective(sienna_results_builder: SiennaResultsBuilder, value: float) -> None:
    sienna_results_builder.set_objective(value)


@given(parsers.parse('the results are saved in "{results_dir}"'))
def given_results_saved(sienna_results_builder: SiennaResultsBuilder, results_dir: str) -> None:
    sienna_results_builder.save(Path(results_dir))
