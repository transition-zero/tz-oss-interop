from pathlib import Path

import pytest
from interop_testing import write_pipeline
from pytest_bdd import given, parsers, scenarios, when

from tests.step_defs.conftest import (
    invoke_translate,
)

scenarios("../features/pypsa_to_sienna_to_pypsa.feature")

# Written by the test rather than shipped: going out and back checks that the two hops
# agree, which is not a translation anyone asks the menu for, and shipping it would offer
# PyPSA as a destination from PyPSA.
_ROUND_TRIP_PIPELINE = """\
source_framework: pypsa
destination_framework: pypsa
compose:
  - pipeline: pypsa-to-sienna
    params:
      emit_sienna_files.output_system_json_file_path: system.json
      emit_sienna_files.output_h5_file_path: system_time_series_storage.h5
      emit_sienna_files.output_extensions_file_path: extensions.json
  - pipeline: sienna-to-pypsa
    params:
      stage_sienna_system_json.system_json_path: {system}
      stage_sienna_system_json.time_series_h5_path: {h5}
      stage_sienna_system_json.extensions_json_path: {extensions}
""".format(
    system="$pypsa-to-sienna.emit_sienna_files.output_system_json_file_path",
    h5="$pypsa-to-sienna.emit_sienna_files.output_h5_file_path",
    extensions="$pypsa-to-sienna.emit_sienna_files.output_extensions_file_path",
)


@given(parsers.parse('a project-local pipeline "{name}" chaining pypsa-to-sienna then back'))
def given_round_trip_pipeline(name: str) -> None:
    write_pipeline(name, _ROUND_TRIP_PIPELINE)


@when(
    parsers.parse(
        'I run translate against "{nc_path}" pipeline "{pipeline}" '
        'writing the network back to "{nc_output}"'
    )
)
def run_round_trip(
    monkeypatch: pytest.MonkeyPatch, nc_path: str, pipeline: str, nc_output: str
) -> None:
    invoke_translate(
        monkeypatch,
        "pypsa",
        "pypsa",
        pipeline,
        user_mappings_path="user_mappings.yaml",
        source_path=str(Path(nc_path)),
        sink_0_output_path=nc_output,
    )
