"""The fuel buses that a load or a plant draws from, and that no technology supplies.

A PyPSA network balances each bus in each hour, so a load on such a bus cannot be met, and a
plant that burns its fuel cannot run.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence

from interop.core.extensions import ConversionExtension, GeneratorExtension, LoadExtension
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.osemosys_canonical.constants import FUEL
from interop.plugins.shared.osemosys_sienna_constants import OSEMOSYS_TO_SIENNA_PIPELINE
from interop.plugins.shared.osemosys_sienna_translations._events import build_osemosys_field
from interop.plugins.shared.pypsa_constants import LINK_FURTHER_PORTS
from interop.plugins.shared.warning_text import name_a_few
from interop.ports.outbound.reporting import EventKind, TranslationEvent

log = logging.getLogger(__name__)

_WARNING = (
    "%s: %d fuel bus(es) have a load or a plant that draws from them, and no technology of the "
    "operations year supplies them, so a PyPSA network cannot meet that demand. Buses: %s"
)


def report_unsupplied_fuel_buses(
    suppliers: Sequence[GeneratorExtension | ConversionExtension],
    loads: Sequence[LoadExtension],
    plants: Sequence[GeneratorExtension],
    recorder: ScopedRecorder,
) -> None:
    """Record NOT_MAPPED for each fuel bus with a draw and no supply, and warn once."""
    supplied = _list_supplied_buses(suppliers)
    load_names = _build_draws((load.bus, load.name) for load in loads)
    plant_names = _build_draws(
        (bus, plant.name) for plant in plants for bus in plant.fuel_buses or {}
    )
    unsupplied = sorted((set(load_names) | set(plant_names)) - supplied)
    for bus in unsupplied:
        recorder.append(_build_event(bus, load_names.get(bus, []), plant_names.get(bus, [])))
    if unsupplied:
        log.warning(_WARNING, OSEMOSYS_TO_SIENNA_PIPELINE, len(unsupplied), name_a_few(unsupplied))


def _list_supplied_buses(
    suppliers: Sequence[GeneratorExtension | ConversionExtension],
) -> set[str | None]:
    """The bus of each fuel generator, and each bus that a conversion puts a fuel out at."""
    supplied: set[str | None] = set()
    for record in suppliers:
        if isinstance(record, GeneratorExtension):
            supplied.add(record.bus)
            continue
        supplied.add(record.bus1)
        for bus_field, efficiency_field in LINK_FURTHER_PORTS:
            if (getattr(record, efficiency_field) or 0.0) > 0:
                supplied.add(getattr(record, bus_field))
    supplied.discard(None)
    return supplied


def _build_draws(pairs: Iterable[tuple[str | None, str]]) -> dict[str, list[str]]:
    """The names of the components that draw from each bus."""
    draws: dict[str, list[str]] = {}
    for bus, name in pairs:
        if bus is not None:
            draws.setdefault(bus, []).append(name)
    return {bus: sorted(names) for bus, names in draws.items()}


def _build_event(bus: str, loads: list[str], plants: list[str]) -> TranslationEvent:
    drawn = (("load", loads), ("plant", plants))
    parts = [f"the {noun}(s) {', '.join(names)}" for noun, names in drawn if names]
    return TranslationEvent(
        kind=EventKind.NOT_MAPPED,
        sources=[build_osemosys_field(FUEL, bus)],
        note=(
            f"{' and '.join(parts)} draw from the bus, and no technology of the operations year "
            "supplies it; a PyPSA network balances each bus in each hour, so it cannot meet "
            "that demand"
        ),
    )
