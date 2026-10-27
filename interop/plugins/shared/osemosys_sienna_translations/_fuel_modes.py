"""OSeMOSYS technologies of the fuels that are not electricity, one row for each operating mode.

Sienna holds electricity only, so a technology that supplies, moves or converts another fuel
has no Sienna component. Each operating mode that has a flow in the operations year becomes one
PyPSA component, which extensions.json holds:

- a mode that takes in nothing and puts out one fuel is a Generator on the bus of the fuel;
- a mode that takes in and puts out is a Link from the bus of its largest input to the bus of
  its largest output, with a third and a fourth fuel at bus2 and bus3;
- a mode that takes in and puts out nothing is a Link with no bus1, which no network holds.

A technology rates its capacity in units of activity. One unit of capacity runs
`capacity_to_activity_unit` of activity in a year, so a mode rates `residual_capacity` ×
`capacity_to_activity_unit` / 8760 h, in MW of activity. A model that declares no
`capacity_to_activity_unit` takes the canonical default of 1, so its capacity is the activity
of a year. Only a canonical stage with no default converts with the capacity unit. Each mode can
run at the whole capacity, where OSeMOSYS shares the capacity among the modes. A technology that
the model builds at no cost in the year is extendable, up to the limit that `_free_build` gives.
"""

from __future__ import annotations

import polars as pl

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.osemosys_canonical.constants import (
    FUEL,
    OPERATING_MODE,
    OSEMOSYS_FRAMEWORK,
    POLLUTANT,
    REGION,
    TECHNOLOGY,
    VALUE_COL,
    FlowParameter,
)
from interop.plugins.shared.osemosys_sienna_constants import (
    LOAD_NAME_SEPARATOR,
    NO_COST,
    OSEMOSYS_TO_SIENNA_PIPELINE,
    TECHNOLOGIES_LABEL,
    ActivityParameter,
    SupplyParameter,
)
from interop.plugins.shared.osemosys_sienna_translations._activity import (
    enrich_capacity_to_activity,
    express_activity_mw,
)
from interop.plugins.shared.osemosys_sienna_translations._activity_limits import (
    LOWER_BOUND,
    UPPER_BOUND,
)
from interop.plugins.shared.osemosys_sienna_translations._canonical import (
    read_parameter,
)
from interop.plugins.shared.osemosys_sienna_translations._free_build import (
    BUILD_AVAILABILITY,
    BUILD_LIMIT,
    IS_FREE_TO_BUILD,
    RESIDUAL,
    enrich_free_build,
    express_has_fleet,
    express_is_available,
)
from interop.plugins.shared.osemosys_sienna_translations._fuels import (
    FUEL_BUS,
    FUEL_CARRIER,
    FUEL_LOCATION,
    IS_ELECTRICITY,
    read_fuel_buses,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_emissions import (
    ACTIVITY_RATE_T_PER_MWH,
    PENALTY_PER_TONNE,
    STATED_RATE,
    read_emission_penalties,
    read_emission_rates,
)
from interop.plugins.shared.osemosys_sienna_translations._left_out import (
    HAS_FLOWS,
    IS_ALL_ELECTRICITY,
    read_left_out_technologies,
)
from interop.plugins.shared.osemosys_sienna_translations._names import express_component_name
from interop.plugins.shared.osemosys_sienna_translations._operations import OperationsYear
from interop.plugins.shared.osemosys_sienna_translations._technology_columns import (
    TECHNOLOGY_NAME,
)
from interop.plugins.shared.osemosys_sienna_translations._units import (
    express_converted,
)
from interop.plugins.shared.translation_runner import (
    SkippedNames,
    SkipReport,
    SkipRule,
    filter_component,
)

# One row for each operating mode, in OSeMOSYS words, before any record exists.
MODE_NAME = "mode_name"
MODE_REPORT_NAME = "mode_report_name"
ROLE = "role"
INPUTS = "inputs"
OUTPUTS = "outputs"
RATIO = "ratio"
RATED_RATIO = "rated_ratio"
AVAILABILITY = "availability"
VARIABLE_COST = "variable_cost"
ACTIVITY_MW = "activity_mw"
MAX_ACTIVITY_MW = "max_activity_mw"
IS_EXTENDABLE = "is_extendable"
COST_MWH = "cost_mwh"
PENALTY_MWH = "penalty_mwh"
RATES = "rates"
RATE_T_PER_MWH = "rate_t_per_mwh"
E_MIN_MWH = "e_min_mwh"
E_MAX_MWH = "e_max_mwh"
MODE_COUNT = "mode_count"
IS_INPUT = "is_input"

# What a mode does in the network.
SUPPLY = "supply"
LINK = "link"
EXPORT = "export"
# A PyPSA Link of this hop holds bus0, bus1, bus2 and bus3.
MAX_LINK_FUELS = 4

_KEYS = [REGION, TECHNOLOGY]
_MODE_KEYS = [REGION, TECHNOLOGY, OPERATING_MODE]
_MODE_SUFFIX = "mode"
_PENALTY_COST = "penalty_cost"
_TECH_LOWER = "technology_lower"
_TECH_UPPER = "technology_upper"
_MODE_LOWER = "mode_lower"
_MODE_UPPER = "mode_upper"
_COUNTED_NOUN = "fuel technology mode(s)"
_LISTED = SkippedNames(column=MODE_REPORT_NAME, label=TECHNOLOGIES_LABEL)


def _build_skip(reason: str, note: str, attribute_col: str | None = None) -> SkipReport:
    return SkipReport(
        pipeline=OSEMOSYS_TO_SIENNA_PIPELINE,
        framework=OSEMOSYS_FRAMEWORK,
        component=TECHNOLOGY,
        name_col=MODE_REPORT_NAME,
        reason=reason,
        counted_noun=_COUNTED_NOUN,
        note=note,
        listed=_LISTED,
        attribute_col=attribute_col,
    )


NO_BUS_SKIP = _build_skip(
    "use an electricity fuel with no location",
    "an electricity fuel with no location has no bus, so the mode has nowhere to connect",
)
SEVERAL_OUTPUTS_SKIP = _build_skip(
    "take in nothing and put out more than one fuel",
    "a PyPSA Generator puts out at one bus, so a supply of two fuels has no component",
)
MANY_FUELS_SKIP = _build_skip(
    f"take in and put out more than {MAX_LINK_FUELS} fuels",
    f"a link of this translation joins {MAX_LINK_FUELS} buses at most, so the mode has no "
    "component",
)
NO_CAPACITY_SKIP = _build_skip(
    "have no residual capacity in the operations year, and the model builds none at no cost",
    "the fleet of the operations year is its residual capacity, which holds none of it",
    RESIDUAL,
)
NO_AVAILABILITY_SKIP = _build_skip(
    "have an availability factor of 0 in the operations year",
    "an availability factor of 0 lets the technology run at none of its capacity in the year",
    AVAILABILITY,
)
CLOSED_SKIP = _build_skip(
    "may not run in the operations year",
    "an annual activity upper limit of 0 closes the technology in the year",
    E_MAX_MWH,
)

_PORT = pl.struct(
    pl.col(FUEL),
    pl.col(FUEL_BUS),
    pl.col(RATIO),
    pl.col(IS_ELECTRICITY),
    FUEL_CARRIER,
    FUEL_LOCATION,
)


def build_fuel_modes_source(
    state: State, operations: OperationsYear, recorder: ScopedRecorder
) -> pl.DataFrame:
    """One row for each mode that a component of the network runs, with its values."""
    modes = _read_modes(state, operations)
    if modes.height == 0:
        return modes
    modes = _enrich_capacity(state, operations, modes)
    modes = _enrich_bounds(state, operations, modes)
    for rule in _SKIP_RULES:
        modes, _ = filter_component(modes, rule.keep, rule.report, recorder)
    modes = _enrich_costs(state, operations, modes)
    return modes.sort(MODE_NAME)


def express_port(ports: str, index: int, field: str) -> pl.Expr:
    """One field of one fuel of a list of ports, or null where the list is shorter."""
    return pl.col(ports).list.get(index, null_on_oob=True).struct.field(field)


# --- the modes of the year ----------------------------------------------------------------


def _read_modes(state: State, operations: OperationsYear) -> pl.DataFrame:
    technologies = _read_technologies(state, operations)
    flows = _read_flows(state, operations.year, technologies)
    modes = (
        flows.sort([RATIO, FUEL], descending=[True, False])
        .group_by(_MODE_KEYS, maintain_order=True)
        .agg(
            _PORT.filter(pl.col(IS_INPUT)).alias(INPUTS),
            _PORT.filter(~pl.col(IS_INPUT)).alias(OUTPUTS),
        )
        .join(technologies, on=_KEYS)
    )
    return (
        _enrich_names(operations, modes)
        .with_columns(_express_role().alias(ROLE))
        .with_columns(_express_rated_ratio().alias(RATED_RATIO))
    )


def _read_technologies(state: State, operations: OperationsYear) -> pl.DataFrame:
    """Each technology with a flow in the year whose fuels are not all electricity."""
    technologies = read_left_out_technologies(state, operations).filter(
        ~pl.col(IS_ALL_ELECTRICITY) & pl.col(HAS_FLOWS)
    )
    return technologies.with_columns(express_component_name(TECHNOLOGY).alias(MODE_NAME))


def _read_flows(state: State, year: int, technologies: pl.DataFrame) -> pl.DataFrame:
    directions = (
        (FlowParameter.INPUT_ACTIVITY_RATIO, True),
        (FlowParameter.OUTPUT_ACTIVITY_RATIO, False),
    )
    flows = pl.concat(
        [
            read_parameter(state, parameter, year)
            .filter(pl.col(VALUE_COL) > 0)
            .join(technologies.select(_KEYS), on=_KEYS, how="semi")
            .select(
                *_MODE_KEYS,
                FUEL,
                pl.col(VALUE_COL).cast(pl.Float64).alias(RATIO),
                pl.lit(is_input).alias(IS_INPUT),
            )
            for parameter, is_input in directions
        ]
    )
    return flows.join(read_fuel_buses(state), on=[REGION, FUEL], how="left")


def _enrich_names(operations: OperationsYear, modes: pl.DataFrame) -> pl.DataFrame:
    """A technology of one mode, or the operations mode of a technology, takes the name of the
    technology; another mode takes `<name>/mode<mode>`."""
    count = pl.len().over(_KEYS)
    is_plain = (count == 1) | (pl.col(OPERATING_MODE) == operations.mode)
    suffix = (
        pl.when(is_plain)
        .then(pl.lit(""))
        .otherwise(
            pl.concat_str(pl.lit(f"{LOAD_NAME_SEPARATOR}{_MODE_SUFFIX}"), pl.col(OPERATING_MODE))
        )
    )
    return modes.with_columns(
        count.alias(MODE_COUNT),
        pl.concat_str(pl.col(MODE_NAME), suffix).alias(MODE_NAME),
        pl.concat_str(pl.col(TECHNOLOGY_NAME), suffix).alias(MODE_REPORT_NAME),
    )


def _express_role() -> pl.Expr:
    takes_in = pl.col(INPUTS).list.len() > 0
    puts_out = pl.col(OUTPUTS).list.len() > 0
    return (
        pl.when(~takes_in)
        .then(pl.lit(SUPPLY))
        .when(~puts_out)
        .then(pl.lit(EXPORT))
        .otherwise(pl.lit(LINK))
    )


def _express_rated_ratio() -> pl.Expr:
    """A supply rates on the fuel that it puts out, a link on its largest input."""
    is_supply = pl.col(ROLE) == SUPPLY
    return (
        pl.when(is_supply)
        .then(express_port(OUTPUTS, 0, RATIO))
        .otherwise(express_port(INPUTS, 0, RATIO))
    )


# --- the capacity -------------------------------------------------------------------------


def _enrich_capacity(state: State, operations: OperationsYear, modes: pl.DataFrame) -> pl.DataFrame:
    table = enrich_free_build(state, operations.year, modes)
    table = enrich_capacity_to_activity(state, operations.year, table)
    table = table.with_columns(
        pl.col(BUILD_AVAILABILITY).alias(AVAILABILITY), pl.col(BUILD_LIMIT).alias(MAX_ACTIVITY_MW)
    )
    return table.with_columns(
        express_activity_mw(table, RESIDUAL, operations.units).alias(ACTIVITY_MW),
        express_activity_mw(table, MAX_ACTIVITY_MW, operations.units).alias(MAX_ACTIVITY_MW),
        pl.col(IS_FREE_TO_BUILD).alias(IS_EXTENDABLE),
    )


# --- the annual bounds -----------------------------------------------------------------------


def _enrich_bounds(state: State, operations: OperationsYear, modes: pl.DataFrame) -> pl.DataFrame:
    """MWh of activity in the year. A bound of the technology applies to a technology of one
    mode, as the modes of another are separate components."""
    table = _enrich_stated_bounds(state, operations, modes)
    energy = operations.units.convert_energy_to_mwh
    is_single = pl.col(MODE_COUNT) == 1
    upper = _express_tightest(
        pl.when(pl.col(_MODE_UPPER) > 0).then(pl.col(_MODE_UPPER)),
        pl.when(is_single & UPPER_BOUND.binds(pl.col(_TECH_UPPER))).then(pl.col(_TECH_UPPER)),
    ).list.min()
    lower = _express_tightest(
        pl.when(pl.col(_MODE_LOWER) > 0).then(pl.col(_MODE_LOWER)),
        pl.when(is_single & LOWER_BOUND.binds(pl.col(_TECH_LOWER))).then(pl.col(_TECH_LOWER)),
    ).list.max()
    table = table.with_columns(upper.alias(E_MAX_MWH), lower.alias(E_MIN_MWH))
    return table.with_columns(
        express_converted(table, E_MAX_MWH, energy),
        express_converted(table, E_MIN_MWH, energy),
    ).drop(_MODE_UPPER, _MODE_LOWER, _TECH_UPPER, _TECH_LOWER)


def _express_tightest(*bounds: pl.Expr) -> pl.Expr:
    """The bounds that bind, as a list; min_horizontal fails on columns that are all null."""
    return pl.concat_list(*bounds).list.drop_nulls()


def _enrich_stated_bounds(
    state: State, operations: OperationsYear, modes: pl.DataFrame
) -> pl.DataFrame:
    table = modes
    for parameter, column, keys in _BOUNDS:
        stated = read_parameter(state, parameter, operations.year).select(
            *keys, pl.col(VALUE_COL).cast(pl.Float64).alias(column)
        )
        table = table.join(stated, on=keys, how="left")
    return table


_BOUNDS: tuple[tuple[str, str, list[str]], ...] = (
    (SupplyParameter.ACTIVITY_UPPER_LIMIT, _TECH_UPPER, _KEYS),
    (SupplyParameter.ACTIVITY_LOWER_LIMIT, _TECH_LOWER, _KEYS),
    (ActivityParameter.BY_MODE_UPPER_LIMIT, _MODE_UPPER, _MODE_KEYS),
    (ActivityParameter.BY_MODE_LOWER_LIMIT, _MODE_LOWER, _MODE_KEYS),
)


# --- the costs and the emissions ------------------------------------------------------------


def _enrich_costs(state: State, operations: OperationsYear, modes: pl.DataFrame) -> pl.DataFrame:
    """$/MWh and t/MWh of activity: the variable cost, the emission rates and their penalty."""
    units = operations.units
    costs = read_parameter(state, SupplyParameter.VARIABLE_OPERATION_COST, operations.year)
    costs = costs.select(*_MODE_KEYS, pl.col(VALUE_COL).cast(pl.Float64).alias(VARIABLE_COST))
    table = modes.join(costs, on=_MODE_KEYS, how="left").with_columns(
        pl.col(VARIABLE_COST).fill_null(NO_COST)
    )
    convert = units.convert_cost_per_energy_to_dollars_per_mwh
    table = table.with_columns(express_converted(table, VARIABLE_COST, convert).alias(COST_MWH))
    rates = _read_rates(state, operations, table)
    return table.join(rates, on=_MODE_KEYS, how="left").with_columns(
        pl.col(PENALTY_MWH).fill_null(NO_COST)
    )


def _read_rates(state: State, operations: OperationsYear, modes: pl.DataFrame) -> pl.DataFrame:
    """One list of pollutant rates for each mode that emits, and the penalty of the list."""
    rates = read_emission_rates(state, operations, modes)
    penalties = read_emission_penalties(state, operations, rates)
    priced = rates.join(penalties, on=[REGION, POLLUTANT], how="left").with_columns(
        (pl.col(ACTIVITY_RATE_T_PER_MWH) * pl.col(PENALTY_PER_TONNE)).alias(_PENALTY_COST)
    )
    return (
        priced.sort(POLLUTANT)
        .group_by(_MODE_KEYS)
        .agg(
            pl.struct(
                POLLUTANT,
                STATED_RATE,
                pl.col(ACTIVITY_RATE_T_PER_MWH).alias(RATE_T_PER_MWH),
            ).alias(RATES),
            pl.col(_PENALTY_COST).sum().alias(PENALTY_MWH),
        )
    )


# --- the rules ----------------------------------------------------------------------------


def _express_has_buses() -> pl.Expr:
    def has_no_null_bus(ports: str) -> pl.Expr:
        return ~pl.col(ports).list.eval(pl.element().struct.field(FUEL_BUS).is_null()).list.any()

    return has_no_null_bus(INPUTS) & has_no_null_bus(OUTPUTS)


def _express_fuel_count() -> pl.Expr:
    return pl.col(INPUTS).list.len() + pl.col(OUTPUTS).list.len()


_SKIP_RULES = (
    SkipRule(_express_has_buses(), NO_BUS_SKIP),
    SkipRule((pl.col(ROLE) != SUPPLY) | (pl.col(OUTPUTS).list.len() == 1), SEVERAL_OUTPUTS_SKIP),
    SkipRule(_express_fuel_count() <= MAX_LINK_FUELS, MANY_FUELS_SKIP),
    SkipRule(express_has_fleet(), NO_CAPACITY_SKIP),
    SkipRule(express_is_available(), NO_AVAILABILITY_SKIP),
    SkipRule(pl.col(E_MAX_MWH).is_null() | (pl.col(E_MAX_MWH) > 0), CLOSED_SKIP),
)
