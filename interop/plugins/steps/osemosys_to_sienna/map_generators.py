"""OSeMOSYS SupplyTechnology -> Sienna generators, as a part of the operations step."""

from __future__ import annotations

from typing import ClassVar

import polars as pl

from interop.core.extensions import ExtensionKind, append_extensions
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import StagedTimeSeriesCol
from interop.plugins.shared.osemosys_sienna_translations import (
    GENERATOR_NAME,
    GENERATOR_TYPE_MAPPINGS,
    SIENNA_TYPE,
    GeneratorSources,
    GeneratorTypeMapping,
    OperationsMapping,
    OperationsYear,
    StagedSeries,
    add_per_unit_series,
    build_generator_extensions,
    build_generators_source,
)
from interop.plugins.shared.osemosys_sienna_user_mappings import OsemosysSiennaCarrierMappings
from interop.plugins.shared.sienna_constants import SiennaComponent, SiennaSeriesName
from interop.plugins.shared.translation_runner import apply_translations, finalise


class OsemosysToSiennaMapGenerators(OperationsMapping):
    """Writes one Sienna generator for each supply technology of the fleet of the year."""

    step_name: ClassVar[str] = "osemosys_to_sienna_map_generators"

    def __init__(self, recorder: ScopedRecorder, mappings: OsemosysSiennaCarrierMappings) -> None:
        self._recorder = recorder
        self._mappings = mappings

    def map_components(self, state: State, operations: OperationsYear) -> None:
        source = build_generators_source(state, operations, self._mappings, self._recorder)
        if source.table.height == 0:
            return
        for mapping in GENERATOR_TYPE_MAPPINGS:
            self._map_type(state, source, mapping)
        append_extensions(
            state.destination_extensions,
            ExtensionKind.GENERATOR,
            build_generator_extensions(source.table),
        )

    def _map_type(
        self, state: State, source: GeneratorSources, mapping: GeneratorTypeMapping
    ) -> None:
        table = source.table.filter(pl.col(SIENNA_TYPE) == mapping.sienna_type)
        if table.height == 0:
            return
        destination = apply_translations(table, mapping.translations, self._recorder)
        generators = finalise(destination, mapping.schema, self._recorder, mapping.sienna_type)
        state.destination_tables[mapping.sienna_type] = generators
        names = table[GENERATOR_NAME].implode()
        series = source.series.filter(pl.col(StagedTimeSeriesCol.COMPONENT).is_in(names))
        if series.height == 0:
            return
        for attribute in _list_series_names(mapping.sienna_type):
            add_per_unit_series(
                state, StagedSeries(mapping.sienna_type, attribute, series), generators
            )


def _list_series_names(sienna_type: SiennaComponent) -> list[SiennaSeriesName]:
    """A HydroDispatch needs a budget, and the availability in each hour is that budget."""
    if sienna_type == SiennaComponent.HYDRO_DISPATCH:
        return [SiennaSeriesName.MAX_ACTIVE_POWER, SiennaSeriesName.HYDRO_BUDGET]
    return [SiennaSeriesName.MAX_ACTIVE_POWER]
