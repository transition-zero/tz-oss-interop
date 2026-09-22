from __future__ import annotations

from pathlib import Path

import pytest
from pytest_bdd import parsers, when

from tests.step_defs.conftest import (
    STANDARD_CARRIER_MAP,
    STANDARD_PRIME_MOVER_MAP,
    invoke_translate,
    write_user_mappings,
)

_MAPPINGS_PATH = "user_mappings.yaml"

_CARRIERS = ("solar", "onwind", "hydro", "PHS")
_THERMAL_CARRIER = "CCGT"


@pytest.fixture(autouse=True)
def carrier_mappings_file() -> None:
    write_user_mappings(
        {_THERMAL_CARRIER: STANDARD_CARRIER_MAP[_THERMAL_CARRIER]},
        prime_mover={carrier: STANDARD_PRIME_MOVER_MAP[carrier] for carrier in _CARRIERS},
    )


@when(parsers.parse('I translate "{nc_path}" into a Sienna portfolio'))
def run_sienna_investments_translation(monkeypatch: pytest.MonkeyPatch, nc_path: str) -> None:
    invoke_translate(
        monkeypatch,
        "pypsa",
        "sienna",
        "pypsa-to-sienna-investments",
        user_mappings_path=_MAPPINGS_PATH,
        source_path=str(Path(nc_path)),
        sink_0_output_system_json_file_path="outputs/system.json",
        sink_1_output_path="outputs/portfolio.json",
    )


@when(parsers.parse('I run the investments solver translation writing "{portfolio_path}"'))
def run_investments_solver_translation(
    monkeypatch: pytest.MonkeyPatch, portfolio_path: str
) -> None:
    invoke_translate(
        monkeypatch,
        "sienna",
        "power-systems-investments",
        "sienna-to-power-systems-investments",
        source_portfolio_json_path="outputs/portfolio.json",
        source_system_json_path="outputs/system.json",
        source_time_series_h5_path="outputs/system_time_series_storage.h5",
        sink_0_portfolio_path=portfolio_path,
        sink_0_h5_output_path="psi/portfolio_base_system_time_series.h5",
    )
