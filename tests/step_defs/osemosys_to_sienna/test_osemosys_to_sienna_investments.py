from __future__ import annotations

from pathlib import Path

from interop_testing import run_pipeline
from interop_testing.builders.otoole_models import OtooleModelBuilder
from pytest_bdd import parsers, scenarios, when

scenarios("osemosys_to_sienna/osemosys_to_sienna_investments.feature")

_PIPELINE = "osemosys-csv-to-sienna-investments"
_USER_MAPPINGS_PATH = "user_mappings.yaml"
_CONFIG_PATH = "model/config.yaml"
_CSV_DIRECTORY = "model/csv"


@when(
    "I translate the otoole model to a Sienna investments portfolio",
    target_fixture="pipeline_exit_code",
)
def translate_the_otoole_model(otoole_model_builder: OtooleModelBuilder) -> int:
    """Write the model to `model/config.yaml` and `model/csv`, then translate it with
    `user_mappings.yaml`."""
    otoole_model_builder.write(Path(_CONFIG_PATH), Path(_CSV_DIRECTORY))
    overrides = [f"source.config_path={_CONFIG_PATH}", f"source.csv_dir={_CSV_DIRECTORY}"]
    return run_pipeline(_PIPELINE, overrides=overrides, user_mappings_path=_USER_MAPPINGS_PATH)


@when(
    parsers.parse(
        "I translate the otoole model to a Sienna investments portfolio, with only the system "
        'at "{system_path}" and the portfolio at "{portfolio_path}"'
    ),
    target_fixture="pipeline_exit_code",
)
def translate_the_otoole_model_to_paths(
    otoole_model_builder: OtooleModelBuilder, system_path: str, portfolio_path: str
) -> int:
    """Override the main output path of each sink, and no companion path."""
    otoole_model_builder.write(Path(_CONFIG_PATH), Path(_CSV_DIRECTORY))
    overrides = [
        f"source.config_path={_CONFIG_PATH}",
        f"source.csv_dir={_CSV_DIRECTORY}",
        f"sink[0].output_system_json_file_path={system_path}",
        f"sink[1].output_path={portfolio_path}",
    ]
    return run_pipeline(_PIPELINE, overrides=overrides, user_mappings_path=_USER_MAPPINGS_PATH)
