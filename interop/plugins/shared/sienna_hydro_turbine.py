"""The fields that a Sienna HydroTurbine states and a HydroDispatch does not."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, NamedTuple

from power_openapi_models.operations.models import HydroDispatch, HydroTurbine

# The fields a HydroTurbine states that a HydroDispatch does not, read from the SDK.
TURBINE_ONLY_FIELDS: tuple[str, ...] = tuple(
    sorted(set(HydroTurbine.model_fields) - set(HydroDispatch.model_fields))
)


class UnreadTurbineField(NamedTuple):
    """One field a HydroTurbine states that the destination does not read."""

    turbine: str
    field: str
    value: Any


def list_stated_turbine_fields(
    row: Mapping[str, Any], name: str, fields: Iterable[str]
) -> list[UnreadTurbineField]:
    """Each of the named fields that one turbine row states, with its value."""
    stated = [UnreadTurbineField(name, field, row.get(field)) for field in fields]
    return [one for one in stated if one.value is not None]
