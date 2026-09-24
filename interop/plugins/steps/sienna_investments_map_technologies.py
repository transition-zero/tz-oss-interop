"""Turn what a Sienna base system says about its own expansion into a portfolio.

An operations step runs first and writes the Sienna components and the extensions sidecar
beside them. This step reads both and writes the portfolio: the candidates as technologies,
the demand they have to meet, the caps they run under, and the attributes tying each
technology to the fleet the base system already holds.

A plant nobody has built yet is capacity a plan may add, not capacity a dispatch may use,
so its row leaves the base system as the portfolio takes it.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from functools import partial
from typing import Any, ClassVar, NamedTuple

import polars as pl
from pydantic import BaseModel, Field

from interop.core.extensions import ConstraintExtension, ExtensionKind
from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import Framework
from interop.plugins.shared.pypsa_constants import PyPSAGeneratorCol
from interop.plugins.shared.pypsa_sienna_investments_translations import (
    AREA_NAME,
    PLEXOS_TO_SIENNA_INVESTMENTS,
    REGION_COL,
    TECHNOLOGY_NAME,
    TECHNOLOGY_TYPE,
    CandidateTechnology,
    InvestmentsSource,
    build_association_rows,
    build_carbon_cap_skips,
    build_carbon_cap_translations,
    build_carbon_caps_source_table,
    build_demand_translations,
    build_existing_devices_translations,
    build_existing_fleet_source_table,
    build_financial_data_events,
    build_portfolio_financial_data,
    build_retirement_potential_translations,
    build_storage_skips,
    build_storage_technology_translations,
    build_supply_skips,
    build_supply_translations,
    build_topology_mapping_translations,
    build_topology_source_table,
    constraint_source,
)
from interop.plugins.shared.sienna_constants import (
    SIENNA_ID_COLUMN,
    SIENNA_NAME_COLUMN,
    SiennaComponent,
)
from interop.plugins.shared.sienna_investments_constants import (
    CARBON_CAPS_DESTINATION_SCHEMA,
    DEFAULT_BASE_YEAR,
    DEMAND_REQUIREMENT_DESTINATION_SCHEMA,
    EXISTING_DEVICES_DESTINATION_SCHEMA,
    PORTFOLIO_FINANCIAL_DATA_TABLE,
    RETIREMENT_POTENTIAL_DESTINATION_SCHEMA,
    STORAGE_TECHNOLOGY_DESTINATION_SCHEMA,
    SUPPLEMENTAL_ATTRIBUTE_ASSOCIATION_SCHEMA,
    SUPPLEMENTAL_ATTRIBUTE_ASSOCIATIONS_TABLE,
    SUPPLEMENTAL_ATTRIBUTE_ORDER,
    SUPPLY_TECHNOLOGY_DESTINATION_SCHEMA,
    TOPOLOGY_MAPPING_DESTINATION_SCHEMA,
    SiennaInvestmentsComponent,
    SiennaSupplementalAttribute,
)
from interop.plugins.shared.sienna_investments_sources import (
    BASE_TYPE_COL,
    GENERATOR_SIDECAR,
    GENERATOR_TYPES,
    POWER_LOAD_SOURCE,
    STORAGE_SIDECAR,
    STORAGE_SOURCE_SCHEMA,
    STORAGE_TYPES,
    SUPPLY_SOURCE_SCHEMA,
    BaseComponent,
    build_candidate_table,
    build_demand_table,
    grouping_carrier,
    list_base_components,
    read_area_by_bus,
    read_records,
)
from interop.plugins.shared.translation_runner import (
    SkipRule,
    Translation,
    apply_translations,
    filter_component,
    finalise,
)
from interop.ports.outbound.reporting import EventKind, TranslationEvent

_Schema = dict[str, pl.DataType | type[pl.DataType]]

UNBUILT_CANDIDATE_NOTE = (
    "this is capacity the plan may build rather than capacity an operations model may "
    "dispatch, so the portfolio holds it and the base system does not"
)


class _CandidateKind(NamedTuple):
    """Everything one candidate table does differently from the other."""

    extension: ExtensionKind
    source: InvestmentsSource
    base_types: tuple[SiennaComponent, ...]
    schema: _Schema
    skips: Callable[[InvestmentsSource], tuple[SkipRule, ...]]
    build: Callable[[InvestmentsSource, int, int], list[Translation]]
    destination_schema: _Schema
    component: SiennaInvestmentsComponent


_SUPPLY = _CandidateKind(
    extension=ExtensionKind.GENERATOR,
    source=GENERATOR_SIDECAR,
    base_types=GENERATOR_TYPES,
    schema=SUPPLY_SOURCE_SCHEMA,
    skips=build_supply_skips,
    build=build_supply_translations,
    destination_schema=SUPPLY_TECHNOLOGY_DESTINATION_SCHEMA,
    component=SiennaInvestmentsComponent.SUPPLY_TECHNOLOGY,
)

_STORAGE = _CandidateKind(
    extension=ExtensionKind.STORAGE,
    source=STORAGE_SIDECAR,
    base_types=STORAGE_TYPES,
    schema=STORAGE_SOURCE_SCHEMA,
    skips=build_storage_skips,
    build=build_storage_technology_translations,
    destination_schema=STORAGE_TECHNOLOGY_DESTINATION_SCHEMA,
    component=SiennaInvestmentsComponent.STORAGE_TECHNOLOGY,
)

# In the order they take their ids, which one counter hands out in turn.
_CANDIDATE_KINDS: tuple[_CandidateKind, ...] = (_SUPPLY, _STORAGE)


class _Attribute(NamedTuple):
    schema: _Schema
    build: Callable[[int], list[Translation]]
    name_col: str
    describes: Callable[[pl.DataFrame], list[str]]


_ATTRIBUTES: dict[SiennaSupplementalAttribute, _Attribute] = {
    SiennaSupplementalAttribute.EXISTING_DEVICES: _Attribute(
        schema=EXISTING_DEVICES_DESTINATION_SCHEMA,
        build=partial(build_existing_devices_translations, GENERATOR_SIDECAR),
        name_col=TECHNOLOGY_NAME,
        describes=lambda source: source[TECHNOLOGY_TYPE].to_list(),
    ),
    SiennaSupplementalAttribute.RETIREMENT_POTENTIAL: _Attribute(
        schema=RETIREMENT_POTENTIAL_DESTINATION_SCHEMA,
        build=partial(build_retirement_potential_translations, GENERATOR_SIDECAR),
        name_col=TECHNOLOGY_NAME,
        describes=lambda source: source[TECHNOLOGY_TYPE].to_list(),
    ),
    SiennaSupplementalAttribute.TOPOLOGY_MAPPING: _Attribute(
        schema=TOPOLOGY_MAPPING_DESTINATION_SCHEMA,
        build=build_topology_mapping_translations,
        name_col=AREA_NAME,
        describes=lambda source: [str(SiennaComponent.AREA)] * source.height,
    ),
}


class SiennaInvestmentsMapTechnologiesParams(BaseModel):
    base_year: int = Field(
        default=DEFAULT_BASE_YEAR,
        description=(
            "the economic year every cost in the portfolio is quoted in; no Sienna field states one"
        ),
    )


class _Numbering:
    """One id counter, handed to each table written under it in turn."""

    def __init__(self) -> None:
        self.next_id = 1


class _Found(NamedTuple):
    """One candidate table, and the base-system rows the portfolio took it from."""

    kind: _CandidateKind
    table: pl.DataFrame


class SiennaInvestmentsMapTechnologies(TranslationStep):
    """Write the investments portfolio the Sienna base system beside it already states."""

    name: ClassVar[str] = "sienna_investments_map_technologies"
    params_schema: ClassVar[type[BaseModel] | None] = SiennaInvestmentsMapTechnologiesParams

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def run(self, state: State, params: BaseModel | None) -> State:
        buses = state.destination_tables.get(SiennaComponent.AC_BUS)
        if buses is None:
            return state
        base_year = _base_year(params)
        area_by_bus = read_area_by_bus(state)
        numbering = _Numbering()
        found = [
            self._map_candidates(state, area_by_bus, kind, numbering, base_year)
            for kind in _CANDIDATE_KINDS
        ]
        self._map_demand(state, area_by_bus, numbering)
        self._map_carbon_caps(state, numbering, found)
        self._map_supplemental_attributes(state, buses, area_by_bus, found)
        state.destination_tables[PORTFOLIO_FINANCIAL_DATA_TABLE] = build_portfolio_financial_data(
            base_year
        )
        for event in build_financial_data_events(base_year):
            self._recorder.append(event)
        self._drop_unbuilt_candidates(state, found)
        return state

    def _map_candidates(
        self,
        state: State,
        area_by_bus: dict[str, str | None],
        kind: _CandidateKind,
        numbering: _Numbering,
        base_year: int,
    ) -> _Found:
        """The rows one candidate table was translated from, once the table is written."""
        components = list_base_components(state, kind.base_types)
        table = build_candidate_table(
            components, read_records(state, kind.extension), area_by_bus, kind.schema
        )
        if table.is_empty():
            return _Found(kind, table)
        for rule in kind.skips(kind.source):
            table, _ = filter_component(table, rule.keep, rule.report, self._recorder)
        if table.is_empty():
            return _Found(kind, table)
        self._write_table(
            state,
            table,
            partial(kind.build, kind.source, base_year),
            kind.destination_schema,
            kind.component,
            numbering,
        )
        return _Found(kind, table)

    def _write_table(
        self,
        state: State,
        table: pl.DataFrame,
        build: Callable[[int], list[Translation]],
        schema: _Schema,
        component: str,
        numbering: _Numbering,
    ) -> pl.DataFrame:
        """Translate one source table into a destination table, and take its share of the ids."""
        out = finalise(
            apply_translations(table, build(numbering.next_id), self._recorder),
            schema,
            self._recorder,
            component,
        )
        state.destination_tables[component] = out
        numbering.next_id += out.height
        return out

    def _map_demand(
        self, state: State, area_by_bus: dict[str, str | None], numbering: _Numbering
    ) -> None:
        table = build_demand_table(state, area_by_bus)
        if table.is_empty():
            return
        self._write_table(
            state,
            table,
            partial(build_demand_translations, POWER_LOAD_SOURCE),
            DEMAND_REQUIREMENT_DESTINATION_SCHEMA,
            SiennaInvestmentsComponent.DEMAND_REQUIREMENT,
            numbering,
        )

    def _map_carbon_caps(
        self, state: State, numbering: _Numbering, found: Sequence[_Found]
    ) -> None:
        records = [
            record
            for record in state.destination_extensions.get(ExtensionKind.CONSTRAINT, [])
            if isinstance(record, ConstraintExtension)
        ]
        if not records:
            return
        source = constraint_source(Framework.SIENNA, PLEXOS_TO_SIENNA_INVESTMENTS)
        table = build_carbon_caps_source_table(records, _model_components(state, found, records))
        for rule in build_carbon_cap_skips(source):
            table, _ = filter_component(table, rule.keep, rule.report, self._recorder)
        if table.is_empty():
            return
        self._write_table(
            state,
            table,
            partial(build_carbon_cap_translations, source),
            CARBON_CAPS_DESTINATION_SCHEMA,
            SiennaInvestmentsComponent.CARBON_CAPS,
            numbering,
        )

    def _map_supplemental_attributes(
        self,
        state: State,
        buses: pl.DataFrame,
        area_by_bus: dict[str, str | None],
        found: Sequence[_Found],
    ) -> None:
        """The three attributes, numbered from the one counter the flat array shares."""
        fleet = self._build_fleet(state, area_by_bus, found)
        topology = build_topology_source_table(buses)
        sources: dict[SiennaSupplementalAttribute, pl.DataFrame] = {
            SiennaSupplementalAttribute.EXISTING_DEVICES: fleet,
            SiennaSupplementalAttribute.RETIREMENT_POTENTIAL: fleet,
            SiennaSupplementalAttribute.TOPOLOGY_MAPPING: topology,
        }
        associations: list[pl.DataFrame] = []
        numbering = _Numbering()
        for attribute_kind in SUPPLEMENTAL_ATTRIBUTE_ORDER:
            attribute = _ATTRIBUTES[attribute_kind]
            source = sources[attribute_kind]
            if source.is_empty():
                continue
            out = self._write_table(
                state,
                source,
                attribute.build,
                attribute.schema,
                attribute_kind,
                numbering,
            )
            associations.append(
                build_association_rows(
                    attribute_kind,
                    out[SIENNA_ID_COLUMN].to_list(),
                    source[attribute.name_col].to_list(),
                    attribute.describes(source),
                )
            )
        state.destination_tables[SUPPLEMENTAL_ATTRIBUTE_ASSOCIATIONS_TABLE] = (
            pl.concat(associations)
            if associations
            else pl.DataFrame(schema=SUPPLEMENTAL_ATTRIBUTE_ASSOCIATION_SCHEMA)
        )

    def _build_fleet(
        self, state: State, area_by_bus: dict[str, str | None], found: Sequence[_Found]
    ) -> pl.DataFrame:
        """The base-system devices each technology stands for, and the years they state."""
        fleets: list[pl.DataFrame] = []
        for kind, table in found:
            records = read_records(state, kind.extension)
            devices = [
                component
                for component in list_base_components(state, kind.base_types)
                if not _is_unbuilt(records.get(component.name))
            ]
            fleets.append(
                build_existing_fleet_source_table(
                    _technologies(kind, table),
                    _fleet_groups(devices, records, area_by_bus),
                    _years(devices, records, "build_year"),
                    _years(devices, records, "retirement_year"),
                )
            )
        return pl.concat(fleets)

    def _drop_unbuilt_candidates(self, state: State, found: Sequence[_Found]) -> None:
        """Take each plant nobody has built out of the base system, and say why.

        The operations step writes one, because a hop back into PyPSA rebuilds the
        extendable generator from it. A portfolio states it as a technology instead, so the
        base system must not also hold it as a plant that may dispatch.
        """
        for _, table in found:
            if table.is_empty():
                continue
            for row in table.iter_rows(named=True):
                if row[PyPSAGeneratorCol.P_NOM_MIN]:
                    continue
                _drop_row(state, row[BASE_TYPE_COL], row[PyPSAGeneratorCol.NAME])
                self._recorder.append(_dropped_event(row))


def _base_year(params: BaseModel | None) -> int:
    if isinstance(params, SiennaInvestmentsMapTechnologiesParams):
        return params.base_year
    return DEFAULT_BASE_YEAR


def _drop_row(state: State, sienna_type: str, name: str) -> None:
    table = state.destination_tables.get(sienna_type)
    if table is None:
        return
    state.destination_tables[sienna_type] = table.filter(pl.col(SIENNA_NAME_COLUMN) != name)


def _dropped_event(row: dict[str, Any]) -> TranslationEvent:
    return TranslationEvent(
        kind=EventKind.COMPONENT_SKIPPED,
        sources=[
            GENERATOR_SIDECAR.field(
                row[PyPSAGeneratorCol.NAME],
                PyPSAGeneratorCol.P_NOM_EXTENDABLE,
                row[PyPSAGeneratorCol.P_NOM_EXTENDABLE],
            )
        ],
        note=UNBUILT_CANDIDATE_NOTE,
    )


def _is_unbuilt(record: object) -> bool:
    """Whether the sidecar states a build and no capacity the component already runs."""
    return bool(
        record is not None
        and getattr(record, "p_nom_extendable", False)
        and not (getattr(record, "p_nom_min", None) or 0.0)
    )


def _technologies(kind: _CandidateKind, table: pl.DataFrame) -> list[CandidateTechnology]:
    """Each translated technology, beside the fleet its base-system devices make up.

    ``component_type`` is the portfolio component the attribute describes, and
    ``device_class`` is the base-system class of the devices it lists.
    """
    if table.is_empty():
        return []
    return [
        CandidateTechnology(
            name=name,
            component_type=str(kind.component),
            device_class=base_type,
            carrier=carrier or base_type,
            region=region,
        )
        for name, base_type, carrier, region in zip(
            table[PyPSAGeneratorCol.NAME].to_list(),
            table[BASE_TYPE_COL].to_list(),
            table[PyPSAGeneratorCol.CARRIER].to_list(),
            table[REGION_COL].to_list(),
            strict=True,
        )
    ]


def _fleet_groups(
    devices: Sequence[BaseComponent],
    records: dict[str, Any],
    area_by_bus: dict[str, str | None],
) -> dict[tuple[str, str | None], list[str]]:
    """The base-system components of each carrier and area, in the order the system holds them."""
    groups: dict[tuple[str, str | None], list[str]] = {}
    for device in devices:
        carrier = grouping_carrier(records.get(device.name), device.sienna_type)
        groups.setdefault((carrier, area_by_bus.get(device.bus or "")), []).append(device.name)
    return groups


def _years(
    devices: Sequence[BaseComponent], records: dict[str, Any], attribute: str
) -> dict[str, int]:
    """One year per device that states it, read off the sidecar record."""
    years: dict[str, int] = {}
    for device in devices:
        value = getattr(records.get(device.name), attribute, None)
        if value is not None:
            years[device.name] = int(value)
    return years


def _model_components(
    state: State, found: Sequence[_Found], records: Sequence[ConstraintExtension]
) -> set[tuple[str, str]]:
    """Every component a constraint could weight, named by the class the constraints use.

    A constraint states each member's class in the words of the framework that wrote the
    record, which is the source framework and never Sienna. So a component a constraint
    names travels under that class, and one no constraint names keeps its Sienna type. A
    component nothing names fails the subset test on its name alone, whatever its class.
    """
    named = _classes_by_member(records)
    components: set[tuple[str, str]] = set()
    for kind, table in found:
        for component in list_base_components(state, kind.base_types):
            components.add((component.name, named.get(component.name, component.sienna_type)))
        if not table.is_empty():
            for name, base_type in zip(
                table[PyPSAGeneratorCol.NAME].to_list(),
                table[BASE_TYPE_COL].to_list(),
                strict=True,
            ):
                components.add((name, named.get(name, base_type)))
    return components


def _classes_by_member(records: Sequence[ConstraintExtension]) -> dict[str, str]:
    """The class every constraint's members give each name they weight."""
    return {member.name: member.member_class for record in records for member in record.members}
