from __future__ import annotations

from pathlib import Path

from interop_testing import run_pipeline
from interop_testing.builders.otoole_models import OtooleModelBuilder
from pytest_bdd import scenarios, when

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
