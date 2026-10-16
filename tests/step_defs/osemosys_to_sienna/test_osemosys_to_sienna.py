from __future__ import annotations

from pathlib import Path

from interop_testing import run_pipeline, write_pipeline, write_project_plugin
from interop_testing.builders.otoole_models import OtooleModelBuilder
from pytest_bdd import given, parsers, scenarios, when

scenarios("osemosys_to_sienna/osemosys_to_sienna.feature")

_PIPELINE = "osemosys-csv-to-sienna"
_USER_MAPPINGS_PATH = "user_mappings.yaml"
_CONFIG_PATH = "model/config.yaml"
_CSV_DIRECTORY = "model/csv"

_MOVE_BRACKET_STEP_PY = """\
from typing import ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep

_KEY = ("parameter", "timeslice_in_daily_time_bracket")
_BRACKET = "daily_time_bracket"


class _MoveBracket(TranslationStep):
    name: ClassVar[str] = "move_bracket"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def run(self, state: State, params: BaseModel | None) -> State:
        moved = pl.when(pl.col("timeslice") == {timeslice!r}).then(pl.lit({bracket!r}))
        state.source_time_series[_KEY] = state.source_time_series[_KEY].with_columns(
            moved.otherwise(pl.col(_BRACKET)).alias(_BRACKET)
        )
        return state
"""

_MOVE_BRACKET_PIPELINE_YAML = """\
source_framework: osemosys
destination_framework: sienna
source:
  name: stage_osemosys_csv
  params:
    config_path: model/config.yaml
    csv_dir: model/csv
steps:
  - name: move_bracket
  - name: osemosys_to_sienna_map_components
    params:
      year: 2030
  - name: sienna_relate_components
sinks:
  - name: emit_sienna_files
"""


@given(
    parsers.parse(
        'a pipeline "{name}" that puts the timeslice "{timeslice}" in the daily time bracket '
        '"{bracket}" before the translation'
    )
)
def given_move_bracket_pipeline(name: str, timeslice: str, bracket: str) -> None:
    """A project step changes the canonical stage, as a stage that no source wrote could be."""
    source = _MOVE_BRACKET_STEP_PY.format(timeslice=timeslice, bracket=bracket)
    write_project_plugin("steps", "move_bracket", source)
    write_pipeline(name, _MOVE_BRACKET_PIPELINE_YAML)


@when(
    parsers.parse('I translate the otoole model to Sienna for the year "{year}"'),
    target_fixture="pipeline_exit_code",
)
def translate_the_otoole_model(otoole_model_builder: OtooleModelBuilder, year: str) -> int:
    """Write the model to `model/config.yaml` and `model/csv`, then translate it with
    `user_mappings.yaml`."""
    otoole_model_builder.write(Path(_CONFIG_PATH), Path(_CSV_DIRECTORY))
    overrides = [
        f"source.config_path={_CONFIG_PATH}",
        f"source.csv_dir={_CSV_DIRECTORY}",
        f"step[0].year={year}",
    ]
    return run_pipeline(_PIPELINE, overrides=overrides, user_mappings_path=_USER_MAPPINGS_PATH)


@when(
    parsers.parse('I run the otoole model through the pipeline "{pipeline}"'),
    target_fixture="pipeline_exit_code",
)
def run_the_otoole_model(otoole_model_builder: OtooleModelBuilder, pipeline: str) -> int:
    otoole_model_builder.write(Path(_CONFIG_PATH), Path(_CSV_DIRECTORY))
    return run_pipeline(pipeline, user_mappings_path=_USER_MAPPINGS_PATH)
