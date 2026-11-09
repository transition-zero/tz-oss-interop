"""The emission penalty that the cost of a line or a conversion record holds.

OSeMOSYS charges `emission_penalty` for each tonne that the operations mode of a technology
emits. A line and a conversion record price each MWh that the technology takes in, so each
pollutant that the region charges a penalty for adds its rate in t for each MWh taken in × the
penalty in $/t to that cost, as it does to the cost of a generator.
"""

from __future__ import annotations

from typing import Any

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.constants import UNIT_DOLLARS_PER_MWH
from interop.plugins.shared.osemosys_canonical.constants import (
    OPERATING_MODE,
    POLLUTANT,
    REGION,
    TECHNOLOGY,
    FlowParameter,
)
from interop.plugins.shared.osemosys_sienna_constants import (
    NO_COST,
    REGION_NAME_SEPARATOR,
    SupplyParameter,
)
from interop.plugins.shared.osemosys_sienna_translations._events import (
    build_osemosys_field,
    build_sienna_source,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_emissions import (
    ACTIVITY_RATE_T_PER_MWH,
    PENALTY,
    RATE_T_PER_MWH,
    STATED_RATE,
    read_emission_rates,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_penalties import (
    EMISSION_COST_MWH,
    PENALTY_COST_MWH,
    PENALTY_TERMS,
    build_penalty_terms,
)
from interop.plugins.shared.osemosys_sienna_translations._operations import OperationsYear
from interop.plugins.shared.osemosys_sienna_translations._technology_columns import TECHNOLOGY_NAME
from interop.plugins.shared.osemosys_sienna_translations._transport_columns import INPUT_RATIO
from interop.plugins.shared.translation_runner import DestinationFieldFactory
from interop.ports.outbound.reporting import EventKind, SourceField, TranslationEvent

_KEYS = [REGION, TECHNOLOGY]
_MODE_KEYS = [REGION, TECHNOLOGY, OPERATING_MODE]
_OPERATIONS_MODE = "electricity at the operations mode"
_PENALTY_DERIVATION = (
    "emission_rate of the pollutant at the operations mode, in t/MWh, × emission_penalty of the "
    "pollutant in the region, in $/t, / the electricity input_activity_ratio at that mode"
)


def enrich_link_penalties(
    state: State, operations: OperationsYear, members: pl.DataFrame
) -> pl.DataFrame:
    """The penalty of each pollutant that the operations mode emits, for each MWh that goes in,
    and their sum.

    `members` holds the keys and the electricity input ratio of each technology.
    """
    term = pl.struct(POLLUTANT, STATED_RATE, RATE_T_PER_MWH, PENALTY, PENALTY_COST_MWH)
    listed = (
        _build_penalised_emissions(state, operations, members)
        .sort(POLLUTANT)
        .group_by(_KEYS)
        .agg(term.alias(PENALTY_TERMS), pl.col(PENALTY_COST_MWH).sum().alias(EMISSION_COST_MWH))
    )
    return members.join(listed, on=_KEYS, how="left").with_columns(
        pl.col(EMISSION_COST_MWH).fill_null(NO_COST)
    )


def build_penalty_cost_sources(
    old: dict[str, Any], sienna_type: str, name: str, cost_attribute: str
) -> list[SourceField]:
    """The penalty of each pollutant, as the cost event of the member reads it."""
    return [
        build_sienna_source(
            sienna_type,
            name,
            _build_penalty_attribute(cost_attribute, term),
            term[PENALTY_COST_MWH],
            UNIT_DOLLARS_PER_MWH,
        )
        for term in old[PENALTY_TERMS] or []
    ]


def build_link_penalty_events(
    old: dict[str, Any], dest: DestinationFieldFactory, name: str, cost_attribute: str
) -> list[TranslationEvent]:
    """One event for each pollutant: the rate and the penalty give a cost for each MWh in."""
    return [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=_build_penalty_sources(old, term),
            destinations=[
                dest(
                    name,
                    _build_penalty_attribute(cost_attribute, term),
                    term[PENALTY_COST_MWH],
                    UNIT_DOLLARS_PER_MWH,
                )
            ],
            derivation=_PENALTY_DERIVATION,
        )
        for term in old[PENALTY_TERMS] or []
    ]


def _build_penalty_attribute(cost_attribute: str, term: dict[str, Any]) -> str:
    return f"{cost_attribute} emission penalty of {term[POLLUTANT]}"


def _build_penalty_sources(old: dict[str, Any], term: dict[str, Any]) -> list[SourceField]:
    return [
        build_osemosys_field(
            SupplyParameter.EMISSION_RATE,
            old[TECHNOLOGY_NAME],
            f"{term[POLLUTANT]} at the operations mode",
            term[STATED_RATE],
        ),
        build_osemosys_field(
            SupplyParameter.EMISSION_PENALTY,
            f"{old[REGION]}{REGION_NAME_SEPARATOR}{term[POLLUTANT]}",
            None,
            term[PENALTY],
        ),
        build_osemosys_field(
            FlowParameter.INPUT_ACTIVITY_RATIO,
            old[TECHNOLOGY_NAME],
            _OPERATIONS_MODE,
            old[INPUT_RATIO],
        ),
    ]


def _build_penalised_emissions(
    state: State, operations: OperationsYear, members: pl.DataFrame
) -> pl.DataFrame:
    """Each pollutant that a member emits at the operations mode and that its region penalises,
    with the penalty for each MWh that the member takes in."""
    held = members.select(*_KEYS, INPUT_RATIO, pl.lit(operations.mode).alias(OPERATING_MODE))
    rates = read_emission_rates(state, operations, held).join(held, on=_MODE_KEYS)
    per_input = pl.col(ACTIVITY_RATE_T_PER_MWH) / pl.col(INPUT_RATIO)
    return build_penalty_terms(
        state,
        operations,
        rates.select(*_KEYS, POLLUTANT, STATED_RATE, per_input.alias(RATE_T_PER_MWH)),
    )
