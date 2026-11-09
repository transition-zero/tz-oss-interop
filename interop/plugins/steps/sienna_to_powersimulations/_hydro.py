"""A Sienna HydroTurbine and HydroReservoir, for a solve template that states neither.

The solve template gives a HydroDispatch the ``HydroDispatchRunOfRiverBudget`` formulation
and states no formulation for a HydroTurbine or a HydroReservoir. A HydroTurbine states
every field a HydroDispatch states, so it runs as one, and the reservoir stays out of the
solve.
"""

from __future__ import annotations

import logging
from typing import Any

from power_openapi_models.operations.models import HydroDispatch, HydroTurbine

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import Framework
from interop.plugins.shared.sienna_constants import (
    SIENNA_TYPE_ATTRIBUTE,
    SiennaComponent,
    SiennaHydroReservoirCol,
    SiennaTable,
)
from interop.plugins.shared.warning_text import name_a_few
from interop.ports.outbound.reporting import (
    DestinationField,
    EventKind,
    SourceField,
    TranslationEvent,
)

log = logging.getLogger(__name__)

# The fields a HydroTurbine states that a HydroDispatch does not, read from the SDK.
TURBINE_ONLY_FIELDS: tuple[str, ...] = tuple(
    sorted(set(HydroTurbine.model_fields) - set(HydroDispatch.model_fields))
)

_RUNS_AS_DISPATCH = (
    "the solve template has no formulation for a HydroTurbine, so it runs as a HydroDispatch"
)
_TURBINE_FIELD_NOTE = "a HydroDispatch states no {field}, so the solve does not read it"
_RESERVOIR_NOTE = (
    "the solve template has no formulation for a HydroReservoir, so the reservoir does not "
    "reach the solve and its turbines run on their own limits"
)


def map_turbine_to_dispatch(out: dict[str, Any], name: str, recorder: ScopedRecorder) -> None:
    """Record that a HydroTurbine runs as a HydroDispatch, and drop what a HydroDispatch lacks."""
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
    for field in TURBINE_ONLY_FIELDS:
        value = out.pop(field, None)
        if value is not None:
            _record_unread(recorder, name, field, value)


def _record_unread(recorder: ScopedRecorder, name: str, field: str, value: Any) -> None:
    recorder.append(
        TranslationEvent(
            kind=EventKind.NOT_MAPPED,
            sources=[_build_turbine_source(name, field, value)],
            note=_TURBINE_FIELD_NOTE.format(field=field),
        )
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
