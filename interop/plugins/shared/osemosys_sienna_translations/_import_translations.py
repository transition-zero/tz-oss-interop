"""The Translation list that turns the import source table into Sienna ThermalStandard rows.

An import mode states no plant and no fuel, so the generator takes a fixed type, prime mover
and fuel. Each other field comes from the transport technology and from its import mode.
"""

from __future__ import annotations

from functools import partial
from typing import Any

import polars as pl

from interop.plugins.shared.constants import (
    UNIT_DOLLARS_PER_MWH,
    UNIT_MVA,
    UNIT_TONNES_PER_MWH,
)
from interop.plugins.shared.osemosys_canonical.constants import (
    FUEL,
    OPERATING_MODE,
    POLLUTANT,
    REGION,
    TECHNOLOGY,
    AnnotationColumn,
    FlowParameter,
)
from interop.plugins.shared.osemosys_sienna_constants import (
    IMPORT_CARRIER,
    REGION_NAME_SEPARATOR,
    SupplyParameter,
)
from interop.plugins.shared.osemosys_sienna_translations._activity import (
    ELECTRICITY_OUTPUT_RATIO,
)
from interop.plugins.shared.osemosys_sienna_translations._events import (
    build_defaulted,
    build_derived,
    build_osemosys_field,
    build_sienna_field,
    build_sienna_source,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_columns import (
    CAPACITY_UNIT,
    GENERATOR_NAME,
    OUTPUT_CAPACITY_MW,
    RESIDUAL_CAPACITY,
    TECHNOLOGY_NAME,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_costs import OWN_COST
from interop.plugins.shared.osemosys_sienna_translations._generator_emissions import (
    EMISSION_TERMS,
    OWN_RATE,
    RATE_T_PER_MWH,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_penalties import (
    OPERATION_COST_MWH,
    PENALTY_COST_MWH,
    PENALTY_TERMS,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_translations import (
    CARRIER_ATTRIBUTE,
    CATEGORY_ATTRIBUTE,
    EMISSION_ATTRIBUTE,
    FIXED_COST_ATTRIBUTE,
    GENERATOR_AVAILABLE_NOTE,
    GENERATOR_ID_NOTE,
    NO_COST,
    PENALTY_ATTRIBUTE,
    PROPORTIONAL_TERM_ATTRIBUTE,
    build_commitment,
    build_penalty_events,
    build_power_defaults,
    build_reactive_limits,
    build_series_events,
    build_thermal_power_limits,
    express_thermal_cost,
)
from interop.plugins.shared.osemosys_sienna_translations._transport_imports import IMPORT_FUELS
from interop.plugins.shared.sienna_constants import (
    PRIME_MOVERS_DTYPE,
    SIENNA_TYPE_ATTRIBUTE,
    THERMAL_FUELS_DTYPE,
    THERMAL_GENERATION_COST_DTYPE,
    SiennaComponent,
    SiennaPrimeMovers,
    SiennaThermalFuels,
    SiennaThermalGeneratorCol,
)
from interop.plugins.shared.translation_runner import (
    Translation,
    default_translation,
    row_position_id_translation,
)
from interop.ports.outbound.reporting import EventKind, SourceField, TranslationEvent

_Col = SiennaThermalGeneratorCol
_dest = partial(build_sienna_field, SiennaComponent.THERMAL_STANDARD)
_default = partial(default_translation, _dest, name_col=GENERATOR_NAME)

_SOURCE_TECHNOLOGY_ATTRIBUTE = "extensions.source_technology"
_SOURCE_MODE_ATTRIBUTE = "extensions.source_mode"

_TYPE_NOTE = (
    "an import mode brings electricity from outside the model and states no plant, so it "
    "becomes a ThermalStandard"
)
_PRIME_MOVER_NOTE = "an import mode states no plant, so the prime mover is OT, which is other"
_FUEL_TYPE_NOTE = "an import mode states no fuel, so the fuel is OTHER"
_CARRIER_NOTE = "an import mode has no category of its own, so the carrier is import"
_CATEGORY_NOTE = "an import mode has no category of its own, so the category is import"
_FIXED_COST_NOTE = (
    "OSeMOSYS states the fixed cost for the transport technology and not for one mode, so the "
    "line record holds it and the import pays none"
)
_NAME_DERIVATION = (
    "the transport technology, after its region when two regions hold it, then /import/ and "
    "the operating mode"
)
_BUS_DERIVATION = (
    "the location of the electricity fuel that the import mode puts out, which is one end of "
    "the line -> bus"
)
_BASE_POWER_DERIVATION = (
    "residual_capacity of the transport technology in the operations year, in MW, × the "
    "electricity output_activity_ratio of the import mode"
)
_VARIABLE_COST_DERIVATION = (
    "variable_operation_cost of the import mode, in $/MWh, / the electricity "
    "output_activity_ratio of the mode, plus the emission penalty of each pollutant that it emits"
)
_EMISSION_DERIVATION = (
    "emission_rate of the import mode / the electricity output_activity_ratio of the mode, in t/MWh"
)
_SOURCE_DERIVATION = "the transport technology and the operating mode that the generator stands for"


def build_import_translations(start: int) -> list[Translation]:
    """The fields of each import generator, whose ids follow the ThermalStandard ids before it."""
    return [
        _build_name(),
        row_position_id_translation(
            _dest, dest_name_col=_Col.NAME, id_col=_Col.ID, note=GENERATOR_ID_NOTE, start=start
        ),
        _default(dest_col=_Col.AVAILABLE, value=True, note=GENERATOR_AVAILABLE_NOTE),
        _build_bus(),
        *_build_fixed_choices(),
        _build_base_power(),
        *build_power_defaults(_dest),
        build_thermal_power_limits(_dest),
        build_reactive_limits(_dest),
        *_build_operation_cost(),
        *build_commitment(_dest),
        *_build_reports(),
    ]


def _build_mode_detail(old: dict[str, Any], detail: str | None = None) -> str:
    """The mode of a value keyed by mode, and its detail, as an operating_modes event names them."""
    mode = f"{OPERATING_MODE} {old[OPERATING_MODE]}"
    return mode if detail is None else f"{mode}, {detail}"


def _build_source(
    parameter: str, old: dict[str, Any], attribute: str | None, value: Any = None
) -> SourceField:
    return build_osemosys_field(parameter, old[TECHNOLOGY_NAME], attribute, value)


def _build_output_ratio_source(old: dict[str, Any]) -> SourceField:
    return _build_source(
        FlowParameter.OUTPUT_ACTIVITY_RATIO,
        old,
        f"electricity at the operating mode {old[OPERATING_MODE]}",
        old[ELECTRICITY_OUTPUT_RATIO],
    )


def _build_name() -> Translation:
    return Translation(
        exprs=[pl.col(GENERATOR_NAME).alias(_Col.NAME)],
        make_events=lambda old, new: build_derived(
            [
                _build_source(TECHNOLOGY, old, TECHNOLOGY, old[TECHNOLOGY]),
                _build_source(TECHNOLOGY, old, OPERATING_MODE, old[OPERATING_MODE]),
            ],
            [_dest(new[_Col.NAME], _Col.NAME, new[_Col.NAME])],
            _NAME_DERIVATION,
        ),
    )


def _build_bus() -> Translation:
    return Translation(
        exprs=[pl.col(AnnotationColumn.LOCATION).alias(_Col.BUS_NAME)],
        make_events=lambda old, new: build_derived(
            [_build_output_ratio_source(old), *_build_fuel_location_sources(old)],
            [_dest(old[GENERATOR_NAME], _Col.BUS_NAME, new[_Col.BUS_NAME])],
            _BUS_DERIVATION,
        ),
    )


def _build_fuel_location_sources(old: dict[str, Any]) -> list[SourceField]:
    return [
        build_osemosys_field(
            FUEL,
            f"{old[REGION]}{REGION_NAME_SEPARATOR}{fuel}",
            AnnotationColumn.LOCATION,
            old[AnnotationColumn.LOCATION],
        )
        for fuel in old[IMPORT_FUELS]
    ]


def _build_fixed_choices() -> list[Translation]:
    """The type, the prime mover and the fuel, which no carriers: row gives an import."""
    return [
        Translation(
            exprs=[],
            make_events=lambda old, _new: build_defaulted(
                [
                    _dest(
                        old[GENERATOR_NAME],
                        SIENNA_TYPE_ATTRIBUTE,
                        SiennaComponent.THERMAL_STANDARD.value,
                    )
                ],
                _TYPE_NOTE,
            ),
        ),
        _default(
            dest_col=_Col.PRIME_MOVER_TYPE,
            value=SiennaPrimeMovers.OT.value,
            note=_PRIME_MOVER_NOTE,
            dtype=PRIME_MOVERS_DTYPE,
        ),
        _default(
            dest_col=_Col.FUEL_TYPE,
            value=SiennaThermalFuels.OTHER.value,
            note=_FUEL_TYPE_NOTE,
            dtype=THERMAL_FUELS_DTYPE,
        ),
    ]


def _build_base_power() -> Translation:
    return Translation(
        exprs=[pl.col(OUTPUT_CAPACITY_MW).alias(_Col.BASE_POWER)],
        make_events=lambda old, new: build_derived(
            [
                build_osemosys_field(
                    SupplyParameter.RESIDUAL_CAPACITY,
                    old[TECHNOLOGY_NAME],
                    None,
                    old[RESIDUAL_CAPACITY],
                    old[CAPACITY_UNIT],
                ),
                _build_output_ratio_source(old),
            ],
            [_dest(old[GENERATOR_NAME], _Col.BASE_POWER, new[_Col.BASE_POWER], UNIT_MVA)],
            _BASE_POWER_DERIVATION,
        ),
    )


def _build_operation_cost() -> list[Translation]:
    """The variable cost as a linear curve, and a fixed cost of zero."""
    return [
        Translation(
            exprs=[
                express_thermal_cost()
                .cast(THERMAL_GENERATION_COST_DTYPE)
                .alias(_Col.OPERATION_COST)
            ],
            make_events=lambda old, _new: build_derived(
                _build_cost_sources(old),
                [
                    _dest(
                        old[GENERATOR_NAME],
                        PROPORTIONAL_TERM_ATTRIBUTE,
                        old[OPERATION_COST_MWH],
                        UNIT_DOLLARS_PER_MWH,
                    )
                ],
                _VARIABLE_COST_DERIVATION,
            ),
        ),
        Translation(
            exprs=[],
            make_events=lambda old, _new: build_defaulted(
                [_dest(old[GENERATOR_NAME], FIXED_COST_ATTRIBUTE, NO_COST)], _FIXED_COST_NOTE
            ),
        ),
    ]


def _build_cost_sources(old: dict[str, Any]) -> list[SourceField]:
    """The cost of the mode, its output ratio, and the penalty of each pollutant."""
    own = _build_source(
        SupplyParameter.VARIABLE_OPERATION_COST,
        old,
        _build_mode_detail(old),
        old[OWN_COST],
    )
    penalties = [
        build_sienna_source(
            SiennaComponent.THERMAL_STANDARD,
            old[GENERATOR_NAME],
            f"{PENALTY_ATTRIBUTE}{term[POLLUTANT]}",
            term[PENALTY_COST_MWH],
            UNIT_DOLLARS_PER_MWH,
        )
        for term in old[PENALTY_TERMS] or []
    ]
    return [own, _build_output_ratio_source(old), *penalties]


def _build_reports() -> list[Translation]:
    return [
        Translation(exprs=[], make_events=lambda old, _new: build_series_events(_dest, old)),
        Translation(exprs=[], make_events=lambda old, _new: _build_emission_events(old)),
        Translation(exprs=[], make_events=lambda old, _new: build_penalty_events(_dest, old)),
        Translation(exprs=[], make_events=lambda old, _new: _build_grouping_events(old)),
        Translation(exprs=[], make_events=lambda old, _new: _build_source_events(old)),
    ]


def _build_emission_events(old: dict[str, Any]) -> list[TranslationEvent]:
    return [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                _build_source(
                    SupplyParameter.EMISSION_RATE,
                    old,
                    _build_mode_detail(old, term[POLLUTANT]),
                    term[OWN_RATE],
                ),
                _build_output_ratio_source(old),
            ],
            destinations=[
                _dest(
                    old[GENERATOR_NAME],
                    f"{EMISSION_ATTRIBUTE}{term[POLLUTANT]}",
                    term[RATE_T_PER_MWH],
                    UNIT_TONNES_PER_MWH,
                )
            ],
            derivation=_EMISSION_DERIVATION,
        )
        for term in old[EMISSION_TERMS] or []
    ]


def _build_grouping_events(old: dict[str, Any]) -> list[TranslationEvent]:
    return [
        *build_defaulted(
            [_dest(old[GENERATOR_NAME], CATEGORY_ATTRIBUTE, IMPORT_CARRIER)], _CATEGORY_NOTE
        ),
        *build_defaulted(
            [_dest(old[GENERATOR_NAME], CARRIER_ATTRIBUTE, IMPORT_CARRIER)], _CARRIER_NOTE
        ),
    ]


def _build_source_events(old: dict[str, Any]) -> list[TranslationEvent]:
    sources = [
        _build_source(TECHNOLOGY, old, TECHNOLOGY, old[TECHNOLOGY]),
        _build_source(TECHNOLOGY, old, OPERATING_MODE, old[OPERATING_MODE]),
    ]
    return build_derived(
        sources,
        [
            _dest(old[GENERATOR_NAME], _SOURCE_TECHNOLOGY_ATTRIBUTE, old[TECHNOLOGY_NAME]),
            _dest(old[GENERATOR_NAME], _SOURCE_MODE_ATTRIBUTE, old[OPERATING_MODE]),
        ],
        _SOURCE_DERIVATION,
    )
