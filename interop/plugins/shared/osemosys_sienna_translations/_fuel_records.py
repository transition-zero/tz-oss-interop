"""The records of extensions.json that the fuels that are not electricity become.

Each mode of `_fuel_modes` becomes a generator record or a conversion record in PyPSA terms.
Each value is for one MWh of the fuel that rates the component: the fuel that a generator puts
out, or the fuel that goes in at bus0 of a link. Each bus of such a fuel becomes a bus record.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, NamedTuple

import polars as pl

from interop.core.extensions import (
    BusExtension,
    ByYear,
    ConversionExtension,
    ExtensionKind,
    GeneratorExtension,
)
from interop.core.pipeline import State
from interop.plugins.shared.constants import (
    EXTENSIONS_PREFIX,
    UNIT_DOLLARS_PER_MWH,
    UNIT_MW,
    UNIT_MWH,
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
    WHOLE_CAPACITY,
    ActivityParameter,
    InvestmentParameter,
    SupplyParameter,
)
from interop.plugins.shared.osemosys_sienna_translations._events import (
    build_osemosys_field,
    build_sienna_field,
)
from interop.plugins.shared.osemosys_sienna_translations._free_build import (
    CAPITAL_COST,
    FIXED_COST,
    FREE_BUILD_PARAMETERS,
    MAX_CAPACITY,
    MAX_INVESTMENT,
    RESIDUAL,
)
from interop.plugins.shared.osemosys_sienna_translations._fuel_modes import (
    ACTIVITY_MW,
    AVAILABILITY,
    COST_MWH,
    CTAU,
    E_MAX_MWH,
    E_MIN_MWH,
    INPUTS,
    IS_EXTENDABLE,
    MAX_ACTIVITY_MW,
    MODE_COUNT,
    MODE_NAME,
    MODE_REPORT_NAME,
    OUTPUTS,
    PENALTY_MWH,
    RATE_T_PER_MWH,
    RATED_RATIO,
    RATES,
    RATIO,
    ROLE,
    SUPPLY,
    VARIABLE_COST,
)
from interop.plugins.shared.osemosys_sienna_translations._fuels import (
    FUEL_BUS,
    FUEL_CARRIER,
    FUEL_LOCATION,
    IS_ELECTRICITY,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_penalties import (
    PenaltyNote,
    build_penalty_keys,
    set_penalties_persisted,
)
from interop.plugins.shared.osemosys_sienna_translations._persisted import set_persisted_rows
from interop.plugins.shared.pypsa_constants import LINK_FURTHER_PORTS
from interop.ports.outbound.reporting import EventKind, SourceField, TranslationEvent

_NO_COST = 0.0
_FUEL_SCOPE = "fuel"
_FUEL_PENALTY_SCOPE = "fuel-penalties"


@dataclass
class FuelRecords:
    """The records of the modes and the buses of their fuels, and the event of each value."""

    generators: list[GeneratorExtension] = field(default_factory=list)
    conversions: list[ConversionExtension] = field(default_factory=list)
    buses: list[BusExtension] = field(default_factory=list)
    events: list[TranslationEvent] = field(default_factory=list)


class _Value(NamedTuple):
    """The parameters that one field of a record reads, its unit and how it derives."""

    parameters: tuple[str, ...]
    unit: str | None
    derivation: str


def build_fuel_records(modes: pl.DataFrame, loads: pl.DataFrame, year: int) -> FuelRecords:
    """One record for each mode, and one bus record for each fuel that a mode or a load uses.

    `loads` holds the fuel and its bus, carrier and location, for each load of a fuel that is
    not electricity.
    """
    built = FuelRecords()
    for row in modes.iter_rows(named=True):
        if row[ROLE] == SUPPLY:
            generator = _build_generator(row, year)
            built.generators.append(generator)
            built.events.extend(_build_events(row, ExtensionKind.GENERATOR, generator))
        else:
            conversion = _build_conversion(row, year)
            built.conversions.append(conversion)
            built.events.extend(_build_events(row, ExtensionKind.CONVERSION, conversion))
    for bus in _build_buses(modes, loads).iter_rows(named=True):
        built.buses.append(_build_bus(bus))
        built.events.extend(_build_bus_events(bus))
    return built


def set_fuel_values_persisted(state: State, modes: pl.DataFrame) -> None:
    """Note the rows of each technology whose values a generator or a conversion record holds.

    A limit of the technology binds the sum of its modes, so only a technology of one mode
    applies it.
    """
    for kind, held in (
        (ExtensionKind.GENERATOR, modes.filter(pl.col(ROLE) == SUPPLY)),
        (ExtensionKind.CONVERSION, modes.filter(pl.col(ROLE) != SUPPLY)),
    ):
        groups = (
            (_HELD_PARAMETERS, held),
            (_TECHNOLOGY_LIMITS, held.filter(pl.col(MODE_COUNT) == 1)),
            (FREE_BUILD_PARAMETERS, held.filter(pl.col(IS_EXTENDABLE))),
        )
        for parameters, rows in groups:
            for parameter in parameters:
                _set_persisted(state, kind, parameter, rows)
        note = PenaltyNote(kind, _FUEL_PENALTY_SCOPE)
        set_penalties_persisted(state, note, build_penalty_keys(held, (RATES,)))


def _set_persisted(state: State, kind: ExtensionKind, parameter: str, held: pl.DataFrame) -> None:
    if held.height > 0:
        set_persisted_rows(state, kind, parameter, [held.select(REGION, TECHNOLOGY)], _FUEL_SCOPE)


_HELD_PARAMETERS: tuple[str, ...] = (
    SupplyParameter.RESIDUAL_CAPACITY,
    SupplyParameter.AVAILABILITY_FACTOR,
    ActivityParameter.CAPACITY_TO_ACTIVITY_UNIT,
    SupplyParameter.VARIABLE_OPERATION_COST,
    SupplyParameter.EMISSION_RATE,
    ActivityParameter.BY_MODE_UPPER_LIMIT,
    ActivityParameter.BY_MODE_LOWER_LIMIT,
)
_TECHNOLOGY_LIMITS: tuple[str, ...] = (
    SupplyParameter.ACTIVITY_UPPER_LIMIT,
    SupplyParameter.ACTIVITY_LOWER_LIMIT,
)


# --- the records -----------------------------------------------------------------------------


def _build_generator(row: dict[str, Any], year: int) -> GeneratorExtension:
    output = row[OUTPUTS][0]
    return GeneratorExtension(
        name=row[MODE_NAME],
        bus=output[FUEL_BUS],
        carrier=row[AnnotationColumn.CATEGORY] or output[FUEL_CARRIER],
        **_build_rated_fields(row, year),
    )


def _build_conversion(row: dict[str, Any], year: int) -> ConversionExtension:
    first_in = row[INPUTS][0]
    outputs = row[OUTPUTS]
    first_out = outputs[0] if outputs else None
    carrier_port = first_out or first_in
    return ConversionExtension(
        name=row[MODE_NAME],
        carrier=row[AnnotationColumn.CATEGORY] or carrier_port[FUEL_CARRIER],
        bus0=first_in[FUEL_BUS],
        bus1=None if first_out is None else first_out[FUEL_BUS],
        input_fuel=first_in[FUEL],
        output_fuel=None if first_out is None else first_out[FUEL],
        efficiency=None if first_out is None else first_out[RATIO] / row[RATED_RATIO],
        **_build_extra_ports(row),
        **_build_rated_fields(row, year),
    )


def _build_extra_ports(row: dict[str, Any]) -> dict[str, Any]:
    """A further input takes a negative efficiency, as PyPSA draws it from its bus."""
    rated = row[RATED_RATIO]
    extras = [(port[FUEL_BUS], -port[RATIO] / rated) for port in row[INPUTS][1:]]
    extras += [(port[FUEL_BUS], port[RATIO] / rated) for port in row[OUTPUTS][1:]]
    fields: dict[str, Any] = {}
    for (bus, efficiency), (bus_field, efficiency_field) in zip(
        extras, LINK_FURTHER_PORTS, strict=False
    ):
        fields[bus_field] = bus
        fields[efficiency_field] = efficiency
    return fields


def _build_rated_fields(row: dict[str, Any], year: int) -> dict[str, Any]:
    """The values of a mode for each MWh of the fuel that rates it."""
    rated = row[RATED_RATIO]
    marginal_cost = (row[COST_MWH] + row[PENALTY_MWH]) / rated
    fields: dict[str, Any] = {
        "p_nom": row[ACTIVITY_MW] * rated,
        "p_nom_extendable": True if row[IS_EXTENDABLE] else None,
        "p_nom_max": _build_rated_value(row[MAX_ACTIVITY_MW], rated)
        if row[IS_EXTENDABLE]
        else None,
        "marginal_cost": marginal_cost if marginal_cost != _NO_COST else None,
        "p_max_pu": row[AVAILABILITY] if row[AVAILABILITY] != WHOLE_CAPACITY else None,
        "emission_rates_t_per_mwh": _build_rates(row[RATES], rated),
        "e_sum_min": _build_yearly(row[E_MIN_MWH], rated, year),
        "e_sum_max": _build_yearly(row[E_MAX_MWH], rated, year),
    }
    return {name: value for name, value in fields.items() if value is not None}


def _build_rated_value(value: float | None, rated: float) -> float | None:
    return None if value is None else value * rated


def _build_rates(rates: list[dict[str, Any]] | None, rated: float) -> dict[str, float] | None:
    if not rates:
        return None
    return {rate[POLLUTANT]: rate[RATE_T_PER_MWH] / rated for rate in rates}


def _build_yearly(value: float | None, rated: float, year: int) -> ByYear | None:
    return None if value is None else {year: value * rated}


def _build_buses(modes: pl.DataFrame, loads: pl.DataFrame) -> pl.DataFrame:
    """Each fuel that is not electricity and that a mode or a load uses, once, by bus."""
    ports = [
        modes.select(pl.col(ports).alias(_PORT))
        .explode(_PORT, empty_as_null=True)
        .drop_nulls()
        .unnest(_PORT)
        for ports in (INPUTS, OUTPUTS)
    ]
    columns = [FUEL, FUEL_BUS, FUEL_CARRIER, FUEL_LOCATION]
    used = [table.filter(~pl.col(IS_ELECTRICITY)).select(columns) for table in ports]
    used.append(loads.select(columns))
    return pl.concat(used).unique(FUEL_BUS).sort(FUEL_BUS)


_PORT = "port"


def _build_bus(bus: dict[str, Any]) -> BusExtension:
    return BusExtension(name=bus[FUEL_BUS], carrier=bus[FUEL_CARRIER], location=bus[FUEL_LOCATION])


# --- the events ------------------------------------------------------------------------------


def _build_events(
    row: dict[str, Any], kind: ExtensionKind, record: GeneratorExtension | ConversionExtension
) -> list[TranslationEvent]:
    """One event for each field that the record states; a field with no `_VALUES` row raises."""
    stated = record.model_dump(exclude={"name"}, exclude_none=True, exclude_unset=True)
    return [_build_event(row, kind, field_name, value) for field_name, value in stated.items()]


def _build_event(
    row: dict[str, Any], kind: ExtensionKind, field_name: str, stated: Any
) -> TranslationEvent:
    value = _VALUES[field_name]
    return TranslationEvent(
        kind=EventKind.VALUE_DERIVED,
        sources=[
            source
            for parameter in value.parameters
            for source in _build_parameter_sources(row, parameter)
        ],
        destinations=[
            build_sienna_field(
                kind, row[MODE_NAME], f"{EXTENSIONS_PREFIX}{field_name}", stated, value.unit
            )
        ],
        derivation=value.derivation,
    )


def _build_parameter_sources(row: dict[str, Any], parameter: str) -> list[SourceField]:
    """The values of one parameter that a field reads: each flow, each rate, or one value."""
    name = row[MODE_REPORT_NAME]
    mode = f"mode {row[OPERATING_MODE]}"
    rates = row[RATES] or []
    if parameter in _FLOW_PORTS:
        return [
            build_osemosys_field(parameter, name, f"{port[FUEL]} at {mode}", port[RATIO])
            for port in row[_FLOW_PORTS[parameter]]
        ]
    if parameter == SupplyParameter.EMISSION_RATE:
        return [
            build_osemosys_field(
                parameter, name, f"{rate[POLLUTANT]} at {mode}", rate[_STATED_RATE]
            )
            for rate in rates
        ]
    if parameter == SupplyParameter.EMISSION_PENALTY:
        return [build_osemosys_field(parameter, name, rate[POLLUTANT]) for rate in rates]
    column = _STATED_COLUMNS.get(parameter)
    attribute = mode if parameter in _MODE_PARAMETERS else None
    return [
        build_osemosys_field(parameter, name, attribute, None if column is None else row[column])
    ]


def _build_bus_events(bus: dict[str, Any]) -> list[TranslationEvent]:
    return [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[build_osemosys_field(FUEL, bus[FUEL_BUS], value.attribute, bus[value.column])],
            destinations=[
                build_sienna_field(
                    ExtensionKind.BUS,
                    bus[FUEL_BUS],
                    f"{EXTENSIONS_PREFIX}{value.field_name}",
                    bus[value.column],
                )
            ],
            derivation=value.derivation,
        )
        for value in _BUS_VALUES
        if bus[value.column] is not None
    ]


class _BusValue(NamedTuple):
    """A field of a bus record, the annotation that states it, its column and how it derives."""

    field_name: str
    attribute: str
    column: str
    derivation: str


_BUS_VALUES = (
    _BusValue(
        "carrier",
        AnnotationColumn.CARRIER,
        FUEL_CARRIER,
        "the carrier of the fuel, or the name of the fuel where it states none; a fuel that "
        "is not electricity balances in its region, so its bus is <region>/<fuel>",
    ),
    _BusValue("location", AnnotationColumn.LOCATION, FUEL_LOCATION, "the location of the fuel"),
)
_FLOWS = (FlowParameter.INPUT_ACTIVITY_RATIO, FlowParameter.OUTPUT_ACTIVITY_RATIO)
# The ports of a mode that hold each flow parameter.
_FLOW_PORTS: dict[str, str] = {
    FlowParameter.INPUT_ACTIVITY_RATIO: INPUTS,
    FlowParameter.OUTPUT_ACTIVITY_RATIO: OUTPUTS,
}
# The field of each rate of a mode that holds the rate as the model states it.
_STATED_RATE = "stated_rate"
# The column of the mode row that holds the stated value of each other parameter.
_STATED_COLUMNS: dict[str, str] = {
    SupplyParameter.RESIDUAL_CAPACITY: RESIDUAL,
    ActivityParameter.CAPACITY_TO_ACTIVITY_UNIT: CTAU,
    SupplyParameter.AVAILABILITY_FACTOR: AVAILABILITY,
    SupplyParameter.VARIABLE_OPERATION_COST: VARIABLE_COST,
    InvestmentParameter.CAPITAL_COST: CAPITAL_COST,
    SupplyParameter.FIXED_COST: FIXED_COST,
    InvestmentParameter.MAX_CAPACITY_INVESTMENT: MAX_INVESTMENT,
    InvestmentParameter.CAPACITY_LIMITS_MAX: MAX_CAPACITY,
    AnnotationColumn.CATEGORY: AnnotationColumn.CATEGORY,
}
_MODE_PARAMETERS = (
    SupplyParameter.VARIABLE_OPERATION_COST,
    ActivityParameter.BY_MODE_UPPER_LIMIT,
    ActivityParameter.BY_MODE_LOWER_LIMIT,
)
_CAPACITY = (
    SupplyParameter.RESIDUAL_CAPACITY,
    ActivityParameter.CAPACITY_TO_ACTIVITY_UNIT,
    *_FLOWS,
)
_RATED = "for each MWh of the fuel that rates the component"
_VALUES: dict[str, _Value] = {
    "bus": _Value(
        (FlowParameter.OUTPUT_ACTIVITY_RATIO,),
        None,
        "the bus of the fuel that the mode puts out",
    ),
    "carrier": _Value(
        (AnnotationColumn.CATEGORY,),
        None,
        "the category of the technology, else the carrier of its fuel",
    ),
    "bus0": _Value(
        (FlowParameter.INPUT_ACTIVITY_RATIO,),
        None,
        "the bus of the largest fuel that the mode takes in",
    ),
    "bus1": _Value(
        (FlowParameter.OUTPUT_ACTIVITY_RATIO,),
        None,
        "the bus of the largest fuel that the mode puts out",
    ),
    "bus2": _Value(_FLOWS, None, "the bus of a third fuel of the mode"),
    "bus3": _Value(_FLOWS, None, "the bus of a fourth fuel of the mode"),
    "input_fuel": _Value(
        (FlowParameter.INPUT_ACTIVITY_RATIO,),
        None,
        "the largest fuel that the mode takes in",
    ),
    "output_fuel": _Value(
        (FlowParameter.OUTPUT_ACTIVITY_RATIO,),
        None,
        "the largest fuel that the mode puts out",
    ),
    "efficiency": _Value(
        _FLOWS, None, "output_activity_ratio of bus1 / input_activity_ratio of bus0"
    ),
    "efficiency2": _Value(
        _FLOWS,
        None,
        "the ratio of the third fuel / input_activity_ratio of bus0, negative for an input",
    ),
    "efficiency3": _Value(
        _FLOWS,
        None,
        "the ratio of the fourth fuel / input_activity_ratio of bus0, negative for an input",
    ),
    "p_nom": _Value(
        _CAPACITY,
        UNIT_MW,
        f"residual_capacity × capacity_to_activity_unit, in MWh, / 8760 h, {_RATED}",
    ),
    "p_nom_extendable": _Value(
        FREE_BUILD_PARAMETERS,
        None,
        "capital_cost and fixed_cost are 0, and the year may build more capacity, so the model "
        "builds capacity of the technology at no cost",
    ),
    "p_nom_max": _Value(
        (
            InvestmentParameter.CAPACITY_LIMITS_MAX,
            SupplyParameter.RESIDUAL_CAPACITY,
            InvestmentParameter.MAX_CAPACITY_INVESTMENT,
            ActivityParameter.CAPACITY_TO_ACTIVITY_UNIT,
        ),
        UNIT_MW,
        "min(total_annual_max_capacity, residual_capacity + total_annual_max_capacity_investment), "
        f"converted as p_nom is, {_RATED}",
    ),
    "marginal_cost": _Value(
        (
            SupplyParameter.VARIABLE_OPERATION_COST,
            SupplyParameter.EMISSION_RATE,
            SupplyParameter.EMISSION_PENALTY,
        ),
        UNIT_DOLLARS_PER_MWH,
        f"(variable_operation_cost + Σ emission_rate × emission_penalty) in $/MWh, {_RATED}",
    ),
    "p_max_pu": _Value(
        (SupplyParameter.AVAILABILITY_FACTOR,),
        None,
        "availability_factor of the operations year",
    ),
    "emission_rates_t_per_mwh": _Value(
        (SupplyParameter.EMISSION_RATE,),
        UNIT_TONNES_PER_MWH,
        f"emission_rate, in t/MWh of activity, {_RATED}",
    ),
    "e_sum_min": _Value(
        (SupplyParameter.ACTIVITY_LOWER_LIMIT, ActivityParameter.BY_MODE_LOWER_LIMIT),
        UNIT_MWH,
        f"the larger lower limit of the mode and of a one-mode technology, in MWh, {_RATED}",
    ),
    "e_sum_max": _Value(
        (SupplyParameter.ACTIVITY_UPPER_LIMIT, ActivityParameter.BY_MODE_UPPER_LIMIT),
        UNIT_MWH,
        f"the smaller upper limit of the mode and of a one-mode technology, in MWh, {_RATED}",
    ),
}
