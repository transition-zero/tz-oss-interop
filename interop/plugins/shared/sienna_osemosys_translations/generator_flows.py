"""What one unit of the activity of a technology takes in and puts out, for each of its modes.

A Sienna generator rates in megawatts of electricity, so the forward leg divided every value
of its technology by the electricity output ratio of that technology. No Sienna field states
that ratio, so this leg writes it as 1 and every other flow as the quotient that the forward
leg left. The electricity output of the held mode is therefore always 1.

The `fuel_buses` and the `output_buses` of the record state the other flows of the held mode,
each keyed by the bus of its fuel. Each other mode states its own flows as an
`operating_modes` entry, keyed by the name of the fuel.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, NamedTuple

import polars as pl

from interop.core.extensions import GeneratorExtension, OperatingMode
from interop.plugins.shared.constants import EXTENSIONS_PREFIX
from interop.plugins.shared.osemosys_canonical.constants import (
    FUEL,
    OPERATING_MODE,
    REGION,
    TECHNOLOGY,
    VALUE_COL,
    FlowParameter,
)
from interop.plugins.shared.sienna_osemosys_translations.buses import build_bus_members
from interop.plugins.shared.sienna_osemosys_translations.generator_columns import (
    HELD_MODE,
    SOURCE_COMPONENT,
)
from interop.plugins.shared.sienna_osemosys_translations.generator_modes import (
    list_mode_records,
)
from interop.plugins.shared.sienna_osemosys_translations.generators import GeneratorSources

# The canonical parameter that the row fills, and the record field that it comes from.
PARAMETER = "parameter"
SOURCE_ATTRIBUTE = "source_attribute"
# The whole electricity output ratio, which the forward leg divided every other value by.
WHOLE_OUTPUT_RATIO = 1.0
# The record fields that the flows of a technology come from.
FLOW_MAPPED_FIELDS = ("fuel_buses", "output_buses", "operating_modes")

FLOWS_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    REGION: pl.Utf8,
    TECHNOLOGY: pl.Utf8,
    FUEL: pl.Utf8,
    OPERATING_MODE: pl.Utf8,
    PARAMETER: pl.Utf8,
    VALUE_COL: pl.Float64,
    SOURCE_COMPONENT: pl.Utf8,
    SOURCE_ATTRIBUTE: pl.Utf8,
}

_INPUT_RATIOS_FIELD = "input_ratios"
_OUTPUT_RATIOS_FIELD = "output_ratios"
_FUEL_BUSES_FIELD = "fuel_buses"
_OUTPUT_BUSES_FIELD = "output_buses"
_MODES_FIELD = "operating_modes"


class _Flow(NamedTuple):
    """One activity ratio of one mode, before the table holds it."""

    fuel: str
    mode: str
    parameter: str
    value: float
    attribute: str | None


def build_generator_flows(sources: GeneratorSources) -> pl.DataFrame:
    """One row for each fuel that each mode of each technology takes in or puts out."""
    rows = [
        _build_row(row, flow)
        for row in sources.table.iter_rows(named=True)
        for flow in _list_flows(
            row, sources.records.get_fields(row[TECHNOLOGY], FLOW_MAPPED_FIELDS)
        )
    ]
    return pl.DataFrame(rows, schema=FLOWS_SCHEMA)


def _build_row(generator: dict[str, Any], flow: _Flow) -> dict[str, Any]:
    return {
        REGION: generator[REGION],
        TECHNOLOGY: generator[TECHNOLOGY],
        FUEL: flow.fuel,
        OPERATING_MODE: flow.mode,
        PARAMETER: flow.parameter,
        VALUE_COL: flow.value,
        SOURCE_COMPONENT: generator[SOURCE_COMPONENT],
        SOURCE_ATTRIBUTE: flow.attribute,
    }


def _list_flows(row: dict[str, Any], record: GeneratorExtension) -> Iterator[_Flow]:
    """The flows of the held mode, then the flows that each other mode states."""
    held = str(row[HELD_MODE])
    yield _Flow(str(row[FUEL]), held, FlowParameter.OUTPUT_ACTIVITY_RATIO, WHOLE_OUTPUT_RATIO, None)
    yield from _list_bus_flows(
        record.fuel_buses, held, FlowParameter.INPUT_ACTIVITY_RATIO, _FUEL_BUSES_FIELD
    )
    yield from _list_bus_flows(
        record.output_buses, held, FlowParameter.OUTPUT_ACTIVITY_RATIO, _OUTPUT_BUSES_FIELD
    )
    for mode in list_mode_records(record):
        if mode.mode != held:
            yield from _list_mode_flows(mode)


def _list_bus_flows(
    buses: dict[str, float] | None, mode: str, parameter: str, field: str
) -> Iterator[_Flow]:
    """A record keys a flow of the held mode by the bus of its fuel, `<region>/<fuel>`."""
    for bus, ratio in sorted((buses or {}).items()):
        attribute = f"{EXTENSIONS_PREFIX}{field}.{bus}"
        yield _Flow(build_bus_members(bus).fuel, mode, parameter, ratio, attribute)


def _list_mode_flows(mode: OperatingMode) -> Iterator[_Flow]:
    """An `operating_modes` entry keys a flow of its own mode by the name of the fuel."""
    yield from _list_ratios(
        mode, mode.input_ratios, FlowParameter.INPUT_ACTIVITY_RATIO, _INPUT_RATIOS_FIELD
    )
    yield from _list_ratios(
        mode, mode.output_ratios, FlowParameter.OUTPUT_ACTIVITY_RATIO, _OUTPUT_RATIOS_FIELD
    )


def _list_ratios(
    mode: OperatingMode, ratios: dict[str, float] | None, parameter: str, field: str
) -> Iterator[_Flow]:
    for fuel, ratio in sorted((ratios or {}).items()):
        attribute = f"{EXTENSIONS_PREFIX}{_MODES_FIELD}.{mode.mode}.{field}.{fuel}"
        yield _Flow(fuel, mode.mode, parameter, ratio, attribute)
