"""The kind and the location of a technology, inferred from what it takes in and puts out."""

from __future__ import annotations

from collections.abc import Callable
from typing import NamedTuple

import polars as pl

from interop.plugins.shared.osemosys_canonical.constants import (
    FUEL,
    LOCATION_SEPARATOR,
    MODE_OF_OPERATION,
    REGION,
    TECHNOLOGY,
    VALUE_COL,
    FlowParameter,
    TechnologyKind,
)
from interop.plugins.shared.osemosys_canonical.object_rows import MemberKey

_FLOW_COLUMNS = [REGION, TECHNOLOGY, FUEL, MODE_OF_OPERATION]
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
    """One fuel that a technology takes in or puts out in one mode."""

    mode: str
    is_input: bool
    fuel: str


class FuelAnnotation(NamedTuple):
    """What the kind inference needs to know about one fuel in one region."""

    location: str
    is_electricity: bool
    has_row_location: bool


class LocatedFlow(NamedTuple):
    """One fuel flow of a technology, with the annotation of its fuel."""

    flow: FuelFlow
    fuel: FuelAnnotation


class TechnologyStructure(NamedTuple):
    """What one technology in one region takes in and puts out, and whether it has a storage."""

    flows: list[LocatedFlow]
    has_storage: bool

    @property
    def inputs(self) -> list[FuelAnnotation]:
        return [located.fuel for located in self.flows if located.flow.is_input]

    @property
    def outputs(self) -> list[FuelAnnotation]:
        return [located.fuel for located in self.flows if not located.flow.is_input]


class Inference(NamedTuple):
    """One inferred annotation, and the rule that gave it."""

    value: str
    rule: str


class KindRule(NamedTuple):
    """One kind of the closed list, the test of a technology for it, and the rule a note names."""

    kind: TechnologyKind
    is_match: Callable[[TechnologyStructure], bool]
    rule: str


def build_technology_flows(canonical: dict[str, pl.LazyFrame]) -> dict[MemberKey, list[FuelFlow]]:
    """Counts each row whose VALUE is above zero, in any year and any mode."""
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
    """Collects only the distinct key columns, which are component scale."""
    columns = _STORAGE_COLUMNS if parameter in _STORAGE_PARAMETERS else _FLOW_COLUMNS
    table = canonical.get(parameter)
    if table is None:
        return pl.DataFrame(schema=dict.fromkeys(columns, pl.Utf8))
    return table.filter(pl.col(VALUE_COL) > 0).select(columns).unique().collect()


def choose_kind(structure: TechnologyStructure) -> Inference | None:
    """The kinds are tried in the order of the closed list, and the first that fits wins."""
    for rule in _KIND_RULES:
        if rule.is_match(structure):
            return Inference(rule.kind.value, rule.rule)
    return None


def build_technology_location(structure: TechnologyStructure, region: str) -> Inference:
    """In the lowest mode, the location of the input fuel comes before the output fuel's."""
    located = sorted(
        (located for located in structure.flows if located.fuel.has_row_location),
        key=_build_location_order,
    )
    locations = list(dict.fromkeys(flow.fuel.location for flow in located))
    if not locations:
        return Inference(region, _REGION_LOCATION_RULE)
    return Inference(LOCATION_SEPARATOR.join(locations), _FUEL_LOCATION_RULE)


def _build_location_order(located: LocatedFlow) -> tuple[int, str, bool, str]:
    """A mode that is a whole number sorts by its number, so mode 2 comes before mode 10."""
    mode = located.flow.mode
    number = int(mode) if mode.isdigit() else -1
    return number, mode, not located.flow.is_input, located.fuel.location


def _is_storage(structure: TechnologyStructure) -> bool:
    return structure.has_storage


def _is_link(structure: TechnologyStructure) -> bool:
    """Two row-given electricity locations among its inputs and outputs mean one input and one
    output differ."""
    inputs = [fuel for fuel in structure.inputs if fuel.is_electricity]
    outputs = [fuel for fuel in structure.outputs if fuel.is_electricity]
    return bool(inputs) and bool(outputs) and len(_list_row_locations([*inputs, *outputs])) > 1


def _is_generator(structure: TechnologyStructure) -> bool:
    puts_out_electricity = any(fuel.is_electricity for fuel in structure.outputs)
    return puts_out_electricity and not any(fuel.is_electricity for fuel in structure.inputs)


def _is_supply(structure: TechnologyStructure) -> bool:
    puts_out_other = any(not fuel.is_electricity for fuel in structure.outputs)
    return puts_out_other and not structure.inputs


def _is_export(structure: TechnologyStructure) -> bool:
    return bool(structure.inputs) and not structure.outputs


def _is_conversion(structure: TechnologyStructure) -> bool:
    locations = _list_row_locations([located.fuel for located in structure.flows])
    return bool(structure.inputs) and bool(structure.outputs) and len(locations) <= 1


def _list_row_locations(fuels: list[FuelAnnotation]) -> list[str]:
    """A location that the engine infers for a fuel does not count, as in the technology
    location."""
    return list(dict.fromkeys(fuel.location for fuel in fuels if fuel.has_row_location))


_KIND_RULES = (
    KindRule(
        TechnologyKind.STORAGE,
        _is_storage,
        "it connects to a storage through TechnologyToStorage or TechnologyFromStorage",
    ),
    KindRule(
        TechnologyKind.LINK,
        _is_link,
        "it takes in electricity at one location and puts it out at another",
    ),
    KindRule(
        TechnologyKind.GENERATOR,
        _is_generator,
        "it puts out electricity, and takes in no electricity",
    ),
    KindRule(
        TechnologyKind.SUPPLY,
        _is_supply,
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
