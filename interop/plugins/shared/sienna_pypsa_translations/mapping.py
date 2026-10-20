"""Row-level helpers shared by the Sienna -> PyPSA generator and storage mapping steps.

Both steps resolve bus ids to names and read the proportional term out of a Sienna
operation cost. Keeping these here lets either step reuse them without importing the
other (the composite imports both, so a step-to-step import would cycle).
"""

from __future__ import annotations

from typing import Any

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.constants import Framework
from interop.plugins.shared.sienna_constants import (
    SiennaACBusCol,
    SiennaComponent,
    SiennaGeneratorCol,
    SiennaLineCol,
    SiennaStructField,
    SiennaTable,
    SiennaUnitSystem,
)
from interop.plugins.shared.sienna_pypsa_translations.constants import SIENNA_TO_PYPSA
from interop.plugins.shared.translation_runner import SkipReport
from interop.ports.errors import UserInputError


def extendable_floor(rated: float, is_extendable: bool | None) -> float | None:
    return rated if is_extendable else None


def build_power_units_skip_report(
    component: str, plural: str, name_col: str, supported: SiennaUnitSystem
) -> SkipReport:
    return SkipReport(
        pipeline=SIENNA_TO_PYPSA,
        framework=Framework.SIENNA,
        component=component,
        name_col=name_col,
        reason="state a power basis this reader does not convert",
        counted_noun=plural,
        note=(
            lambda row: (
                f"power_units is {row[SiennaStructField.POWER_UNITS]}; "
                f"tz-oss-interop reads {supported.value} for this type"
            )
        ),
        attribute_col=SiennaStructField.POWER_UNITS,
    )


def express_power_units_kept(
    supported: SiennaUnitSystem, handled: list[SiennaComponent] | None = None
) -> pl.Expr:
    """Keep a row that states the supported basis. A row of a type outside handled stays."""
    stated = pl.col(SiennaStructField.POWER_UNITS) == supported.value
    if handled is None:
        return stated
    other_type = ~pl.col(SiennaGeneratorCol.SIENNA_TYPE).is_in([t.value for t in handled])
    return other_type | stated


def reject_unsupported_parameter_units(row: dict[str, Any]) -> None:
    """Raise when a Line states r, x, b and g in a basis other than COMPONENT_BASE.

    parameter_units is optional in SiennaSchemas 0.2 and defaults to COMPONENT_BASE.
    """
    stated = row.get(SiennaLineCol.PARAMETER_UNITS)
    if stated is None:
        return
    if SiennaUnitSystem(stated) is not SiennaUnitSystem.COMPONENT_BASE:
        raise UserInputError(
            f"{row[SiennaGeneratorCol.SIENNA_TYPE]} {row[SiennaGeneratorCol.NAME]!r} states "
            f"parameter_units {stated}; tz-oss-interop reads {SiennaUnitSystem.COMPONENT_BASE}"
        )


def per_unit_of(value: float, base_power: float) -> float:
    """Express ``value`` (MW) as a per-unit fraction of ``base_power``.

    A zero-capacity component (``base_power == 0``, a valid placeholder generator in PyPSA)
    has no meaningful per-unit value, so the fraction is 0.0 rather than a division by zero.
    """
    return value / base_power if base_power else 0.0


# PyPSA's own default, for a component that has no capacity to divide a rating by.
_ZERO_CAPACITY_P_MAX_PU: float = 1.0
# The writer multiplied a per-unit value by the base. Twelve digits remove the floating point
# error of that product and keep every digit that a source states.
_RATING_DIGITS: int = 12


def rated_per_unit(rating: float, base_power: float) -> float:
    """Express a NATURAL_UNITS rating (MVA) as a fraction of ``base_power``."""
    if not base_power:
        return _ZERO_CAPACITY_P_MAX_PU
    return round(rating / base_power, _RATING_DIGITS)


def variable_proportional_term(operation_cost: dict[str, Any], variable_key: str) -> float:
    variable = operation_cost[variable_key]
    return float(
        variable[SiennaStructField.VALUE_CURVE][SiennaStructField.FUNCTION_DATA][
            SiennaStructField.PROPORTIONAL_TERM
        ]
    )


def bus_id_to_name(state: State) -> dict[int, str]:
    buses = state.source_topology.get(SiennaTable.BUSES)
    if buses is None:
        return {}
    frame = buses.select([SiennaACBusCol.ID, SiennaACBusCol.NAME]).collect()
    return {row[SiennaACBusCol.ID]: row[SiennaACBusCol.NAME] for row in frame.iter_rows(named=True)}


def bus_id_to_v_nom(state: State) -> dict[int, float]:
    """Map each bus id to its nominal voltage (kV), for per-unit -> Ohm line conversions."""
    buses = state.source_topology.get(SiennaTable.BUSES)
    if buses is None:
        return {}
    frame = buses.select([SiennaACBusCol.ID, SiennaACBusCol.BASE_VOLTAGE]).collect()
    return {
        row[SiennaACBusCol.ID]: float(row[SiennaACBusCol.BASE_VOLTAGE])
        for row in frame.iter_rows(named=True)
    }
