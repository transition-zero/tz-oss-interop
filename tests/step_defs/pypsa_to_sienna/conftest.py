from __future__ import annotations

from pathlib import Path

import pytest
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


@given("a user mappings file with all standard carriers")
def given_standard_mapping() -> None:
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
