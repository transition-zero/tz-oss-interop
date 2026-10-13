from __future__ import annotations

from collections.abc import Callable
from typing import NamedTuple

import polars as pl

from interop.plugins.shared.osemosys_canonical.constants import (
    FUEL,
    LOCATION_SEPARATOR,
    OPERATING_MODE,
    REGION,
    TECHNOLOGY,
    VALUE_COL,
    FlowParameter,
    TechnologyKind,
)
from interop.plugins.shared.osemosys_canonical.object_rows import MemberKey

_FLOW_COLUMNS = [REGION, TECHNOLOGY, FUEL, OPERATING_MODE]
_STORAGE_COLUMNS = [REGION, TECHNOLOGY]
_REGION_LOCATION_RULE = (
    "a technology takes the location of its region when no row gives a location to its fuels"
)
_FUEL_LOCATION_RULE = "the locations of the fuels that it takes in and puts out"
_FLOW_DIRECTIONS = {
    FlowParameter.INPUT_ACTIVITY_RATIO: True,
    FlowParameter.OUTPUT_ACTIVITY_RATIO: False,
}
_STORAGE_PARAMETERS = (FlowParameter.TECHNOLOGY_TO_STORAGE, FlowParameter.TECHNOLOGY_FROM_STORAGE)


class FuelFlow(NamedTuple):
    mode: str
    is_input: bool
    fuel: str


class FuelAnnotation(NamedTuple):
    """`row_location` is the location that an `objects:` row gives the fuel, if any."""

    row_location: str | None
    is_electricity: bool


class LocatedFlow(NamedTuple):
    flow: FuelFlow
    fuel: FuelAnnotation


class TechnologyStructure(NamedTuple):
    flows: list[LocatedFlow]
    has_storage: bool

    @property
    def inputs(self) -> list[FuelAnnotation]:
        return [located.fuel for located in self.flows if located.flow.is_input]

    @property
    def outputs(self) -> list[FuelAnnotation]:
        return [located.fuel for located in self.flows if not located.flow.is_input]


class Inference(NamedTuple):
    value: str
    rule: str


class KindRule(NamedTuple):
    kind: TechnologyKind
    is_match: Callable[[TechnologyStructure], bool]
    rule: str


def build_technology_flows(canonical: dict[str, pl.LazyFrame]) -> dict[MemberKey, list[FuelFlow]]:
    flows: dict[MemberKey, list[FuelFlow]] = {}
    for parameter, is_input in _FLOW_DIRECTIONS.items():
        for region, technology, fuel, mode in _build_positive_keys(canonical, parameter).rows():
            flows.setdefault(MemberKey(region, technology), []).append(
                FuelFlow(mode, is_input, fuel)
            )
    return flows


def build_storage_technologies(canonical: dict[str, pl.LazyFrame]) -> set[MemberKey]:
    return {
        MemberKey(*row)
        for parameter in _STORAGE_PARAMETERS
        for row in _build_positive_keys(canonical, parameter).rows()
    }


def _build_positive_keys(canonical: dict[str, pl.LazyFrame], parameter: str) -> pl.DataFrame:
    """A parameter table can hold billions of rows, so collect only the distinct key columns."""
    columns = _STORAGE_COLUMNS if parameter in _STORAGE_PARAMETERS else _FLOW_COLUMNS
    table = canonical.get(parameter)
    if table is None:
        return pl.DataFrame(schema=dict.fromkeys(columns, pl.Utf8))
    return table.filter(pl.col(VALUE_COL) > 0).select(columns).unique().collect()


def choose_kind(structure: TechnologyStructure) -> Inference | None:
    for rule in _KIND_RULES:
        if rule.is_match(structure):
            return Inference(rule.kind.value, rule.rule)
    return None


def build_technology_location(structure: TechnologyStructure, region: str) -> Inference:
    located = sorted(structure.flows, key=_build_location_order)
    locations = _list_row_locations([flow.fuel for flow in located])
    if not locations:
        return Inference(region, _REGION_LOCATION_RULE)
    return Inference(LOCATION_SEPARATOR.join(locations), _FUEL_LOCATION_RULE)


def _build_location_order(located: LocatedFlow) -> tuple[int, str, bool, str]:
    """A string sort puts mode 10 before mode 2, so sort a whole-number mode by its number."""
    mode = located.flow.mode
    number = int(mode) if mode.isdecimal() else -1
    return number, mode, not located.flow.is_input, located.fuel.row_location or ""


def _is_storage_technology(structure: TechnologyStructure) -> bool:
    return structure.has_storage


def _is_aggregate_transport_technology(structure: TechnologyStructure) -> bool:
    inputs = [fuel for fuel in structure.inputs if fuel.is_electricity]
    outputs = [fuel for fuel in structure.outputs if fuel.is_electricity]
    return bool(inputs) and bool(outputs) and len(_list_row_locations([*inputs, *outputs])) > 1


def _is_supply_technology(structure: TechnologyStructure) -> bool:
    puts_out_electricity = any(fuel.is_electricity for fuel in structure.outputs)
    return puts_out_electricity and not any(fuel.is_electricity for fuel in structure.inputs)


def _is_fuel_supply(structure: TechnologyStructure) -> bool:
    puts_out_other = any(not fuel.is_electricity for fuel in structure.outputs)
    return puts_out_other and not structure.inputs


def _is_export(structure: TechnologyStructure) -> bool:
    return bool(structure.inputs) and not structure.outputs


def _is_conversion(structure: TechnologyStructure) -> bool:
    locations = _list_row_locations([located.fuel for located in structure.flows])
    return bool(structure.inputs) and bool(structure.outputs) and len(locations) <= 1


def _list_row_locations(fuels: list[FuelAnnotation]) -> list[str]:
    rows = [fuel.row_location for fuel in fuels if fuel.row_location is not None]
    return list(dict.fromkeys(rows))


# The first rule that fits wins, so a new order changes the kind of some technologies.
_KIND_RULES = (
    KindRule(
        TechnologyKind.STORAGE_TECHNOLOGY,
        _is_storage_technology,
        f"it connects to a storage through {FlowParameter.TECHNOLOGY_TO_STORAGE} or "
        f"{FlowParameter.TECHNOLOGY_FROM_STORAGE}",
    ),
    KindRule(
        TechnologyKind.AGGREGATE_TRANSPORT_TECHNOLOGY,
        _is_aggregate_transport_technology,
        "it takes in electricity at one location and puts it out at another",
    ),
    KindRule(
        TechnologyKind.SUPPLY_TECHNOLOGY,
        _is_supply_technology,
        "it puts out electricity, and takes in no electricity",
    ),
    KindRule(
        TechnologyKind.FUEL_SUPPLY,
        _is_fuel_supply,
        "it puts out a fuel that is not electricity, and takes in nothing",
    ),
    KindRule(TechnologyKind.EXPORT, _is_export, "it takes in a fuel, and puts out nothing"),
    KindRule(
        TechnologyKind.CONVERSION,
        _is_conversion,
        "it takes in and puts out, rows give its fuels one location at most, "
        "and no kind before it fits",
    ),
)
