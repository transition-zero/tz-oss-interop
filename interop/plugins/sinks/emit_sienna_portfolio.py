"""Write the SiennaSchemas portfolio document beside the base system it expands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, ClassVar

import polars as pl
from pydantic import BaseModel, Field

from interop.core.pipeline import Sink, State
from interop.plugins.shared.sienna_constants import (
    SIENNA_ID_COLUMN,
    SIENNA_NAME_COLUMN,
    SIENNA_REGION_COLUMN,
    SIENNA_REGION_NAME_COLUMN,
    SiennaCompanionFilename,
    SiennaComponent,
)
from interop.plugins.shared.sienna_investments_constants import (
    PORTFOLIO_AGGREGATION,
    PORTFOLIO_FINANCIAL_DATA_TABLE,
    PORTFOLIO_JSON_FILENAME,
    SUPPLEMENTAL_ATTRIBUTE_ASSOCIATIONS_TABLE,
    SUPPLEMENTAL_ATTRIBUTE_ORDER,
    NamedYearField,
    PortfolioDocument,
    SiennaInvestmentsComponent,
    SiennaRetirementPotentialCol,
    SiennaSupplementalAttributeAssociationCol,
)
from interop.plugins.sinks._sienna_files import SYSTEM_JSON_FILENAME, validate_refs
from interop.ports.outbound.filesystem import FilesystemPort, Location

_DEFAULT_OUTPUT_DIR = Path("outputs")

_NAMED_YEAR_FIELDS: tuple[str, ...] = (
    SiennaRetirementPotentialCol.BUILD_YEAR,
    SiennaRetirementPotentialCol.PLANNED_RETIREMENT_YEAR,
)

_COMPONENT_TYPES: tuple[SiennaInvestmentsComponent, ...] = (
    SiennaInvestmentsComponent.SUPPLY_TECHNOLOGY,
    SiennaInvestmentsComponent.STORAGE_TECHNOLOGY,
    SiennaInvestmentsComponent.DEMAND_REQUIREMENT,
    SiennaInvestmentsComponent.CARBON_CAPS,
)


class EmitSiennaPortfolioParams(BaseModel):
    output_path: Location = Field(
        default=_DEFAULT_OUTPUT_DIR / PORTFOLIO_JSON_FILENAME,
        description="the SiennaSchemas portfolio document to write",
    )
    base_system_file: str = Field(
        default=SYSTEM_JSON_FILENAME,
        description="basename of the base system document the portfolio expands",
    )
    time_series_storage_file: str = Field(
        default=SiennaCompanionFilename.TIME_SERIES_H5,
        description="basename of the HDF5 companion holding the base system's time series",
    )
    indent: int = Field(default=2, description="JSON indent width")


class EmitSiennaPortfolio(Sink):
    name: ClassVar[str] = "emit_sienna_portfolio"
    params_schema: ClassVar[type[BaseModel] | None] = EmitSiennaPortfolioParams

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def write(self, state: State, params: BaseModel | None) -> None:
        if not isinstance(params, EmitSiennaPortfolioParams):
            raise TypeError(
                f"{type(self).__name__} requires {EmitSiennaPortfolioParams.__name__}, "
                f"got {type(params).__name__}"
            )
        payload = self.build_payload(
            state, params.base_system_file, params.time_series_storage_file
        )
        serialised = json.dumps(payload, indent=params.indent, default=str).encode("utf-8")
        self._fs.write_bytes(params.output_path, serialised)

    @staticmethod
    def build_payload(
        state: State, base_system_file: str, time_series_storage_file: str
    ) -> dict[str, Any]:
        area_ids = _name_to_id(state.destination_tables.get(SiennaComponent.AREA))
        components: dict[str, Any] = {}
        component_ids: dict[str, dict[str, int]] = {}
        for component in _COMPONENT_TYPES:
            table = state.destination_tables.get(component)
            objects = _build_components(table, area_ids)
            if objects:
                components[str(component)] = objects
            component_ids[str(component)] = _name_to_id(table)
        component_ids[str(SiennaComponent.AREA)] = area_ids

        attributes, attribute_ids = _build_attributes(state)
        payload: dict[str, Any] = {
            PortfolioDocument.AGGREGATION: PORTFOLIO_AGGREGATION,
            PortfolioDocument.COMPONENTS: components,
            PortfolioDocument.SUPPLEMENTAL_ATTRIBUTES: attributes,
            PortfolioDocument.SUPPLEMENTAL_ATTRIBUTE_ASSOCIATIONS: _build_associations(
                state.destination_tables.get(SUPPLEMENTAL_ATTRIBUTE_ASSOCIATIONS_TABLE),
                component_ids,
                attribute_ids,
            ),
            PortfolioDocument.TIME_SERIES_ASSOCIATIONS: [],
            PortfolioDocument.BASE_SYSTEM_FILE: base_system_file,
            PortfolioDocument.TIME_SERIES_STORAGE_FILE: time_series_storage_file,
        }
        financial_data = state.destination_tables.get(PORTFOLIO_FINANCIAL_DATA_TABLE)
        if financial_data is not None and not financial_data.is_empty():
            payload[PortfolioDocument.FINANCIAL_DATA] = _stated(
                next(financial_data.iter_rows(named=True))
            )
        return payload


def _name_to_id(table: pl.DataFrame | None) -> dict[str, int]:
    if table is None or table.is_empty():
        return {}
    return dict(
        zip(table[SIENNA_NAME_COLUMN].to_list(), table[SIENNA_ID_COLUMN].to_list(), strict=True)
    )


def _build_components(table: pl.DataFrame | None, area_ids: dict[str, int]) -> list[dict[str, Any]]:
    """One object per row, with the region name resolved to the area ids it stands for."""
    if table is None or table.is_empty():
        return []
    holds_region = SIENNA_REGION_NAME_COLUMN in table.columns
    if holds_region:
        validate_refs(
            SIENNA_REGION_NAME_COLUMN,
            table[SIENNA_REGION_NAME_COLUMN].drop_nulls().unique().to_list(),
            set(area_ids),
            "technologies -> areas",
        )
    objects: list[dict[str, Any]] = []
    for row in table.iter_rows(named=True):
        component = _stated({k: v for k, v in row.items() if k != SIENNA_REGION_NAME_COLUMN})
        area_name = row.get(SIENNA_REGION_NAME_COLUMN) if holds_region else None
        if area_name is not None:
            component[SIENNA_REGION_COLUMN] = [area_ids[area_name]]
        objects.append(component)
    return objects


def _build_attributes(state: State) -> tuple[list[dict[str, Any]], set[int]]:
    """The flat array, in the order the step numbered its types, and the ids it holds."""
    attributes: list[dict[str, Any]] = []
    ids: set[int] = set()
    for attribute in SUPPLEMENTAL_ATTRIBUTE_ORDER:
        table = state.destination_tables.get(attribute)
        if table is None:
            continue
        for row in table.iter_rows(named=True):
            ids.add(row[SIENNA_ID_COLUMN])
            attributes.append(_stated({k: _named_years(k, v) for k, v in row.items()}))
    return attributes, ids


def _named_years(field: str, value: Any) -> Any:
    """A list of name/year pairs, as the object keyed by name that the schema states."""
    if field not in _NAMED_YEAR_FIELDS or value is None:
        return value
    years = {entry[NamedYearField.NAME]: entry[NamedYearField.YEAR] for entry in value}
    return years or None


def _build_associations(
    table: pl.DataFrame | None,
    component_ids: dict[str, dict[str, int]],
    attribute_ids: set[int],
) -> list[dict[str, Any]]:
    """One row per (attribute, component) pair, with the component's name resolved to its id."""
    if table is None or table.is_empty():
        return []
    A = SiennaSupplementalAttributeAssociationCol
    rows: list[dict[str, Any]] = []
    for row in table.iter_rows(named=True):
        component_type = row[A.COMPONENT_TYPE]
        name = row[A.COMPONENT_NAME]
        by_name = component_ids.get(component_type, {})
        validate_refs(A.COMPONENT_NAME, [name], set(by_name), f"attributes -> {component_type}")
        if row[A.ATTRIBUTE_ID] not in attribute_ids:
            raise ValueError(
                f"attributes -> supplemental_attributes: no attribute with id {row[A.ATTRIBUTE_ID]}"
            )
        rows.append(
            {
                A.COMPONENT_ID: by_name[name],
                A.COMPONENT_TYPE: component_type,
                A.ATTRIBUTE_ID: row[A.ATTRIBUTE_ID],
                A.ATTRIBUTE_TYPE: row[A.ATTRIBUTE_TYPE],
            }
        )
    return rows


def _stated(row: dict[str, Any]) -> dict[str, Any]:
    """The fields a row actually holds, at every depth of a nested struct.

    A field no table wrote is absent rather than null, so the schema's own default applies
    to it rather than a null a consumer would have to read as one. A cost struct carries
    every variant's fields, so this is also what leaves a renewable technology's cost
    without the two a thermal one alone states.
    """
    return {
        key: _stated(value) if isinstance(value, dict) else value
        for key, value in row.items()
        if value is not None
    }
