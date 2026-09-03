"""Sienna -> PyPSA mapping constants: the reverse carrier mapping, the extensions.json
field names, and the lossy defaults the reverse applies.

Framework-neutral Sienna vocabulary lives in ``sienna_constants``; the PyPSA
destination tables, schemas, and column names live in ``pypsa_constants``.
"""

from __future__ import annotations

from interop.plugins.shared.pypsa_constants import (
    PyPSABusControl,
    PyPSACarrier,
)
from interop.plugins.shared.sienna_constants import (
    ACBusType,
    PrimeMover,
    SiennaComponent,
    ThermalFuel,
)

ASSUMED_HYDRO_EFFICIENCY_DISPATCH: float = 1.0
"""HydroDispatch carries no turbine efficiency (it is folded into hydro_budget and
lost), so the reverse inflow reconstruction assumes unity. Recorded as lossy."""

DEFAULT_HYDRO_MAX_HOURS: float = 1.0
"""HydroDispatch carries no reservoir capacity, so the PyPSA StorageUnit max_hours is
not recoverable. Falls back to the PyPSA default. Recorded as lossy."""

DEFAULT_STORAGE_EFFICIENCY: float = 1.0
"""HydroDispatch carries no round-trip efficiency, so the PyPSA StorageUnit
efficiency_store / efficiency_dispatch fall back to unity. Recorded as lossy."""

TIME_AT_STATUS_SENTINEL: float = 10000.0
"""``time_at_status`` the forward direction writes when ``up_time_before`` is unset (0).
The reverse reads this sentinel back as ``up_time_before = 0``. A genuine status duration
of exactly this many hours is indistinguishable from the sentinel; this is accepted, as
417 days of prior on-time is not a value a real PyPSA network carries."""


# Inverse of the forward carrier table. Several PyPSA carriers share a (prime_mover, fuel)
# pair (e.g. coal and lignite are both ST/COAL); the reverse derives the canonical carrier
# here, and the per-component ext.carrier (when present) overrides it so the original carrier
# round-trips exactly. See pypsa_carrier().
_THERMAL_CARRIER: dict[tuple[PrimeMover, ThermalFuel], PyPSACarrier] = {
    (PrimeMover.ST, ThermalFuel.COAL): PyPSACarrier.COAL,
    (PrimeMover.ST, ThermalFuel.NUCLEAR): PyPSACarrier.NUCLEAR,
    (PrimeMover.CC, ThermalFuel.NATURAL_GAS): PyPSACarrier.CCGT,
    (PrimeMover.GT, ThermalFuel.NATURAL_GAS): PyPSACarrier.OCGT,
    (PrimeMover.GT, ThermalFuel.DISTILLATE_FUEL_OIL): PyPSACarrier.OIL,
    (PrimeMover.BT, ThermalFuel.GEOTHERMAL): PyPSACarrier.GEOTHERMAL,
    (PrimeMover.ST, ThermalFuel.OTHER_BIOMASS_SOLIDS): PyPSACarrier.BIOMASS,
}

_RENEWABLE_DISPATCH_CARRIER: dict[PrimeMover, PyPSACarrier] = {
    PrimeMover.PVE: PyPSACarrier.SOLAR,
    PrimeMover.WT: PyPSACarrier.ONWIND,
    PrimeMover.WS: PyPSACarrier.OFFWIND,
    PrimeMover.HY: PyPSACarrier.ROR,
}

_RENEWABLE_NON_DISPATCH_CARRIER: dict[PrimeMover, PyPSACarrier] = {
    PrimeMover.PVE: PyPSACarrier.SOLAR_ROOFTOP,
}

_BUSTYPE_TO_CONTROL: dict[ACBusType, PyPSABusControl] = {
    ACBusType.PQ: PyPSABusControl.PQ,
    ACBusType.PV: PyPSABusControl.PV,
    ACBusType.REF: PyPSABusControl.SLACK,
    ACBusType.SLACK: PyPSABusControl.SLACK,
}


def pypsa_control(bustype: ACBusType) -> PyPSABusControl:
    """Invert the forward control -> bustype mapping to a PyPSA bus control mode.

    Raises KeyError for a bustype this pipeline does not map (e.g. ISOLATED), so an
    unsupported bus fails loudly rather than silently producing a wrong control mode.
    """
    return _BUSTYPE_TO_CONTROL[bustype]


def pypsa_carrier(
    sienna_type: SiennaComponent, prime_mover: PrimeMover, fuel: ThermalFuel | None
) -> PyPSACarrier:
    """Invert the forward carrier mapping to a canonical PyPSA carrier.

    Raises KeyError for an (prime_mover, fuel) / prime_mover combination this pipeline
    does not map, so an unsupported Sienna component fails loudly rather than silently
    producing a wrong carrier.
    """
    match sienna_type:
        case SiennaComponent.THERMAL_STANDARD:
            if fuel is None:
                raise KeyError(f"ThermalStandard requires a fuel_type, got {fuel!r}")
            return _THERMAL_CARRIER[(prime_mover, fuel)]
        case SiennaComponent.RENEWABLE_DISPATCH:
            return _RENEWABLE_DISPATCH_CARRIER[prime_mover]
        case SiennaComponent.RENEWABLE_NON_DISPATCH:
            return _RENEWABLE_NON_DISPATCH_CARRIER[prime_mover]
        case SiennaComponent.HYDRO_DISPATCH:
            return PyPSACarrier.HYDRO
        case SiennaComponent.ENERGY_RESERVOIR_STORAGE:
            return PyPSACarrier.PHS
        case (
            SiennaComponent.AC_BUS
            | SiennaComponent.AREA
            | SiennaComponent.ARC
            | SiennaComponent.POWER_LOAD
            | SiennaComponent.INTERRUPTIBLE_POWER_LOAD
            | SiennaComponent.TIME_SERIES_ASSOCIATION
            | SiennaComponent.LINE
            | SiennaComponent.MONITORED_LINE
            | SiennaComponent.TWO_TERMINAL_GENERIC_HVDC_LINE
        ):
            raise KeyError(f"{sienna_type} is not a generation component with a PyPSA carrier")
