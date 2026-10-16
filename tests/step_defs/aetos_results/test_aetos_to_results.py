from __future__ import annotations

from pathlib import Path

from interop_testing import YearlyResultsCsvBuilder, run_pipeline
from pytest_bdd import parsers, scenarios, when

scenarios("aetos_results/aetos_to_results.feature")

_PIPELINE = "aetos-to-results"
_USER_MAPPINGS_PATH = "user_mappings.yaml"
_RESULTS_CSV_PATH = "results/results.csv"


@when(
    parsers.parse('I read the results CSV through aetos-to-results from the year "{first_year}"'),
    target_fixture="pipeline_exit_code",
)
def read_the_results_csv(yearly_results_builder: YearlyResultsCsvBuilder, first_year: str) -> int:
    """Write the CSV to `results/results.csv`, then read it with the model in `model/`."""
    yearly_results_builder.write(Path(_RESULTS_CSV_PATH))
    overrides = [
        "source.config_path=model/config.yaml",
        "source.csv_dir=model/csv",
        f"source.results_csv_path={_RESULTS_CSV_PATH}",
        f"source.first_year={first_year}",
    ]
    return run_pipeline(_PIPELINE, overrides=overrides, user_mappings_path=_USER_MAPPINGS_PATH)
