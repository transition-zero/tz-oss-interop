"""Sink: write the three files PowerSystemsInvestmentsPortfolios reads a portfolio from.

The portfolio document holds one flat component list with a ``__metadata__`` block on each
component. Beside it sits the base system, whose name the reader derives from the portfolio's
own and never reads from a field. Beside both sits the series companion, because the envelope
carries no time series.

No translation decisions are made here. The step resolved every region id, every cost shape
and every representative day.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, ClassVar

import polars as pl
from pydantic import BaseModel, Field

from interop.core.pipeline import Sink, State
from interop.plugins.shared.power_simulations_schema import _PSInternal, _PSUuidRef, get_new_uuid
from interop.plugins.shared.power_systems_investments_schema import (
    BASE_SYSTEM_SUFFIX,
    COMPONENT_ORDER,
    PORTFOLIO_AGGREGATION,
    PORTFOLIO_DATA_FORMAT_VERSION,
    PORTFOLIO_FINANCIAL_DATA_TYPE,
    PORTFOLIO_JSON_FILENAME,
    PORTFOLIO_METADATA_TYPE,
    PORTFOLIO_PERIODS_TABLE,
    PORTFOLIO_SERIES_TABLE,
    PSIP_MODULE,
    SERIES_JSON_SUFFIX,
    TIME_SERIES_STORAGE_TYPE,
    PortfolioColumn,
    PortfolioComponent,
    PortfolioEnvelope,
    SeriesDocument,
    build_component_metadata,
)
from interop.plugins.shared.sienna_investments_constants import PORTFOLIO_FINANCIAL_DATA_TABLE
from interop.plugins.sinks._sienna_files import drop_absent_fields
from interop.plugins.sinks.emit_power_simulations_h5_sidecar import EmitPowerSimulationsH5Sidecar
from interop.plugins.sinks.emit_power_simulations_system_json import EmitPowerSimulationsSystemJson
from interop.ports.outbound.filesystem import FilesystemPort, Location, location_name

_DEFAULT_OUTPUT_DIR = Path("outputs")
_JSON_SUFFIX = ".json"


class EmitPowerSystemsInvestmentsFilesParams(BaseModel):
    portfolio_path: Location = Field(
        default=_DEFAULT_OUTPUT_DIR / PORTFOLIO_JSON_FILENAME,
        description="the portfolio document, in the envelope Portfolio(path) reads",
    )
    h5_output_path: Location = Field(
        default=_DEFAULT_OUTPUT_DIR / "portfolio_base_system_time_series.h5",
        description="the HDF5 time-series companion the base system references by UUID",
    )
    portfolio_name: str = Field(
        default="InteropPortfolio", description="name recorded on the portfolio"
    )
    base_power: float = Field(default=100.0, description="base system base power in MVA")
    frequency: float = Field(default=50.0, description="base system frequency in Hz")
    indent: int = Field(default=2, description="JSON indent width")


class EmitPowerSystemsInvestmentsFiles(Sink):
    name: ClassVar[str] = "emit_power_systems_investments_files"
    params_schema: ClassVar[type[BaseModel] | None] = EmitPowerSystemsInvestmentsFilesParams

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def write(self, state: State, params: BaseModel | None) -> None:
        if not isinstance(params, EmitPowerSystemsInvestmentsFilesParams):
            raise TypeError(
                f"{type(self).__name__} requires "
                f"{EmitPowerSystemsInvestmentsFilesParams.__name__}, "
                f"got {type(params).__name__}"
            )
        with self._fs.open_write(params.h5_output_path) as handle:
            EmitPowerSimulationsH5Sidecar.write_h5(state, handle)
        self._write_json(
            params.portfolio_path, build_portfolio(state, params.portfolio_name), params.indent
        )
        self._write_json(
            self._sibling(params.portfolio_path, BASE_SYSTEM_SUFFIX),
            self._build_base_system(state, params),
            params.indent,
        )
        self._write_json(
            self._sibling(params.portfolio_path, SERIES_JSON_SUFFIX),
            build_series(state),
            params.indent,
        )

    def _build_base_system(
        self, state: State, params: EmitPowerSystemsInvestmentsFilesParams
    ) -> dict[str, Any]:
        return EmitPowerSimulationsSystemJson.build_document(
            state,
            h5_basename=self._location_name(params.h5_output_path),
            system_name=params.portfolio_name,
            base_power=params.base_power,
            frequency=params.frequency,
        )

    def _location_name(self, location: Location) -> str:
        return location_name(location)

    def _sibling(self, portfolio_path: Location, suffix: str) -> Location:
        """A file beside the portfolio, named the way the reader expects to find it."""
        text = str(portfolio_path)
        stem = text[: -len(_JSON_SUFFIX)] if text.endswith(_JSON_SUFFIX) else text
        sibling = f"{stem}{suffix}"
        return sibling if isinstance(portfolio_path, str) else Path(sibling)

    def _write_json(self, path: Location, payload: dict[str, Any], indent: int) -> None:
        serialised = json.dumps(payload, indent=indent, default=str).encode("utf-8")
        self._fs.write_bytes(path, serialised)


def build_portfolio(state: State, portfolio_name: str) -> dict[str, Any]:
    """The document ``Portfolio(path)`` reads.

    It states no ``time_series_storage_file``: the package reads a component through a struct
    with no field for a UUID, so every association the document carried would name a
    component that no longer exists.
    """
    portfolio: dict[str, Any] = {
        PortfolioEnvelope.AGGREGATION: str(PORTFOLIO_AGGREGATION),
        PortfolioEnvelope.DATA_FORMAT_VERSION: PORTFOLIO_DATA_FORMAT_VERSION,
        PortfolioEnvelope.INTERNAL: _new_internal(),
        PortfolioEnvelope.METADATA: _build_metadata(portfolio_name),
        PortfolioEnvelope.DATA: {
            PortfolioEnvelope.COMPONENTS: _build_components(state),
            PortfolioEnvelope.MASKED_COMPONENTS: [],
            PortfolioEnvelope.SUBSYSTEMS: {},
            PortfolioEnvelope.SUPPLEMENTAL_ATTRIBUTE_MANAGER: {
                "attributes": [],
                "associations": [],
            },
            PortfolioEnvelope.INTERNAL: _new_internal(),
            PortfolioEnvelope.TIME_SERIES_STORAGE_TYPE: TIME_SERIES_STORAGE_TYPE,
            PortfolioEnvelope.VERSION_INFO: {},
        },
    }
    financial_data = _build_financial_data(state)
    # A key the document states as null stops the read, so a value it has none of is absent.
    if financial_data is not None:
        portfolio[PortfolioEnvelope.FINANCIAL_DATA] = financial_data
    return portfolio


def build_series(state: State) -> dict[str, Any]:
    """The companion the adapter attaches after the read, and the periods the slices fall in."""
    return {
        SeriesDocument.PERIODS: _rows_of(state.destination_tables.get(PORTFOLIO_PERIODS_TABLE)),
        SeriesDocument.RECORDS: _rows_of(state.destination_tables.get(PORTFOLIO_SERIES_TABLE)),
    }


def _build_components(state: State) -> list[dict[str, Any]]:
    """Every component in one list, each naming the Julia type the package builds it as."""
    components: list[dict[str, Any]] = []
    for component in COMPONENT_ORDER:
        table = state.destination_tables.get(str(component))
        if table is None:
            continue
        components.extend(_build_one(row, component) for row in table.iter_rows(named=True))
    return components


def _build_one(row: dict[str, Any], component: PortfolioComponent) -> dict[str, Any]:
    stated = drop_absent_fields(row)
    stated[PortfolioEnvelope.METADATA_KEY] = build_component_metadata(
        component, row.get(PortfolioColumn.POWER_SYSTEMS_TYPE)
    )
    return stated


def _build_financial_data(state: State) -> dict[str, Any] | None:
    table = state.destination_tables.get(PORTFOLIO_FINANCIAL_DATA_TABLE)
    if table is None or table.is_empty():
        return None
    financial_data = drop_absent_fields(next(table.iter_rows(named=True)))
    financial_data.pop(PortfolioColumn.ID, None)
    financial_data[PortfolioEnvelope.METADATA_KEY] = {
        PortfolioEnvelope.MODULE: PSIP_MODULE,
        PortfolioEnvelope.TYPE: PORTFOLIO_FINANCIAL_DATA_TYPE,
    }
    return financial_data


def _build_metadata(portfolio_name: str) -> dict[str, Any]:
    return {
        PortfolioEnvelope.METADATA_KEY: {
            PortfolioEnvelope.MODULE: PSIP_MODULE,
            PortfolioEnvelope.TYPE: PORTFOLIO_METADATA_TYPE,
        },
        "name": portfolio_name,
    }


def _new_internal() -> dict[str, Any]:
    return _PSInternal(uuid=_PSUuidRef(value=get_new_uuid())).model_dump()


def _rows_of(table: pl.DataFrame | None) -> list[dict[str, Any]]:
    if table is None or table.is_empty():
        return []
    return [drop_absent_fields(row) for row in table.iter_rows(named=True)]
