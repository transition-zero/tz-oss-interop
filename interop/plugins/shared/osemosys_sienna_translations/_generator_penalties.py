"""What a generator pays for each MWh for the pollutants that it emits.

OSeMOSYS charges `emission_penalty` of the region for each unit of a pollutant. The cost for
each MWh is the emission rate of the generator in t/MWh, which holds the rate of the fuel that
it burns, × the penalty in $/t. A negative rate gives a credit, as it does in OSeMOSYS.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import NamedTuple

import polars as pl

from interop.core.extensions import ExtensionKind
from interop.core.pipeline import State
from interop.plugins.shared.osemosys_canonical.constants import (
    POLLUTANT,
    REGION,
    TECHNOLOGY,
)
from interop.plugins.shared.osemosys_sienna_constants import NO_COST
from interop.plugins.shared.osemosys_sienna_translations._generator_costs import (
    VARIABLE_COST_MWH,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_emissions import (
    EMISSION_TERMS,
    PENALTY,
    PENALTY_PER_TONNE,
    RATE_T_PER_MWH,
    read_emission_penalties,
)
from interop.plugins.shared.osemosys_sienna_translations._operations import OperationsYear
from interop.plugins.shared.osemosys_sienna_translations._persisted import set_persisted_rows

PENALTY_TERMS = "penalty_terms"
PENALTY_COST_MWH = "penalty_cost_mwh"
EMISSION_COST_MWH = "emission_cost_mwh"
OPERATION_COST_MWH = "operation_cost_mwh"

_KEYS = [REGION, TECHNOLOGY]
_PENALTY_KEYS = [REGION, POLLUTANT]


class PenaltyNote(NamedTuple):
    """The kind of the records that apply a penalty, and a scope that keeps their note apart."""

    kind: ExtensionKind
    scope: str


GENERATOR_PENALTIES = PenaltyNote(ExtensionKind.GENERATOR, "generator-penalties")
IMPORT_PENALTIES = PenaltyNote(ExtensionKind.GENERATOR, "import-penalties")


def enrich_emission_penalties(
    state: State, operations: OperationsYear, generators: pl.DataFrame
) -> pl.DataFrame:
    """The penalty of each pollutant for each MWh, and the variable cost with their sum.

    `generators` holds the emission terms and the variable cost of each generator.
    """
    priced = build_penalty_terms(state, operations, _list_emission_rates(generators))
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
        pl.col(EMISSION_COST_MWH).fill_null(NO_COST)
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


def build_penalty_keys(table: pl.DataFrame, rate_cols: Sequence[str]) -> pl.DataFrame:
    """The region and pollutant of each rate in the lists of `rate_cols`, once each."""
    keys = [
        table.select(REGION, column)
        .explode(column)
        .drop_nulls(column)
        .select(REGION, pl.col(column).struct.field(POLLUTANT))
        for column in rate_cols
    ]
    return pl.concat(keys).unique()


def set_penalties_persisted(state: State, note: PenaltyNote, keys: pl.DataFrame) -> None:
    """Note that the records apply the emission penalty of each region and pollutant of `keys`."""
    set_persisted_rows(state, note.kind, SupplyParameter.EMISSION_PENALTY, [keys], note.scope)


def build_penalty_terms(
    state: State, operations: OperationsYear, rates: pl.DataFrame
) -> pl.DataFrame:
    """The rows of `rates` whose pollutant has a penalty in their region, with its cost per MWh.

    `rates` holds `region`, `pollutant` and the rate in t/MWh, with any other key columns.
    """
    penalties = read_emission_penalties(state, operations, rates)
    priced = rates.join(penalties.filter(pl.col(PENALTY) != NO_COST), on=_PENALTY_KEYS)
    return priced.with_columns(
        (pl.col(RATE_T_PER_MWH) * pl.col(PENALTY_PER_TONNE)).alias(PENALTY_COST_MWH)
    )
