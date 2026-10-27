"""The events of a generator for the values that reach no Sienna column of their own.

Each builder reads one row of the generator source table. A fuel term, a penalty and the
variable cost take an optional destination: with none, the Sienna type has no operation cost,
so the term is NOT_MAPPED. The warnings name the costs that the events record as left out.
"""

from __future__ import annotations

import logging
from typing import Any, NamedTuple

import polars as pl

from interop.plugins.shared.constants import (
    UNIT_DOLLARS_PER_MW_YEAR,
    UNIT_DOLLARS_PER_MWH,
    UNIT_DOLLARS_PER_TONNE,
    UNIT_TONNES_PER_MWH,
)
from interop.plugins.shared.osemosys_canonical.constants import (
    FUEL,
    POLLUTANT,
    REGION,
    TECHNOLOGY,
    AnnotationColumn,
    FlowParameter,
)
from interop.plugins.shared.osemosys_sienna_constants import (
    NO_COST,
    OSEMOSYS_TO_SIENNA_PIPELINE,
    REGION_NAME_SEPARATOR,
    TECHNOLOGIES_LABEL,
    SupplyParameter,
)
from interop.plugins.shared.osemosys_sienna_translations._activity import (
    ELECTRICITY_OUTPUT_RATIO,
)
from interop.plugins.shared.osemosys_sienna_translations._events import (
    build_derived,
    build_osemosys_field,
    build_sienna_source,
)
from interop.plugins.shared.osemosys_sienna_translations._fuel_supply import (
    INPUT_RATIO,
    OUTPUT_RATIO,
    PRODUCER,
    PRODUCER_COST,
    PRODUCER_COUNT,
    PRODUCER_EMISSION_RATE,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_columns import (
    GENERATOR_NAME,
    HAS_SERIES,
    SIENNA_TYPE,
    TECHNOLOGY_NAME,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_costs import (
    FIXED_COST,
    FIXED_COST_MW_YEAR,
    FUEL_TERM_MWH,
    FUEL_TERMS,
    OWN_COST,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_emissions import (
    EMISSION_TERMS,
    FUEL_PRODUCERS,
    OWN_RATE,
    PENALTY,
    PENALTY_PER_TONNE,
    RATE_T_PER_MWH,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_penalties import (
    OPERATION_COST_MWH,
    PENALTY_COST_MWH,
    PENALTY_TERMS,
)
from interop.plugins.shared.osemosys_sienna_translations._technologies import (
    AVAILABILITY_FACTOR,
)
from interop.plugins.shared.sienna_constants import (
    SiennaComponent,
    SiennaSeriesName,
    SiennaThermalGeneratorCol,
)
from interop.plugins.shared.translation_runner import (
    DestinationFieldFactory,
)
from interop.plugins.shared.warning_text import name_a_few
from interop.ports.outbound.reporting import EventKind, SourceField, TranslationEvent

log = logging.getLogger(__name__)

# Every Sienna generator type names its shared fields alike, so these name them for all four.
_Col = SiennaThermalGeneratorCol

PROPORTIONAL_TERM_ATTRIBUTE = (
    f"{_Col.OPERATION_COST}.variable.value_curve.function_data.proportional_term"
)
_FUEL_TERM_ATTRIBUTE = f"{_Col.OPERATION_COST} fuel term of "
PENALTY_ATTRIBUTE = f"{_Col.OPERATION_COST} emission penalty of "
SERIES_ATTRIBUTE = f"{SiennaSeriesName.MAX_ACTIVE_POWER} time series"
FOM_ATTRIBUTE = "extensions.fom_charge_per_mw_year"
EMISSION_ATTRIBUTE = "extensions.emission_rates_t_per_mwh."
CATEGORY_ATTRIBUTE = "extensions.category"
CARRIER_ATTRIBUTE = "extensions.carrier"
_EACH_TIMESLICE = "each timeslice"
_AVAILABILITY_DERIVATION = (
    "capacity_factor of the timeslice of each hour × availability_factor, per unit of "
    "base_power; OSeMOSYS states availability_factor as a limit on the energy of the year, and "
    "the operations system applies it as a derate in each hour"
)
_FUEL_TERM_DERIVATION = (
    "input_activity_ratio × variable_operation_cost / output_activity_ratio of the producer of "
    "the fuel at the operations mode, in $/MWh, / the electricity output_activity_ratio of the "
    "technology"
)
_PENALTY_DERIVATION = (
    "the emission rate of the pollutant, in t/MWh, × emission_penalty of the pollutant in the "
    "region of the technology, in $/tonne"
)
_VARIABLE_COST_DERIVATION = (
    "variable_operation_cost at the operations mode, in $/MWh, / the electricity "
    "output_activity_ratio, plus the fuel term of each fuel that the technology takes in, plus "
    "the emission penalty of each pollutant that it emits"
)
_FIXED_COST_DERIVATION = (
    "fixed_cost of the operations year, in $/MW/yr, / the electricity output_activity_ratio at "
    "the operations mode"
)
_EMISSION_DERIVATION = (
    "(emission_rate at the operations mode, plus input_activity_ratio × the emission_rate of "
    "the producer of each fuel for each unit of that fuel) / the electricity "
    "output_activity_ratio, in t/MWh"
)
_CATEGORY_DERIVATION = "the category of the technology"
_CARRIER_DERIVATION = "the category of the technology, which names its carriers: row"
_OUTPUT_RATIO_ATTRIBUTE = "electricity at the operations mode"
_LOST_COST_NOTE = (
    "RenewableNonDispatch has no operation_cost field, so the variable cost is left out"
)
_LOST_FUEL_TERM_NOTE = (
    "RenewableNonDispatch has no operation_cost field, so the fuel term of {fuel} is left out"
)
_LOST_PENALTY_NOTE = (
    "RenewableNonDispatch has no operation_cost field, so the emission penalty of {pollutant} "
    "is left out"
)


def _build_producer_note(term: dict[str, Any]) -> str:
    return (
        f"the cheapest of {term[PRODUCER_COUNT]} fuel_supply technologies that put out "
        f"{term[FUEL]} in the region"
    )


def _build_no_producer_note(old: dict[str, Any], term: dict[str, Any]) -> str:
    return (
        f"no fuel_supply technology puts out the fuel {_build_region_name(old, term[FUEL])}, so "
        "the generator pays no fuel cost for it"
    )


def _build_region_name(old: dict[str, Any], member: str) -> str:
    return f"{old[REGION]}{REGION_NAME_SEPARATOR}{member}"


def build_output_ratio_source(old: dict[str, Any]) -> SourceField:
    return _build_source(
        FlowParameter.OUTPUT_ACTIVITY_RATIO,
        old,
        _OUTPUT_RATIO_ATTRIBUTE,
        old[ELECTRICITY_OUTPUT_RATIO],
    )


def _build_source(
    parameter: str, old: dict[str, Any], attribute: str | None, value: Any = None
) -> SourceField:
    return build_osemosys_field(parameter, old[TECHNOLOGY_NAME], attribute, value)


def build_availability_sources(old: dict[str, Any]) -> list[SourceField]:
    return [
        _build_source(SupplyParameter.CAPACITY_FACTOR, old, _EACH_TIMESLICE),
        _build_source(SupplyParameter.AVAILABILITY_FACTOR, old, None, old[AVAILABILITY_FACTOR]),
    ]


def build_series_events(
    dest: DestinationFieldFactory, old: dict[str, Any]
) -> list[TranslationEvent]:
    """The availability series of a generator that has one."""
    if not old[HAS_SERIES]:
        return []
    return build_derived(
        build_availability_sources(old),
        [dest(old[GENERATOR_NAME], SERIES_ATTRIBUTE)],
        _AVAILABILITY_DERIVATION,
    )


def build_fuel_term_events(
    dest: DestinationFieldFactory | None, old: dict[str, Any]
) -> list[TranslationEvent]:
    return [_build_fuel_term_event(dest, old, term) for term in old[FUEL_TERMS] or []]


def _build_fuel_term_event(
    dest: DestinationFieldFactory | None, old: dict[str, Any], term: dict[str, Any]
) -> TranslationEvent:
    if term[PRODUCER] is None:
        return _build_no_producer_event(old, term)
    if dest is None:
        return TranslationEvent(
            kind=EventKind.NOT_MAPPED,
            sources=_build_fuel_term_sources(old, term),
            note=_LOST_FUEL_TERM_NOTE.format(fuel=term[FUEL]),
        )
    return TranslationEvent(
        kind=EventKind.VALUE_DERIVED,
        sources=_build_fuel_term_sources(old, term),
        destinations=[
            dest(
                old[GENERATOR_NAME],
                f"{_FUEL_TERM_ATTRIBUTE}{term[FUEL]}",
                term[FUEL_TERM_MWH],
                UNIT_DOLLARS_PER_MWH,
            )
        ],
        derivation=_FUEL_TERM_DERIVATION,
        note=_build_producer_note(term),
    )


def _build_no_producer_event(old: dict[str, Any], term: dict[str, Any]) -> TranslationEvent:
    return TranslationEvent(
        kind=EventKind.NOT_MAPPED,
        sources=[_build_input_ratio_source(old, term)],
        note=_build_no_producer_note(old, term),
    )


def _build_input_ratio_source(old: dict[str, Any], term: dict[str, Any]) -> SourceField:
    return _build_source(FlowParameter.INPUT_ACTIVITY_RATIO, old, term[FUEL], term[INPUT_RATIO])


def _build_fuel_term_sources(old: dict[str, Any], term: dict[str, Any]) -> list[SourceField]:
    """The input ratio of the fuel, the cost and output ratio of its producer, and own output."""
    producer = _build_region_name(old, term[PRODUCER])
    return [
        _build_input_ratio_source(old, term),
        build_osemosys_field(
            SupplyParameter.VARIABLE_OPERATION_COST, producer, None, term[PRODUCER_COST]
        ),
        build_osemosys_field(
            FlowParameter.OUTPUT_ACTIVITY_RATIO, producer, term[FUEL], term[OUTPUT_RATIO]
        ),
        build_output_ratio_source(old),
    ]


def _build_cost_sources(old: dict[str, Any]) -> list[SourceField]:
    """The own cost, the fuel term of each fuel that has a producer, and each penalty."""
    terms = [
        build_sienna_source(
            old[SIENNA_TYPE],
            old[GENERATOR_NAME],
            f"{_FUEL_TERM_ATTRIBUTE}{term[FUEL]}",
            term[FUEL_TERM_MWH],
            UNIT_DOLLARS_PER_MWH,
        )
        for term in old[FUEL_TERMS] or []
        if term[PRODUCER] is not None
    ]
    penalties = [
        build_sienna_source(
            old[SIENNA_TYPE],
            old[GENERATOR_NAME],
            f"{PENALTY_ATTRIBUTE}{term[POLLUTANT]}",
            term[PENALTY_COST_MWH],
            UNIT_DOLLARS_PER_MWH,
        )
        for term in old[PENALTY_TERMS] or []
    ]
    return [*_build_own_cost_sources(old), *terms, *penalties]


def _build_own_cost_sources(old: dict[str, Any]) -> list[SourceField]:
    own = _build_source(SupplyParameter.VARIABLE_OPERATION_COST, old, None, old[OWN_COST])
    return [own, build_output_ratio_source(old)]


def build_fixed_cost_events(
    dest: DestinationFieldFactory, old: dict[str, Any]
) -> list[TranslationEvent]:
    if old[FIXED_COST] is None:
        return []
    return build_derived(
        [
            _build_source(SupplyParameter.FIXED_COST, old, None, old[FIXED_COST]),
            build_output_ratio_source(old),
        ],
        [
            dest(
                old[GENERATOR_NAME],
                FOM_ATTRIBUTE,
                old[FIXED_COST_MW_YEAR],
                UNIT_DOLLARS_PER_MW_YEAR,
            )
        ],
        _FIXED_COST_DERIVATION,
    )


def build_emission_events(
    dest: DestinationFieldFactory, old: dict[str, Any]
) -> list[TranslationEvent]:
    return [
        build_derived(
            _build_emission_sources(old, term),
            [
                dest(
                    old[GENERATOR_NAME],
                    f"{EMISSION_ATTRIBUTE}{term[POLLUTANT]}",
                    term[RATE_T_PER_MWH],
                    UNIT_TONNES_PER_MWH,
                )
            ],
            _EMISSION_DERIVATION,
        )[0]
        for term in old[EMISSION_TERMS] or []
    ]


def _build_emission_sources(old: dict[str, Any], term: dict[str, Any]) -> list[SourceField]:
    own = _build_source(SupplyParameter.EMISSION_RATE, old, term[POLLUTANT], term[OWN_RATE])
    burned = [
        build_osemosys_field(
            SupplyParameter.EMISSION_RATE,
            _build_region_name(old, producer[PRODUCER]),
            term[POLLUTANT],
            producer[PRODUCER_EMISSION_RATE],
        )
        for producer in term[FUEL_PRODUCERS] or []
    ]
    return [own, *burned, build_output_ratio_source(old)]


def build_penalty_events(
    dest: DestinationFieldFactory | None, old: dict[str, Any]
) -> list[TranslationEvent]:
    """One event for each pollutant: the emission rate and the penalty give a cost per MWh.

    With no `dest`, the type has no operation cost, so each penalty is NOT_MAPPED.
    """
    return [_build_penalty_event(dest, old, term) for term in old[PENALTY_TERMS] or []]


def _build_penalty_event(
    dest: DestinationFieldFactory | None, old: dict[str, Any], term: dict[str, Any]
) -> TranslationEvent:
    if dest is None:
        return TranslationEvent(
            kind=EventKind.NOT_MAPPED,
            sources=_build_penalty_sources(old, term),
            note=_LOST_PENALTY_NOTE.format(pollutant=term[POLLUTANT]),
        )
    return TranslationEvent(
        kind=EventKind.VALUE_DERIVED,
        sources=_build_penalty_sources(old, term),
        destinations=[
            dest(
                old[GENERATOR_NAME],
                f"{PENALTY_ATTRIBUTE}{term[POLLUTANT]}",
                term[PENALTY_COST_MWH],
                UNIT_DOLLARS_PER_MWH,
            )
        ],
        derivation=_PENALTY_DERIVATION,
        note=f"the penalty is {term[PENALTY_PER_TONNE]:g} {UNIT_DOLLARS_PER_TONNE}",
    )


def _build_penalty_sources(old: dict[str, Any], term: dict[str, Any]) -> list[SourceField]:
    return [
        build_sienna_source(
            old[SIENNA_TYPE],
            old[GENERATOR_NAME],
            f"{EMISSION_ATTRIBUTE}{term[POLLUTANT]}",
            term[RATE_T_PER_MWH],
            UNIT_TONNES_PER_MWH,
        ),
        build_osemosys_field(
            SupplyParameter.EMISSION_PENALTY,
            _build_region_name(old, term[POLLUTANT]),
            None,
            term[PENALTY],
        ),
    ]


def build_grouping_events(
    dest: DestinationFieldFactory, old: dict[str, Any]
) -> list[TranslationEvent]:
    category = old[AnnotationColumn.CATEGORY]
    return [
        *build_derived(
            [_build_category_source(old)],
            [dest(old[GENERATOR_NAME], CATEGORY_ATTRIBUTE, category)],
            _CATEGORY_DERIVATION,
        ),
        *build_derived(
            [_build_category_source(old)],
            [dest(old[GENERATOR_NAME], CARRIER_ATTRIBUTE, category)],
            _CARRIER_DERIVATION,
        ),
    ]


def _build_category_source(old: dict[str, Any]) -> SourceField:
    return build_osemosys_field(
        TECHNOLOGY, old[TECHNOLOGY_NAME], AnnotationColumn.CATEGORY, old[AnnotationColumn.CATEGORY]
    )


def build_variable_cost_events(
    dest: DestinationFieldFactory | None, old: dict[str, Any]
) -> list[TranslationEvent]:
    """The proportional term of the cost curve; with no `dest`, a variable cost that is lost.

    The fuel terms and the penalties report themselves, so a lost cost names the own cost only.
    """
    if dest is not None:
        return build_derived(
            _build_cost_sources(old),
            [
                dest(
                    old[GENERATOR_NAME],
                    PROPORTIONAL_TERM_ATTRIBUTE,
                    old[OPERATION_COST_MWH],
                    UNIT_DOLLARS_PER_MWH,
                )
            ],
            _VARIABLE_COST_DERIVATION,
        )
    if not old[OWN_COST]:
        return []
    return [
        TranslationEvent(
            kind=EventKind.NOT_MAPPED,
            sources=_build_own_cost_sources(old),
            note=_LOST_COST_NOTE,
        )
    ]


# --- the warnings about a cost that the system leaves out -----------------------------------


class _LostCost(NamedTuple):
    """A cost that a generator states and its Sienna generator does not pay, and the warning."""

    is_lost: pl.Expr
    counted_noun: str
    reason: str


def _express_has_fuel_term(is_counted: pl.Expr) -> pl.Expr:
    """Whether one fuel term of the generator meets `is_counted`, on the producer of the term."""
    return pl.col(FUEL_TERMS).list.eval(is_counted).list.any().fill_null(False)  # noqa: FBT003


_PRODUCER = pl.element().struct.field(PRODUCER)
_IS_WITHOUT_COST = pl.col(SIENNA_TYPE) == SiennaComponent.RENEWABLE_NON_DISPATCH
_NO_COST_FIELD = "and the type has no operation_cost field, so the cost is left out"
_LOST_COSTS = (
    _LostCost(
        _express_has_fuel_term(_PRODUCER.is_null()),
        "generator(s)",
        "burn a fuel that no fuel_supply technology puts out, so each pays no fuel cost for it",
    ),
    _LostCost(
        _IS_WITHOUT_COST & (pl.col(OWN_COST).fill_null(NO_COST) != NO_COST),
        f"{SiennaComponent.RENEWABLE_NON_DISPATCH} generator(s)",
        f"state a variable cost, {_NO_COST_FIELD}",
    ),
    _LostCost(
        _IS_WITHOUT_COST & _express_has_fuel_term(_PRODUCER.is_not_null()),
        f"{SiennaComponent.RENEWABLE_NON_DISPATCH} generator(s)",
        f"pay for a fuel, {_NO_COST_FIELD}",
    ),
    _LostCost(
        _IS_WITHOUT_COST & (pl.col(PENALTY_TERMS).list.len().fill_null(0) > 0),
        f"{SiennaComponent.RENEWABLE_NON_DISPATCH} generator(s)",
        f"pay an emission penalty, {_NO_COST_FIELD}",
    ),
)


def warn_lost_costs(generators: pl.DataFrame) -> None:
    """One warning for each kind of cost that the events record as not mapped."""
    for lost in _LOST_COSTS:
        names = sorted(generators.filter(lost.is_lost)[TECHNOLOGY_NAME].to_list())
        if names:
            log.warning(
                "%s: %d %s %s. %s: %s",
                OSEMOSYS_TO_SIENNA_PIPELINE,
                len(names),
                lost.counted_noun,
                lost.reason,
                TECHNOLOGIES_LABEL,
                name_a_few(names),
            )
