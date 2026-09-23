"""What a generator burning a dated fuel costs, snapshot by snapshot.

A PLEXOS Fuel priced by date moves the marginal cost of every generator burning it. A
Sienna cost curve states one price, so the varying cost has no field on the component. It
rides a column of the generator companion parquet beside the extensions sidecar, and the
hop that reads the sidecar writes it onto its own generator.

The frame stays lazy, so a price series of any length crosses the hub without being read
into memory.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from interop.core.extensions import CompanionSeriesCol, GeneratorCompanionCol
from interop.core.pipeline import State
from interop.plugins.shared.constants import StagedTimeSeriesCol
from interop.plugins.shared.plexos_constants import PlexosClass, PlexosProperty
from interop.plugins.shared.plexos_pypsa_translations._generator_derivation import GeneratorMapping
from interop.plugins.shared.pypsa_time_series import series_components

# The terms the price rides through, joined on so the arithmetic happens inside the frame.
_HEAT_RATE = "heat_rate"
_COST_WITHOUT_FUEL = "cost_without_fuel"


@dataclass(frozen=True)
class FuelPriceSeries:
    """The companion frame, and the generators whose record names a column of it."""

    frame: pl.LazyFrame | None
    names: frozenset[str]


@dataclass(frozen=True)
class _Burner:
    """One generator, the fuel it burns and what it pays for anything other than that fuel."""

    fuel: str
    name: str
    heat_rate: float
    cost_without_fuel: float


def build_fuel_price_series(state: State, mappings: list[GeneratorMapping]) -> FuelPriceSeries:
    """The marginal cost of each generator whose fuel the model prices by date."""
    burners = _burners(state, mappings)
    if not burners:
        return FuelPriceSeries(None, frozenset())
    staged = state.source_time_series[(PlexosClass.FUEL, PlexosProperty.PRICE)]
    return FuelPriceSeries(
        frame=_priced(staged, burners),
        names=frozenset(burner.name for burner in burners),
    )


def _burners(state: State, mappings: list[GeneratorMapping]) -> list[_Burner]:
    """Each generator burning a fuel the source staged a price series for."""
    staged = state.source_time_series.get((PlexosClass.FUEL, PlexosProperty.PRICE))
    if staged is None:
        return []
    priced = set(series_components(staged))
    return [
        _Burner(terms.fuel_name, mapping.name, terms.heat_rate, terms.cost_without_fuel)
        for mapping in mappings
        if (terms := mapping.cost.thermal_terms) is not None and terms.fuel_name in priced
    ]


def _priced(staged: pl.LazyFrame, burners: list[_Burner]) -> pl.LazyFrame:
    """The fuel's price read through each burning generator's heat rate and other costs."""
    terms = pl.LazyFrame(
        {
            StagedTimeSeriesCol.COMPONENT: [burner.fuel for burner in burners],
            CompanionSeriesCol.NAME: [burner.name for burner in burners],
            _HEAT_RATE: [burner.heat_rate for burner in burners],
            _COST_WITHOUT_FUEL: [burner.cost_without_fuel for burner in burners],
        }
    )
    return (
        staged.join(terms, on=StagedTimeSeriesCol.COMPONENT, how="inner")
        .select(
            pl.col(StagedTimeSeriesCol.SNAPSHOT).alias(CompanionSeriesCol.SNAPSHOT),
            pl.col(CompanionSeriesCol.NAME),
            (
                pl.col(StagedTimeSeriesCol.VALUE) * pl.col(_HEAT_RATE) + pl.col(_COST_WITHOUT_FUEL)
            ).alias(GeneratorCompanionCol.MARGINAL_COST),
        )
        .sort(CompanionSeriesCol.NAME, CompanionSeriesCol.SNAPSHOT)
    )
