from __future__ import annotations

import json
import uuid
from pathlib import Path

import h5py
import numpy as np
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
_BASE_SYSTEM_H5_NAME = "portfolio_base_system_time_series.h5"
_PORTFOLIO_H5_NAME = "portfolio_time_series_storage.h5"
_HOURLY = "P0DT3600.000S"


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
    invoke_investments_solver_translation(monkeypatch, portfolio_path)


@when(
    parsers.parse(
        'I run the investments solver translation writing "{portfolio_path}" '
        "at a base power of {base_power} MVA"
    )
)
def run_investments_solver_translation_at_base_power(
    monkeypatch: pytest.MonkeyPatch, portfolio_path: str, base_power: str
) -> None:
    invoke_investments_solver_translation(monkeypatch, portfolio_path, sink_0_base_power=base_power)


def invoke_investments_solver_translation(
    monkeypatch: pytest.MonkeyPatch, portfolio_path: str, **sink_answers: str
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
        sink_0_h5_output_path=str(Path(portfolio_path).parent / _BASE_SYSTEM_H5_NAME),
        **sink_answers,
    )


@when(
    parsers.parse(
        'I give "{component}" "{name}" of the portfolio "{path}" a "{series}" series for the '
        "year {year} of {count:d} hourly values of {value:g}"
    )
)
def add_portfolio_series(
    component: str, name: str, path: str, series: str, year: str, count: int, value: float
) -> None:
    """Add one series to a written portfolio, with the year feature written as it is given."""
    portfolio_path = Path(path)
    portfolio = json.loads(portfolio_path.read_text(encoding="utf-8"))
    owner = next(c for c in portfolio["components"][component] if c["name"] == name)
    series_uuid = str(uuid.uuid4())
    h5_path = portfolio_path.parent / _PORTFOLIO_H5_NAME
    with h5py.File(h5_path, "a") as h5:
        root = h5.require_group("time_series")
        root.create_group(series_uuid).create_dataset("data", data=np.full(count, value))
    associations = portfolio.setdefault("time_series_associations", [])
    associations.append(
        {
            "association_id": len(associations) + 1,
            "owner_type": component,
            "owner_id": owner["id"],
            "name": series,
            "time_series_uuid": series_uuid,
            "time_series_type": "SingleTimeSeries",
            "initial_timestamp": f"{int(float(year))}-01-01T00:00:00",
            "resolution": _HOURLY,
            "length": count,
            "features": {"year": json.loads(year)},
        }
    )
    portfolio["time_series_storage_file"] = _PORTFOLIO_H5_NAME
    portfolio_path.write_text(json.dumps(portfolio, indent=2), encoding="utf-8")


@when(
    parsers.parse(
        'I add to the portfolio "{path}" the transport technology "{name}" from area "{start}" '
        'to area "{end}" with capacity limits from {minimum:g} to {maximum:g} MW'
    )
)
def add_portfolio_transport(
    path: str, name: str, start: str, end: str, minimum: float, maximum: float
) -> None:
    """Add one transport technology to a written portfolio, naming each end by its area id."""
    portfolio_path = Path(path)
    portfolio = json.loads(portfolio_path.read_text(encoding="utf-8"))
    system = json.loads((portfolio_path.parent / "system.json").read_text(encoding="utf-8"))
    area_ids = {area["name"]: area["id"] for area in system["components"]["Area"]}
    components = portfolio["components"]
    next_id = 1 + max(c["id"] for rows in components.values() for c in rows)
    components.setdefault("AggregateTransportTechnology", []).append(
        {
            "id": next_id,
            "name": name,
            "available": True,
            "power_systems_type": "ACBranch",
            "start_region": area_ids[start],
            "end_region": area_ids[end],
            "capacity_limits": {"min": minimum, "max": maximum},
        }
    )
    portfolio_path.write_text(json.dumps(portfolio, indent=2), encoding="utf-8")
