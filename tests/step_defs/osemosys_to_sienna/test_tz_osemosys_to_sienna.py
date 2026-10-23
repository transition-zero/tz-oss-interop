from __future__ import annotations

from pathlib import Path

from interop_testing import run_pipeline
from interop_testing.builders.tz_osemosys_models import TzOsemosysModelBuilder
from pytest_bdd import parsers, scenarios, when

scenarios("osemosys_to_sienna/tz_osemosys_to_sienna.feature")

_PIPELINE = "tz-osemosys-to-sienna"
_USER_MAPPINGS_PATH = "user_mappings.yaml"
_MODEL_PATH = "model/model.json"


@when(
    parsers.parse('I translate the TZ-format model to Sienna for the year "{year}"'),
    target_fixture="pipeline_exit_code",
)
def translate_the_tz_model(tz_model_builder: TzOsemosysModelBuilder, year: str) -> int:
    """Write the model to `model/model.json`, then translate it with `user_mappings.yaml`."""
    tz_model_builder.write(Path(_MODEL_PATH))
    overrides = [f"source.model_json_path={_MODEL_PATH}", f"step[1].year={year}"]
    return run_pipeline(_PIPELINE, overrides=overrides, user_mappings_path=_USER_MAPPINGS_PATH)
