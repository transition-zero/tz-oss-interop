"""The units of a model, from the `units:` part of the user mappings file.

The canonical stage keeps each value in the unit of the model. Sienna states capacity in MW,
energy in MWh and emissions in t. A unit that a conversion needs and that the file does not
state stops the run, because it is a missing parameter and not model data.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.osemosys_canonical.canonical_stage import build_table_key
from interop.plugins.shared.osemosys_canonical.constants import (
    MetadataColumn,
    MetadataTable,
    TableKind,
)
from interop.plugins.shared.osemosys_sienna_constants import UnitQuantity
from interop.ports.errors import UserInputError

# A value that a conversion multiplies: one number, or a column of a table.
Quantity = TypeVar("Quantity", float, pl.Expr)

_MEGA = 1e6
_JOULES_PER_MWH = 3.6e9

_MW_PER_CAPACITY_UNIT: dict[str, float] = {"kW": 1e-3, "MW": 1.0, "GW": 1e3, "TW": 1e6}
_MWH_PER_ENERGY_UNIT: dict[str, float] = {
    "kWh": 1e-3,
    "MWh": 1.0,
    "GWh": 1e3,
    "TWh": 1e6,
    "kJ": 1e3 / _JOULES_PER_MWH,
    "MJ": 1e6 / _JOULES_PER_MWH,
    "GJ": 1e9 / _JOULES_PER_MWH,
    "TJ": 1e12 / _JOULES_PER_MWH,
    "PJ": 1e15 / _JOULES_PER_MWH,
    "EJ": 1e18 / _JOULES_PER_MWH,
}
_TONNES_PER_EMISSION_UNIT: dict[str, float] = {"t": 1.0, "kt": 1e3, "Mt": _MEGA, "Gt": 1e9}
_CURRENCY_SCALE_WORDS: dict[str, float] = {
    "thousand": 1e3,
    "million": _MEGA,
    "billion": 1e9,
    "k": 1e3,
    "M": _MEGA,
    "bn": 1e9,
}
_CURRENCY = re.compile(r"^(?:(?P<word>\S+)\s+)?(?P<prefix>k|M|bn)?(?P<code>[A-Z]{3})$")


@dataclass(frozen=True)
class ModelUnits:
    """The factor that converts one unit of the model to the Sienna unit, or None if unstated.

    `dollars_per_currency` is the scale of the currency only, for example 1e6 for
    `million USD`. The step does not convert between currencies.
    """

    mw_per_capacity: float | None = None
    mwh_per_energy: float | None = None
    capacity_unit: str | None = None
    energy_unit: str | None = None
    emissions_unit: str | None = None
    tonnes_per_emission: float | None = None
    dollars_per_currency: float | None = None
    currency_code: str | None = None
    currency_year: int | None = None

    def convert_capacity_to_mw(self, value: Quantity) -> Quantity:
        return value * _require_factor(self.mw_per_capacity, UnitQuantity.CAPACITY)

    def convert_energy_to_mwh(self, value: Quantity) -> Quantity:
        return value * _require_factor(self.mwh_per_energy, UnitQuantity.ENERGY)

    def convert_emissions_to_tonnes(self, value: Quantity) -> Quantity:
        return value * _require_factor(self.tonnes_per_emission, UnitQuantity.EMISSIONS)

    def convert_currency_to_dollars(self, value: Quantity) -> Quantity:
        return value * _require_factor(self.dollars_per_currency, UnitQuantity.CURRENCY)

    def convert_cost_per_energy_to_dollars_per_mwh(self, value: Quantity) -> Quantity:
        return self.convert_currency_to_dollars(value) / self.convert_energy_to_mwh(1.0)

    def convert_cost_per_capacity_to_dollars_per_mw(self, value: Quantity) -> Quantity:
        return self.convert_currency_to_dollars(value) / self.convert_capacity_to_mw(1.0)

    def convert_emissions_per_energy_to_tonnes_per_mwh(self, value: Quantity) -> Quantity:
        return self.convert_emissions_to_tonnes(value) / self.convert_energy_to_mwh(1.0)


def express_converted(
    table: pl.DataFrame, column: str, convert: Callable[[pl.Expr], pl.Expr]
) -> pl.Expr:
    """A column in Sienna units. A column that holds no value but zero or null needs no unit."""
    if not table.select((pl.col(column).fill_null(0.0) != 0).any()).item():
        return pl.col(column)
    return convert(pl.col(column))


def parse_units(state: State) -> ModelUnits:
    """The units that `metadata/units` states. A unit that no factor table holds stops the run."""
    stated = _read_stated_units(state)
    currency = stated.get(UnitQuantity.CURRENCY)
    currency_year = stated.get(UnitQuantity.CURRENCY_YEAR)
    return ModelUnits(
        mw_per_capacity=_parse_unit(stated, UnitQuantity.CAPACITY, _MW_PER_CAPACITY_UNIT),
        mwh_per_energy=_parse_unit(stated, UnitQuantity.ENERGY, _MWH_PER_ENERGY_UNIT),
        capacity_unit=stated.get(UnitQuantity.CAPACITY),
        energy_unit=stated.get(UnitQuantity.ENERGY),
        emissions_unit=stated.get(UnitQuantity.EMISSIONS),
        tonnes_per_emission=_parse_unit(stated, UnitQuantity.EMISSIONS, _TONNES_PER_EMISSION_UNIT),
        dollars_per_currency=None if currency is None else _parse_currency_scale(currency),
        currency_code=None if currency is None else _parse_currency_code(currency),
        currency_year=None if currency_year is None else _parse_currency_year(currency_year),
    )


def _read_stated_units(state: State) -> dict[str, str]:
    table = state.source_topology.get(build_table_key(TableKind.METADATA, MetadataTable.UNITS))
    if table is None:
        return {}
    rows = table.select(MetadataColumn.QUANTITY, MetadataColumn.UNIT).collect().rows()
    return {str(quantity): str(unit) for quantity, unit in rows}


def _parse_unit(
    stated: dict[str, str], quantity: UnitQuantity, factors: dict[str, float]
) -> float | None:
    unit = stated.get(quantity)
    if unit is None:
        return None
    factor = factors.get(unit.strip())
    if factor is None:
        raise _build_unknown_unit_error(quantity, unit, sorted(factors))
    return factor


def _parse_currency_year(currency_year: str) -> int:
    try:
        return int(currency_year)
    except ValueError:
        raise UserInputError(
            f"`units: {UnitQuantity.CURRENCY_YEAR}` in the user mappings file is "
            f"{currency_year!r}, which is not a whole year such as 2021."
        ) from None


def _parse_currency_scale(currency: str) -> float:
    match = _require_currency_match(currency)
    word, prefix = match.group("word"), match.group("prefix")
    if word is not None and prefix is not None:
        raise _build_unknown_currency_error(currency)
    scale = word or prefix
    if scale is None:
        return 1.0
    if scale not in _CURRENCY_SCALE_WORDS:
        raise _build_unknown_currency_error(currency)
    return _CURRENCY_SCALE_WORDS[scale]


def _parse_currency_code(currency: str) -> str:
    return _require_currency_match(currency).group("code")


def _require_currency_match(currency: str) -> re.Match[str]:
    match = _CURRENCY.match(currency.strip())
    if match is None:
        raise _build_unknown_currency_error(currency)
    return match


def _require_factor(factor: float | None, quantity: UnitQuantity) -> float:
    if factor is None:
        raise UserInputError(
            f"The user mappings file states no `units: {quantity}` under `osemosys:`, and the "
            f"translation needs it to convert the {quantity} values of the model. Add "
            f"`units: {{{quantity}: ...}}` to the file."
        )
    return factor


def _build_unknown_unit_error(
    quantity: UnitQuantity, unit: str, known: list[str]
) -> UserInputError:
    return UserInputError(
        f"`units: {quantity}` in the user mappings file is {unit!r}, which tz-oss-interop "
        f"cannot convert. Use one of: {', '.join(known)}."
    )


def _build_unknown_currency_error(currency: str) -> UserInputError:
    scales = ", ".join(_CURRENCY_SCALE_WORDS)
    return UserInputError(
        f"`units: {UnitQuantity.CURRENCY}` in the user mappings file is {currency!r}. Give a "
        f"three-letter code such as USD, a scale and a code such as 'million USD', or a code "
        f"with the prefix k, M or bn such as MUSD. The scales are: {scales}."
    )
