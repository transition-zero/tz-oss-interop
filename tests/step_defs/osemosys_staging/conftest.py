from __future__ import annotations

from pathlib import Path

from interop_testing import run_pipeline
from interop_testing.builders.otoole_models import OtooleModelBuilder
from interop_testing.builders.tz_osemosys_models import TzOsemosysModelBuilder
from pytest_bdd import parsers, when

_USER_MAPPINGS_PATH = "user_mappings.yaml"
_OTOOLE_PIPELINE = "osemosys-csv-to-canonical"
_OTOOLE_CONFIG_PATH = "model/config.yaml"
_OTOOLE_CSV_DIRECTORY = "model/csv"
_TZ_PIPELINE = "tz-osemosys-to-canonical"
_TZ_MODEL_PATH = "model/model.json"
_OUTPUT_OVERRIDE = "sink[0].output_dir={output_dir}"


@when(
    parsers.parse('I stage the otoole model into "{output_dir}"'),
    target_fixture="pipeline_exit_code",
)
def stage_the_otoole_model(otoole_model_builder: OtooleModelBuilder, output_dir: str) -> int:
    """Write the model to `model/config.yaml` and `model/csv`, then stage it with
    `user_mappings.yaml`."""
    otoole_model_builder.write(Path(_OTOOLE_CONFIG_PATH), Path(_OTOOLE_CSV_DIRECTORY))
    overrides = [
        f"source.config_path={_OTOOLE_CONFIG_PATH}",
        f"source.csv_dir={_OTOOLE_CSV_DIRECTORY}",
        _OUTPUT_OVERRIDE.format(output_dir=output_dir),
    ]
    return run_pipeline(
        _OTOOLE_PIPELINE, overrides=overrides, user_mappings_path=_USER_MAPPINGS_PATH
    )


@when(
    parsers.parse('I stage the TZ-format model into "{output_dir}"'),
    target_fixture="pipeline_exit_code",
)
def stage_the_tz_model(tz_model_builder: TzOsemosysModelBuilder, output_dir: str) -> int:
    """Write the model to `model/model.json`, then stage it with `user_mappings.yaml`."""
    tz_model_builder.write(Path(_TZ_MODEL_PATH))
    overrides = [
        f"source.model_json_path={_TZ_MODEL_PATH}",
        _OUTPUT_OVERRIDE.format(output_dir=output_dir),
    ]
    return run_pipeline(_TZ_PIPELINE, overrides=overrides, user_mappings_path=_USER_MAPPINGS_PATH)
