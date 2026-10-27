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
    SiennaTimeSeriesAssociationCol,
)
from interop.plugins.shared.sienna_investments_constants import (
    CAPACITY_LIMITS_BY_KEY_DTYPE,
    PORTFOLIO_AGGREGATION,
    PORTFOLIO_FINANCIAL_DATA_TABLE,
    PORTFOLIO_JSON_FILENAME,
    PORTFOLIO_TIME_SERIES_ASSOCIATIONS_TABLE,
    PORTFOLIO_TIME_SERIES_FILENAME,
    SUPPLEMENTAL_ATTRIBUTE_ASSOCIATIONS_TABLE,
    SUPPLEMENTAL_ATTRIBUTE_ORDER,
    MinMaxByKeyField,
    NamedYearField,
    PortfolioDocument,
    SiennaAggregateTransportTechnologyCol,
    SiennaInvestmentsComponent,
    SiennaRetirementPotentialCol,
    SiennaSupplementalAttributeAssociationCol,
)
from interop.plugins.sinks._sienna_files import (
    SYSTEM_JSON_FILENAME,
    drop_absent_fields,
    serialise_portfolio_document,
    validate_refs,
)
from interop.plugins.sinks.emit_sienna_h5_sidecar import EmitSiennaH5Sidecar
from interop.ports.outbound.filesystem import (
    FilesystemPort,
    Location,
    build_sibling_location,
    location_name,
)

_DEFAULT_OUTPUT_DIR = Path("outputs")

_NAMED_YEAR_FIELDS: tuple[str, ...] = (
    SiennaRetirementPotentialCol.BUILD_YEAR,
    SiennaRetirementPotentialCol.PLANNED_RETIREMENT_YEAR,
)

_COMPONENT_TYPES: tuple[SiennaInvestmentsComponent, ...] = (
    SiennaInvestmentsComponent.SUPPLY_TECHNOLOGY,
    SiennaInvestmentsComponent.STORAGE_TECHNOLOGY,
    SiennaInvestmentsComponent.AGGREGATE_TRANSPORT_TECHNOLOGY,
    SiennaInvestmentsComponent.DEMAND_REQUIREMENT,
    SiennaInvestmentsComponent.CARBON_CAPS,
)

# Each column that holds an area name, and the field that states the id of that area.
_AREA_REFERENCES: dict[str, str] = {
    SIENNA_REGION_NAME_COLUMN: SIENNA_REGION_COLUMN,
    SiennaAggregateTransportTechnologyCol.START_REGION_NAME: (
        SiennaAggregateTransportTechnologyCol.START_REGION
    ),
    SiennaAggregateTransportTechnologyCol.END_REGION_NAME: (
        SiennaAggregateTransportTechnologyCol.END_REGION
    ),
}

# The association columns that locate a staged series for the HDF5 sink, which no reader needs.
_INTERNAL_SERIES_COLUMNS = frozenset(
    [
        SiennaTimeSeriesAssociationCol.COMPONENT_NAME,
        SiennaTimeSeriesAssociationCol.SOURCE_TABLE,
        SiennaTimeSeriesAssociationCol.SOURCE_ATTRIBUTE,
        SiennaTimeSeriesAssociationCol.SCALING_FACTOR,
    ]
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
        description=(
            "basename of the HDF5 companion holding the base system's time series, which the "
            "portfolio names when it holds no time series of its own"
        ),
    )
    output_time_series_path: Location | None = Field(
        default=None,
        description=(
            "the HDF5 companion holding the time series of the portfolio, when it has any; "
            "empty writes it beside the portfolio"
        ),
    )
    indent: int = Field(default=2, description="JSON indent width")

    @property
    def time_series_path(self) -> Location:
        """The HDF5 companion of the portfolio, which is beside it unless a path is given."""
        if self.output_time_series_path is not None:
            return self.output_time_series_path
        return build_sibling_location(self.output_path, PORTFOLIO_TIME_SERIES_FILENAME)

    @property
    def time_series_file(self) -> str:
        """The basename of the HDF5 companion of the portfolio, which the document names."""
        return location_name(self.time_series_path)


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
        associations = _find_series_associations(state)
        payload = self.build_payload(state, associations, params)
        if associations is not None:
            with self._fs.open_write(params.time_series_path) as stream:
                EmitSiennaH5Sidecar.write_associated_h5(state, associations, stream)
        serialised = serialise_portfolio_document(payload, params.indent)
        self._fs.write_bytes(params.output_path, serialised)

    @staticmethod
    def build_payload(
        state: State, associations: pl.DataFrame | None, params: EmitSiennaPortfolioParams
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
            PortfolioDocument.REQUIREMENTS_ASSOCIATIONS: [],
            PortfolioDocument.TIME_SERIES_ASSOCIATIONS: _build_time_series_associations(
                associations
            ),
            PortfolioDocument.BASE_SYSTEM_FILE: params.base_system_file,
            PortfolioDocument.TIME_SERIES_STORAGE_FILE: _choose_storage_file(associations, params),
        }
        financial_data = state.destination_tables.get(PORTFOLIO_FINANCIAL_DATA_TABLE)
        if financial_data is not None and not financial_data.is_empty():
            payload[PortfolioDocument.FINANCIAL_DATA] = drop_absent_fields(
                next(financial_data.iter_rows(named=True))
            )
        return payload


def _find_series_associations(state: State) -> pl.DataFrame | None:
    """The rows of the portfolio's own series, or None when it states no series."""
    associations = state.destination_tables.get(PORTFOLIO_TIME_SERIES_ASSOCIATIONS_TABLE)
    if associations is None or associations.is_empty():
        return None
    return associations


def _choose_storage_file(
    associations: pl.DataFrame | None, params: EmitSiennaPortfolioParams
) -> str:
    """The companion of the portfolio's own series, else the companion of the base system."""
    if associations is None:
        return params.time_series_storage_file
    return params.time_series_file


def _name_to_id(table: pl.DataFrame | None) -> dict[str, int]:
    if table is None or table.is_empty():
        return {}
    return dict(
        zip(table[SIENNA_NAME_COLUMN].to_list(), table[SIENNA_ID_COLUMN].to_list(), strict=True)
    )


def _build_components(table: pl.DataFrame | None, area_ids: dict[str, int]) -> list[dict[str, Any]]:
    """One object per row, with each area name resolved to the id of that area."""
    if table is None or table.is_empty():
        return []
    references = {name: field for name, field in _AREA_REFERENCES.items() if name in table.columns}
    for name in references:
        validate_refs(
            name,
            table[name].drop_nulls().unique().to_list(),
            set(area_ids),
            "technologies -> areas",
        )
    by_key = [name for name, dtype in table.schema.items() if dtype == CAPACITY_LIMITS_BY_KEY_DTYPE]
    return [
        _build_component(row, references, by_key, area_ids) for row in table.iter_rows(named=True)
    ]


def _build_component(
    row: dict[str, Any],
    references: dict[str, str],
    by_key: list[str],
    area_ids: dict[str, int],
) -> dict[str, Any]:
    fields = {k: _build_by_key(v) if k in by_key else v for k, v in row.items()}
    component = drop_absent_fields({k: v for k, v in fields.items() if k not in references})
    for name, field in references.items():
        area_name = row[name]
        if area_name is not None:
            area_id = area_ids[area_name]
            component[field] = [area_id] if field == SIENNA_REGION_COLUMN else area_id
    return component


def _build_by_key(entries: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    """A list of key, min and max entries, as the object keyed by `key` that the schema states."""
    if entries is None:
        return None
    return {
        entry[MinMaxByKeyField.KEY]: drop_absent_fields(
            {field: value for field, value in entry.items() if field != MinMaxByKeyField.KEY}
        )
        for entry in entries
    }


def _build_time_series_associations(table: pl.DataFrame | None) -> list[dict[str, Any]]:
    """One row for each series of the portfolio, with its features as an object."""
    if table is None:
        return []
    columns = [name for name in table.columns if name not in _INTERNAL_SERIES_COLUMNS]
    rows = table.select(columns).with_row_index(
        name=SiennaTimeSeriesAssociationCol.ASSOCIATION_ID, offset=1
    )
    features = SiennaTimeSeriesAssociationCol.FEATURES
    return [
        drop_absent_fields({**row, features: json.loads(row[features])})
        for row in rows.iter_rows(named=True)
    ]


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
            attributes.append(drop_absent_fields({k: _named_years(k, v) for k, v in row.items()}))
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
