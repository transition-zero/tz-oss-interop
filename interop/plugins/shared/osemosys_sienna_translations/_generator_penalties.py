"""What a generator pays for each MWh for the pollutants that it emits.

OSeMOSYS charges `emission_penalty` of the region for each unit of a pollutant. The cost for
each MWh is the emission rate of the generator in t/MWh, which holds the rate of the fuel that
it burns, × the penalty in $/t. A negative rate gives a credit, as it does in OSeMOSYS.
"""

from __future__ import annotations

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.osemosys_canonical.constants import (
    POLLUTANT,
    REGION,
    TECHNOLOGY,
    VALUE_COL,
)
from interop.plugins.shared.osemosys_sienna_constants import SupplyParameter
from interop.plugins.shared.osemosys_sienna_translations._canonical import (
    read_parameter_with_defaults,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_costs import (
    VARIABLE_COST_MWH,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_emissions import (
    EMISSION_TERMS,
    RATE_T_PER_MWH,
)
from interop.plugins.shared.osemosys_sienna_translations._operations import OperationsYear
from interop.plugins.shared.osemosys_sienna_translations._units import express_converted

PENALTY_TERMS = "penalty_terms"
PENALTY = "penalty"
PENALTY_PER_TONNE = "penalty_per_tonne"
PENALTY_COST_MWH = "penalty_cost_mwh"
EMISSION_COST_MWH = "emission_cost_mwh"
OPERATION_COST_MWH = "operation_cost_mwh"

_KEYS = [REGION, TECHNOLOGY]
_PENALTY_KEYS = [REGION, POLLUTANT]
_NO_COST = 0.0


def enrich_emission_penalties(
    state: State, operations: OperationsYear, generators: pl.DataFrame
) -> pl.DataFrame:
    """The penalty of each pollutant for each MWh, and the variable cost with their sum.

    `generators` holds the emission terms and the variable cost of each generator.
    """
    priced = _build_penalty_terms(state, operations, _list_emission_rates(generators))
    listed = (
        priced.sort(POLLUTANT)
        .group_by(_KEYS)
        .agg(
            pl.struct(
                POLLUTANT, RATE_T_PER_MWH, PENALTY, PENALTY_PER_TONNE, PENALTY_COST_MWH
            ).alias(PENALTY_TERMS),
            pl.col(PENALTY_COST_MWH).sum().alias(EMISSION_COST_MWH),
        )
    )
    table = generators.join(listed, on=_KEYS, how="left").with_columns(
        pl.col(EMISSION_COST_MWH).fill_null(_NO_COST)
    )
    total = pl.col(VARIABLE_COST_MWH) + pl.col(EMISSION_COST_MWH)
    return table.with_columns(total.alias(OPERATION_COST_MWH))


def _list_emission_rates(generators: pl.DataFrame) -> pl.DataFrame:
    """One row for each generator and pollutant that it emits, with the rate in t/MWh."""
    return (
        generators.select(*_KEYS, EMISSION_TERMS)
        .explode(EMISSION_TERMS)
        .drop_nulls(EMISSION_TERMS)
        .select(
            *_KEYS,
            pl.col(EMISSION_TERMS).struct.field(POLLUTANT),
            pl.col(EMISSION_TERMS).struct.field(RATE_T_PER_MWH),
        )
    )


def _build_penalty_terms(
    state: State, operations: OperationsYear, rates: pl.DataFrame
) -> pl.DataFrame:
    keys = rates.select(_PENALTY_KEYS).unique()
    penalties = read_parameter_with_defaults(
        state, SupplyParameter.EMISSION_PENALTY, operations.year, keys
    ).select(*_PENALTY_KEYS, pl.col(VALUE_COL).cast(pl.Float64).alias(PENALTY))
    priced = rates.join(penalties.filter(pl.col(PENALTY) != 0), on=_PENALTY_KEYS)
    convert = operations.units.convert_cost_per_emissions_to_dollars_per_tonne
    per_tonne = express_converted(priced, PENALTY, convert)
    return priced.with_columns(per_tonne.alias(PENALTY_PER_TONNE)).with_columns(
        (pl.col(RATE_T_PER_MWH) * pl.col(PENALTY_PER_TONNE)).alias(PENALTY_COST_MWH)
    )
