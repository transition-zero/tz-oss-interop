from pathlib import Path

from pytest_bdd import given, parsers, scenarios

scenarios("power_systems_investments_results/power_systems_investments_to_results.feature")


@given(parsers.parse('an empty results directory "{path}"'))
def given_empty_results_directory(path: str) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)


@given(parsers.parse('a results directory "{path}" that holds only the file "{name}"'))
def given_results_directory_with_one_file(path: str, name: str) -> None:
    file = Path(path) / name
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text("solve_time\n1.0\n", encoding="utf-8")
