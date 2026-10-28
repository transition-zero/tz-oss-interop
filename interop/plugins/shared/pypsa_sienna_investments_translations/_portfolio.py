"""The tables of one investments portfolio, numbered by the counters that its associations read.

An association names a component or an attribute by id alone, so ids are unique across the
components of a portfolio, and across its flat array of supplemental attributes. The
components share one counter, and the attributes share a second.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from typing import NamedTuple

import polars as pl

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.pypsa_sienna_investments_translations._associations import (
    build_association_rows,
)
from interop.plugins.shared.pypsa_sienna_investments_translations._existing import (
    TECHNOLOGY_NAME,
    TECHNOLOGY_TYPE,
    build_existing_devices_translations,
    build_retirement_potential_translations,
)
from interop.plugins.shared.pypsa_sienna_investments_translations._shared import (
    InvestmentsSource,
)
from interop.plugins.shared.pypsa_sienna_investments_translations._topology import (
    AREA_NAME,
    build_topology_mapping_translations,
    build_topology_source_table,
)
from interop.plugins.shared.sienna_constants import SIENNA_ID_COLUMN, SiennaComponent
from interop.plugins.shared.sienna_investments_constants import (
    EXISTING_DEVICES_DESTINATION_SCHEMA,
    RETIREMENT_POTENTIAL_DESTINATION_SCHEMA,
    SUPPLEMENTAL_ATTRIBUTE_ASSOCIATION_SCHEMA,
    SUPPLEMENTAL_ATTRIBUTE_ASSOCIATIONS_TABLE,
    SUPPLEMENTAL_ATTRIBUTE_ORDER,
    TOPOLOGY_MAPPING_DESTINATION_SCHEMA,
    SiennaSupplementalAttribute,
)
from interop.plugins.shared.translation_runner import Translation, apply_translations, finalise

Schema = dict[str, pl.DataType | type[pl.DataType]]
# The translations of one table, with ids from the first id that the table takes.
BuildTranslations = Callable[[int], list[Translation]]

_FIRST_ID = 1


class PortfolioTable(NamedTuple):
    """One destination table of the portfolio: its type, its schema and its translations."""

    component: str
    schema: Schema
    build: BuildTranslations


class _Attribute(NamedTuple):
    """One supplemental attribute type, and what each association of it names."""

    kind: SiennaSupplementalAttribute
    table: PortfolioTable
    name_col: str
    describes: Callable[[pl.DataFrame], list[str]]


class PortfolioMapper:
    """Translates the tables of one portfolio into its destination tables.

    Each component table takes its share of the ids in turn. `fleet_source` names the base
    system devices that the ExistingDevices and the RetirementPotential of a technology list.
    """

    def __init__(self, recorder: ScopedRecorder, fleet_source: InvestmentsSource) -> None:
        self._recorder = recorder
        self._fleet_source = fleet_source
        self._next_id = _FIRST_ID

    def map_table(
        self, state: State, table: pl.DataFrame, spec: PortfolioTable
    ) -> pl.DataFrame | None:
        """Translate one source table, and take its share of the ids. An empty table maps none."""
        if table.is_empty():
            return None
        translated = apply_translations(table, spec.build(self._next_id), self._recorder)
        out = finalise(translated, spec.schema, self._recorder, spec.component)
        state.destination_tables[spec.component] = out
        self._next_id += out.height
        return out

    def map_supplemental_attributes(
        self, state: State, fleet: pl.DataFrame, buses: pl.DataFrame
    ) -> None:
        """The three attributes and their associations, numbered from the attribute counter.

        `fleet` holds the existing fleet of each technology, and `buses` the base system buses.
        """
        attributes = PortfolioMapper(self._recorder, self._fleet_source)
        sources = {
            SiennaSupplementalAttribute.EXISTING_DEVICES: fleet,
            SiennaSupplementalAttribute.RETIREMENT_POTENTIAL: fleet,
            SiennaSupplementalAttribute.TOPOLOGY_MAPPING: build_topology_source_table(buses),
        }
        specs = _build_attributes(self._fleet_source)
        mapped = [
            attributes._map_attribute(state, sources[kind], specs[kind])
            for kind in SUPPLEMENTAL_ATTRIBUTE_ORDER
        ]
        associations = [rows for rows in mapped if rows is not None]
        state.destination_tables[SUPPLEMENTAL_ATTRIBUTE_ASSOCIATIONS_TABLE] = (
            pl.concat(associations)
            if associations
            else pl.DataFrame(schema=SUPPLEMENTAL_ATTRIBUTE_ASSOCIATION_SCHEMA)
        )

    def _map_attribute(
        self, state: State, source: pl.DataFrame, attribute: _Attribute
    ) -> pl.DataFrame | None:
        """The association rows of one attribute type, or None when no row holds one."""
        out = self.map_table(state, source, attribute.table)
        if out is None:
            return None
        return build_association_rows(
            attribute.kind,
            out[SIENNA_ID_COLUMN].to_list(),
            source[attribute.name_col].to_list(),
            attribute.describes(source),
        )


def _build_attributes(
    source: InvestmentsSource,
) -> dict[SiennaSupplementalAttribute, _Attribute]:
    """Each attribute type, in the words of the source of its fleet."""
    return {
        SiennaSupplementalAttribute.EXISTING_DEVICES: _Attribute(
            SiennaSupplementalAttribute.EXISTING_DEVICES,
            PortfolioTable(
                SiennaSupplementalAttribute.EXISTING_DEVICES,
                EXISTING_DEVICES_DESTINATION_SCHEMA,
                partial(build_existing_devices_translations, source),
            ),
            name_col=TECHNOLOGY_NAME,
            describes=_list_technology_types,
        ),
        SiennaSupplementalAttribute.RETIREMENT_POTENTIAL: _Attribute(
            SiennaSupplementalAttribute.RETIREMENT_POTENTIAL,
            PortfolioTable(
                SiennaSupplementalAttribute.RETIREMENT_POTENTIAL,
                RETIREMENT_POTENTIAL_DESTINATION_SCHEMA,
                partial(build_retirement_potential_translations, source),
            ),
            name_col=TECHNOLOGY_NAME,
            describes=_list_technology_types,
        ),
        SiennaSupplementalAttribute.TOPOLOGY_MAPPING: _Attribute(
            SiennaSupplementalAttribute.TOPOLOGY_MAPPING,
            PortfolioTable(
                SiennaSupplementalAttribute.TOPOLOGY_MAPPING,
                TOPOLOGY_MAPPING_DESTINATION_SCHEMA,
                build_topology_mapping_translations,
            ),
            name_col=AREA_NAME,
            describes=_list_areas,
        ),
    }


def _list_technology_types(source: pl.DataFrame) -> list[str]:
    return source[TECHNOLOGY_TYPE].to_list()


def _list_areas(source: pl.DataFrame) -> list[str]:
    return [str(SiennaComponent.AREA)] * source.height
