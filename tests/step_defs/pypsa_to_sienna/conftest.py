from __future__ import annotations

from pathlib import Path

import pytest
from interop_testing import write_pipeline, write_project_plugin
from pytest_bdd import given, parsers, when

from tests.step_defs.conftest import (
    STANDARD_CARRIER_MAP,
    STANDARD_PRIME_MOVER_MAP,
    invoke_translate,
    write_user_mappings,
)


@pytest.fixture(autouse=True)
def default_user_mappings() -> None:
    write_user_mappings(STANDARD_CARRIER_MAP, prime_mover=STANDARD_PRIME_MOVER_MAP)


@given(parsers.parse('a user mappings file covering only carrier "{carrier}"'))
def given_mapping_single_carrier(carrier: str) -> None:
    write_user_mappings({carrier: STANDARD_CARRIER_MAP[carrier]})


@when(
    parsers.parse(
        'I run translate against "{nc_path}" pipeline "{pipeline}" sink output "{sink_output}"'
    )
)
def run_translate_pypsa_to_sienna(
    monkeypatch: pytest.MonkeyPatch,
    nc_path: str,
    pipeline: str,
    sink_output: str,
) -> None:
    invoke_translate(
        monkeypatch,
        "pypsa",
        "sienna",
        pipeline,
        user_mappings_path="user_mappings.yaml",
        source_path=str(Path(nc_path)),
        sink_0_output_system_json_file_path=sink_output,
    )


@when(
    parsers.parse(
        'I run translate against "{nc_path}" with sidecar "{extensions_path}" '
        'pipeline "{pipeline}" sink output "{sink_output}"'
    )
)
def run_translate_with_sidecar(
    monkeypatch: pytest.MonkeyPatch,
    nc_path: str,
    extensions_path: str,
    pipeline: str,
    sink_output: str,
) -> None:
    invoke_translate(
        monkeypatch,
        "pypsa",
        "sienna",
        pipeline,
        user_mappings_path="user_mappings.yaml",
        source_path=str(Path(nc_path)),
        source_extensions_json_path=str(Path(extensions_path)),
        sink_0_output_system_json_file_path=sink_output,
    )


_ADD_AREA_FIELD_STEP_PY = """\
from typing import ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep


class AddAreaField(TranslationStep):
    name: ClassVar[str] = "add_area_field"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def run(self, state: State, params: BaseModel | None) -> State:
        areas = state.destination_tables["Area"]
        state.destination_tables["Area"] = areas.with_columns(pl.lit(1.0).alias("{field}"))
        return state
"""

_DRIFTED_PIPELINE_YAML = """\
source_framework: pypsa
destination_framework: sienna
source:
  name: stage_pypsa_network_file
steps:
  - name: pypsa_to_sienna_map_components
  - name: sienna_relate_components
  - name: add_area_field
sinks:
  - name: emit_sienna_files
    params:
      output_system_json_file_path: outputs/system.json
"""


@given(parsers.parse('a pipeline "{name}" whose last step adds the field "{field}" to each Area'))
def given_pipeline_adding_area_field(name: str, field: str) -> None:
    step_source = _ADD_AREA_FIELD_STEP_PY.replace("{field}", field)
    write_project_plugin("steps", "add_area_field", step_source)
    write_pipeline(name, _DRIFTED_PIPELINE_YAML)
