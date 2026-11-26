from __future__ import annotations

from pathlib import Path

from interop_testing import run_pipeline
from interop_testing.builders.sienna_documents import (
    sienna_extensions_filename,
    sienna_h5_filename,
)
from interop_testing.builders.sienna_systems import SiennaSystemBuilder
from pytest_bdd import parsers, when

_PIPELINE = "sienna-to-osemosys-csv"
_SYSTEM_PATH = Path("inputs/system.json")
_MAPPINGS_OUTPUT_PATH = "outputs/osemosys_mappings.yaml"


@when(
    parsers.parse('I write the Sienna system out as an otoole model in "{output_dir}"'),
    target_fixture="pipeline_exit_code",
)
def write_the_sienna_system_out(sienna_system_builder: SiennaSystemBuilder, output_dir: str) -> int:
    sienna_system_builder.save(_SYSTEM_PATH)
    return run_pipeline(_PIPELINE, overrides=_build_overrides(output_dir))


def _build_overrides(output_dir: str) -> list[str]:
    directory = _SYSTEM_PATH.parent
    sidecar = directory / sienna_extensions_filename(_SYSTEM_PATH)
    overrides = [
        f"source.system_json_path={_SYSTEM_PATH}",
        f"source.time_series_h5_path={directory / sienna_h5_filename(_SYSTEM_PATH)}",
        f"sink[0].output_config_path={output_dir}/config.yaml",
        f"sink[0].output_csv_dir={output_dir}/csv",
        f"sink[0].output_mappings_path={_MAPPINGS_OUTPUT_PATH}",
    ]
    if sidecar.is_file():
        overrides.append(f"source.extensions_json_path={sidecar}")
    return overrides
