from pathlib import Path

from pytest_bdd import given, parsers, scenarios

scenarios("power_systems_investments_results/power_systems_investments_to_results.feature")


@given(parsers.parse('an empty results directory "{path}"'))
def given_empty_results_directory(path: str) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)
