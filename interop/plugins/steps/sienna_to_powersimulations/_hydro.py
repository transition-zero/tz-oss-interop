"""A Sienna HydroTurbine and HydroReservoir, for a solve template that states neither.

The solve template gives a HydroDispatch the ``HydroDispatchRunOfRiverBudget`` formulation
and states no formulation for a HydroTurbine or a HydroReservoir. A HydroTurbine states
every field a HydroDispatch states, so it runs as one, and the reservoir stays out of the
solve.
"""

from __future__ import annotations

import logging
from typing import Any

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import Framework
from interop.plugins.shared.sienna_constants import (
    SIENNA_TYPE_ATTRIBUTE,
    SiennaComponent,
    SiennaHydroReservoirCol,
    SiennaTable,
)
from interop.plugins.shared.sienna_hydro_turbine import (
    TURBINE_ONLY_FIELDS,
    UnreadTurbineField,
    list_stated_turbine_fields,
)
from interop.plugins.shared.warning_text import name_a_few
from interop.ports.outbound.reporting import (
    DestinationField,
    EventKind,
    SourceField,
    TranslationEvent,
)

log = logging.getLogger(__name__)

_RUNS_AS_DISPATCH = (
    "the solve template has no formulation for a HydroTurbine, so it runs as a HydroDispatch"
)
_TURBINE_FIELD_NOTE = "a HydroDispatch states no {field}, so the solve does not read it"
_RESERVOIR_NOTE = (
    "the solve template has no formulation for a HydroReservoir, so the reservoir does not "
    "reach the solve and its turbines run on their own limits"
)


def record_turbine_as_dispatch(name: str, recorder: ScopedRecorder) -> None:
    """Record that a HydroTurbine runs as a HydroDispatch."""
    recorder.append(
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                _build_turbine_source(
                    name, SIENNA_TYPE_ATTRIBUTE, SiennaComponent.HYDRO_TURBINE.value
                )
            ],
            destinations=[
                DestinationField(
                    Framework.POWER_SIMULATIONS,
                    SiennaComponent.HYDRO_DISPATCH.value,
                    name,
                    SIENNA_TYPE_ATTRIBUTE,
                    SiennaComponent.HYDRO_DISPATCH.value,
                )
            ],
            derivation=_RUNS_AS_DISPATCH,
        )
    )


def drop_turbine_only_fields(out: dict[str, Any], name: str) -> list[UnreadTurbineField]:
    """Take off one turbine row each field a HydroDispatch lacks, and return those it stated."""
    unread = list_stated_turbine_fields(out, name, TURBINE_ONLY_FIELDS)
    for field in TURBINE_ONLY_FIELDS:
        out.pop(field, None)
    return unread


def report_unread_turbine_fields(
    unread: list[UnreadTurbineField], recorder: ScopedRecorder
) -> None:
    """Record each turbine field that the solve does not read, and warn once naming a few."""
    if not unread:
        return
    for one in unread:
        recorder.append(
            TranslationEvent(
                kind=EventKind.NOT_MAPPED,
                sources=[_build_turbine_source(one.turbine, one.field, one.value)],
                note=_TURBINE_FIELD_NOTE.format(field=one.field),
            )
        )
    log.warning(
        "power-simulations: %d HydroTurbine(s) state %s, which a HydroDispatch does not state, "
        "so the solve does not read them: %s",
        len({one.turbine for one in unread}),
        ", ".join(sorted({one.field for one in unread})),
        name_a_few(sorted({one.turbine for one in unread})),
    )


def _build_turbine_source(name: str, attribute: str, value: Any) -> SourceField:
    return SourceField(
        Framework.SIENNA, SiennaComponent.HYDRO_TURBINE.value, name, attribute, value
    )


def report_unsolved_reservoirs(state: State, recorder: ScopedRecorder) -> None:
    """Record each HydroReservoir the solve leaves out, and warn once naming a few."""
    reservoirs = state.source_topology.get(SiennaTable.RESERVOIRS)
    if reservoirs is None:
        return
    names: list[str] = (
        reservoirs.select(SiennaHydroReservoirCol.NAME).collect().to_series().to_list()
    )
    if not names:
        return
    for name in names:
        recorder.append(
            TranslationEvent(
                kind=EventKind.COMPONENT_SKIPPED,
                sources=[
                    SourceField(
                        Framework.SIENNA, SiennaComponent.HYDRO_RESERVOIR.value, name, None, None
                    )
                ],
                note=_RESERVOIR_NOTE,
            )
        )
    log.warning(
        "power-simulations: %d HydroReservoir(s) have no formulation in the solve template, "
        "so each is left out of the solve: %s",
        len(names),
        name_a_few(sorted(names)),
    )
