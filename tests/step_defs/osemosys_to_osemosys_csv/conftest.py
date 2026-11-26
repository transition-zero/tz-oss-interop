from __future__ import annotations

from pathlib import Path

import pytest
from interop_testing import run_pipeline
from interop_testing.builders.otoole_models import OtooleModelBuilder
from interop_testing.builders.tz_osemosys_models import TzOsemosysModelBuilder
from pytest_bdd import parsers, when

from tests.step_defs.conftest import invoke_translate_cancel_at_destination

_USER_MAPPINGS_PATH = "user_mappings.yaml"
_OTOOLE_PIPELINE = "osemosys-csv-to-osemosys-csv"
_TZ_PIPELINE = "tz-osemosys-to-osemosys-csv"
_OTOOLE_CONFIG_PATH = "model/config.yaml"
_OTOOLE_CSV_DIRECTORY = "model/csv"
_TZ_MODEL_PATH = "model/model.json"
_MAPPINGS_OUTPUT_PATH = "outputs/osemosys_mappings.yaml"
_EVERY_PARAMETER_OVERRIDE = "sink[0].wants_every_parameter=true"


@when(parsers.parse('I start translate from the source framework "{framework}"'))
def start_translate_from_source(monkeypatch: pytest.MonkeyPatch, framework: str) -> None:
    invoke_translate_cancel_at_destination(monkeypatch, framework)


@when(
    parsers.parse('I write the otoole model back out to "{output_dir}"'),
    target_fixture="pipeline_exit_code",
)
def write_the_otoole_model_back(otoole_model_builder: OtooleModelBuilder, output_dir: str) -> int:
    return _run_otoole_pipeline(otoole_model_builder, output_dir, [])


@when(
    parsers.parse('I write the otoole model back out to "{output_dir}" asking for every parameter'),
    target_fixture="pipeline_exit_code",
)
def write_the_otoole_model_back_in_full(
    otoole_model_builder: OtooleModelBuilder, output_dir: str
) -> int:
    return _run_otoole_pipeline(otoole_model_builder, output_dir, [_EVERY_PARAMETER_OVERRIDE])


def _run_otoole_pipeline(
    builder: OtooleModelBuilder, output_dir: str, extra_overrides: list[str]
) -> int:
    """Write the model to `model/`, then read it back out into `output_dir`."""
    builder.write(Path(_OTOOLE_CONFIG_PATH), Path(_OTOOLE_CSV_DIRECTORY))
    overrides = [
        f"source.config_path={_OTOOLE_CONFIG_PATH}",
        f"source.csv_dir={_OTOOLE_CSV_DIRECTORY}",
        *_build_output_overrides(output_dir),
        *extra_overrides,
    ]
    return run_pipeline(
        _OTOOLE_PIPELINE, overrides=overrides, user_mappings_path=_USER_MAPPINGS_PATH
    )


@when(
    parsers.parse('I write the TZ-format model out as an otoole model in "{output_dir}"'),
    target_fixture="pipeline_exit_code",
)
def write_the_tz_model_out(tz_model_builder: TzOsemosysModelBuilder, output_dir: str) -> int:
    tz_model_builder.write(Path(_TZ_MODEL_PATH))
    overrides = [
        f"source.model_json_path={_TZ_MODEL_PATH}",
        *_build_output_overrides(output_dir),
    ]
    return run_pipeline(_TZ_PIPELINE, overrides=overrides, user_mappings_path=_USER_MAPPINGS_PATH)


def _build_output_overrides(output_dir: str) -> list[str]:
    return [
        f"sink[0].output_config_path={output_dir}/config.yaml",
        f"sink[0].output_csv_dir={output_dir}/csv",
        f"sink[0].output_mappings_path={_MAPPINGS_OUTPUT_PATH}",
    ]
