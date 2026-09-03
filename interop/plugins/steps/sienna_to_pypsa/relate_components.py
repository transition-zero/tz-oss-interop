from __future__ import annotations

from typing import ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.pypsa_constants import PyPSABusCol, PyPSADestinationTable
from interop.plugins.shared.sienna_constants import SiennaACBusCol, SiennaTable
from interop.plugins.shared.sienna_pypsa_translations.reporters import BusReporter

_AREA_COL = "_area"


class SiennaToPypsaRelateComponents(TranslationStep):
    """Resolves the Sienna ACBus -> Area reference into each PyPSA bus's location.

    The map step produces buses with an empty location; this step fills it from the
    bus's referenced Area name, keeping the cross-component relation auditable under its
    own step name rather than folded into the per-bus field mapping.
    """

    name: ClassVar[str] = "sienna_to_pypsa_relate_components"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def run(self, state: State, params: BaseModel | None) -> State:
        source = state.source_topology.get(SiennaTable.BUSES)
        buses = state.destination_tables.get(PyPSADestinationTable.BUSES)
        if source is None or buses is None:
            return state

        located = source.select([SiennaACBusCol.NAME, SiennaACBusCol.AREA]).collect()
        name_to_area = {
            row[SiennaACBusCol.NAME]: row[SiennaACBusCol.AREA]
            for row in located.iter_rows(named=True)
            if row[SiennaACBusCol.AREA] is not None
        }
        if not name_to_area:
            return state

        reporter = BusReporter(self._recorder)
        for name, area in name_to_area.items():
            reporter.record_location(name, area)

        locations = pl.DataFrame(
            {
                PyPSABusCol.NAME: list(name_to_area.keys()),
                _AREA_COL: list(name_to_area.values()),
            },
            schema={PyPSABusCol.NAME: pl.Utf8, _AREA_COL: pl.Utf8},
        )
        state.destination_tables[PyPSADestinationTable.BUSES] = (
            buses.join(locations, on=PyPSABusCol.NAME, how="left")
            .with_columns(
                pl.coalesce([pl.col(_AREA_COL), pl.col(PyPSABusCol.LOCATION)]).alias(
                    PyPSABusCol.LOCATION
                )
            )
            .drop(_AREA_COL)
        )
        return state
