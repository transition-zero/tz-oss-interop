from __future__ import annotations

from pathlib import Path

from interop_testing import YearlyResultsCsvBuilder, run_pipeline
from interop_testing.builders.otoole_models import OtooleModelBuilder
from pytest_bdd import parsers, scenarios, when

scenarios("aetos_results/aetos_to_results.feature")

_PIPELINE = "aetos-to-results"
_USER_MAPPINGS_PATH = "user_mappings.yaml"
_RESULTS_CSV_PATH = "results/results.csv"
_CONFIG_PATH = "model/config.yaml"
_CSV_DIRECTORY = "model/csv"


@when(
    parsers.parse('I read the results CSV through aetos-to-results from the year "{first_year}"'),
    target_fixture="pipeline_exit_code",
)
def read_the_results_csv(
    otoole_model_builder: OtooleModelBuilder,
    yearly_results_builder: YearlyResultsCsvBuilder,
    first_year: str,
) -> int:
    """Write the model to `model/` and the CSV to `results/results.csv`, then read them."""
    otoole_model_builder.write(Path(_CONFIG_PATH), Path(_CSV_DIRECTORY))
    yearly_results_builder.write(Path(_RESULTS_CSV_PATH))
    overrides = [
        f"source.config_path={_CONFIG_PATH}",
        f"source.csv_dir={_CSV_DIRECTORY}",
        f"source.results_csv_path={_RESULTS_CSV_PATH}",
        f"source.first_year={first_year}",
    ]
    return run_pipeline(_PIPELINE, overrides=overrides, user_mappings_path=_USER_MAPPINGS_PATH)
