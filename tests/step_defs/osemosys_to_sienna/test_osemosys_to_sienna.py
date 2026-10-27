from __future__ import annotations

from pathlib import Path

import pytest
from interop_testing import run_pipeline, write_pipeline, write_project_plugin
from interop_testing.builders.otoole_models import OtooleModelBuilder
from pytest_bdd import given, parsers, scenarios, when

from tests.step_defs.conftest import invoke_translate

scenarios(
    "osemosys_to_sienna/calendar.feature",
    "osemosys_to_sienna/buses_and_loads.feature",
    "osemosys_to_sienna/operations_year.feature",
)

_PIPELINE = "osemosys-csv-to-sienna"
_SOURCE_FRAMEWORK = "osemosys"
_DESTINATION_FRAMEWORK = "sienna"
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

_SCOPED_PIPELINE_YAML = """\
source_framework: osemosys
destination_framework: sienna
source:
  name: stage_osemosys_csv
steps:
  - name: osemosys_canonical_drop_outside_scope
    params:
      locations: [{location}]
  - name: osemosys_to_sienna_map_components
  - name: sienna_relate_components
sinks:
  - name: emit_sienna_files
    params:
      output_system_json_file_path: outputs/system.json
"""

# The chain to PyPSA names the Sienna files that it hands over, which neither leg names alone.
_TO_PYPSA_PIPELINE_YAML = """\
source_framework: osemosys
destination_framework: pypsa
compose:
  - pipeline: osemosys-csv-to-sienna
    params:
      stage_osemosys_csv.config_path: model/config.yaml
      stage_osemosys_csv.csv_dir: model/csv
      osemosys_to_sienna_map_components.year: {year}
      emit_sienna_files.output_system_json_file_path: system.json
      emit_sienna_files.output_h5_file_path: system_time_series_storage.h5
      emit_sienna_files.output_extensions_file_path: extensions.json
  - pipeline: sienna-to-pypsa
    params:
      stage_sienna_system_json.system_json_path: {system}
      stage_sienna_system_json.time_series_h5_path: {h5}
      stage_sienna_system_json.extensions_json_path: {extensions}
      emit_pypsa_network.output_path: outputs/network.nc
"""
_SIENNA_FILES = "$osemosys-csv-to-sienna.emit_sienna_files"


@given(
    parsers.parse(
        'a pipeline "{name}" that translates the otoole model to Sienna and then to PyPSA in the '
        'year "{year}"'
    )
)
def given_to_pypsa_pipeline(name: str, year: str) -> None:
    """The two legs chained through the Sienna files, as a user composes them."""
    pipeline = _TO_PYPSA_PIPELINE_YAML.format(
        year=year,
        system=f"{_SIENNA_FILES}.output_system_json_file_path",
        h5=f"{_SIENNA_FILES}.output_h5_file_path",
        extensions=f"{_SIENNA_FILES}.output_extensions_file_path",
    )
    write_pipeline(name, pipeline)


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


@given(
    parsers.parse('a pipeline "{name}" that keeps the location "{location}" before the translation')
)
def given_scoped_pipeline(name: str, location: str) -> None:
    """The steps of osemosys-csv-to-sienna, with a scope that the pipeline file states as a list."""
    write_pipeline(name, _SCOPED_PIPELINE_YAML.format(location=location))


@when(
    parsers.parse('I translate the otoole model to Sienna for the year "{year}"'),
    target_fixture="pipeline_exit_code",
)
def translate_the_otoole_model(otoole_model_builder: OtooleModelBuilder, year: str) -> int:
    return translate_with_overrides(otoole_model_builder, [f"step[1].year={year}"])


@when(
    parsers.parse(
        'I translate the otoole model to Sienna for the locations "{locations}" and the years '
        '"{years}" in the year "{year}"'
    ),
    target_fixture="pipeline_exit_code",
)
def translate_the_otoole_model_in_scope(
    otoole_model_builder: OtooleModelBuilder, locations: str, years: str, year: str
) -> int:
    """Give the scope step its locations and years as text, as a command line gives them."""
    overrides = [
        f"step[0].locations={locations}",
        f"step[0].years={years}",
        f"step[1].year={year}",
    ]
    return translate_with_overrides(otoole_model_builder, overrides)


@when(
    parsers.parse('I translate the otoole model to Sienna for the years "{years}" in the year "{year}"'),
    target_fixture="pipeline_exit_code",
)
def translate_the_otoole_model_in_years(
    otoole_model_builder: OtooleModelBuilder, years: str, year: str
) -> int:
    """Give the scope step its years as text, and keep every location."""
    overrides = [f"step[0].years={years}", f"step[1].year={year}"]
    return translate_with_overrides(otoole_model_builder, overrides)


def translate_with_overrides(
    otoole_model_builder: OtooleModelBuilder, step_overrides: list[str]
) -> int:
    """Write the model to `model/config.yaml` and `model/csv`, then translate it with
    `user_mappings.yaml`."""
    otoole_model_builder.write(Path(_CONFIG_PATH), Path(_CSV_DIRECTORY))
    overrides = [
        f"source.config_path={_CONFIG_PATH}",
        f"source.csv_dir={_CSV_DIRECTORY}",
        *step_overrides,
    ]
    return run_pipeline(_PIPELINE, overrides=overrides, user_mappings_path=_USER_MAPPINGS_PATH)


@when(
    parsers.parse('I run the otoole model through the pipeline "{pipeline}"'),
    target_fixture="pipeline_exit_code",
)
def run_the_otoole_model(otoole_model_builder: OtooleModelBuilder, pipeline: str) -> int:
    otoole_model_builder.write(Path(_CONFIG_PATH), Path(_CSV_DIRECTORY))
    return run_pipeline(pipeline, user_mappings_path=_USER_MAPPINGS_PATH)


@when(
    parsers.parse(
        'I translate the otoole model to Sienna in the REPL and answer the year "{year}" '
        'and the locations "{locations}"'
    )
)
def translate_the_otoole_model_in_the_repl(
    monkeypatch: pytest.MonkeyPatch,
    otoole_model_builder: OtooleModelBuilder,
    year: str,
    locations: str,
) -> None:
    """Answer the source paths, the locations and the year; every other prompt keeps its
    default."""
    otoole_model_builder.write(Path(_CONFIG_PATH), Path(_CSV_DIRECTORY))
    invoke_translate(
        monkeypatch,
        _SOURCE_FRAMEWORK,
        _DESTINATION_FRAMEWORK,
        _PIPELINE,
        user_mappings_path=_USER_MAPPINGS_PATH,
        source_config_path=_CONFIG_PATH,
        source_csv_dir=_CSV_DIRECTORY,
        step_0_locations=locations,
        step_1_year=year,
    )


@when(
    parsers.parse(
        'I run the otoole model through the pipeline "{pipeline}" in the REPL '
        'and answer the year "{year}"'
    )
)
def run_the_otoole_model_in_the_repl(
    monkeypatch: pytest.MonkeyPatch,
    otoole_model_builder: OtooleModelBuilder,
    pipeline: str,
    year: str,
) -> None:
    """Answer the source paths and the year; every other prompt keeps what it offers."""
    otoole_model_builder.write(Path(_CONFIG_PATH), Path(_CSV_DIRECTORY))
    invoke_translate(
        monkeypatch,
        _SOURCE_FRAMEWORK,
        _DESTINATION_FRAMEWORK,
        pipeline,
        user_mappings_path=_USER_MAPPINGS_PATH,
        source_config_path=_CONFIG_PATH,
        source_csv_dir=_CSV_DIRECTORY,
        step_1_year=year,
    )
