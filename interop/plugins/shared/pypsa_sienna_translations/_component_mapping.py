from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import polars as pl

from interop.core.extensions import ExtensionKind, ExtensionRecord
from interop.plugins.shared.pypsa_sienna_translations._ts_info import TimeSeriesInfo
from interop.plugins.shared.pypsa_sienna_user_mappings import CarrierMappings
from interop.plugins.shared.sienna_constants import SiennaComponent
from interop.plugins.shared.translation_runner import SkipRule, Translation


@dataclass(frozen=True)
class ExtensionSpec:
    """What a component family sets aside, and which kind of the document it belongs to.

    One field rather than two optionals, so a builder cannot be wired up without saying
    where its records go, and cannot be silently ignored by saying only that.
    """

    kind: ExtensionKind
    build: Callable[[pl.DataFrame, pl.DataFrame], Sequence[ExtensionRecord]]


@dataclass(frozen=True)
class DerivedSeries:
    """A time series a mapping computes from its own rows and its own source series.

    The step puts the result back among the source series under ``attribute``, so a sink
    streams it like any series the network itself stated.
    """

    attribute: str
    build: Callable[[pl.DataFrame, pl.LazyFrame], pl.LazyFrame]


# A skip reads the mapping's own source series, which is None where the network states none.
SkipForSeries = Callable[[pl.LazyFrame | None], SkipRule]


@dataclass(frozen=True)
class ComponentMapping:
    """Declarative recipe for a carrier-filtered PyPSA component -> Sienna component.

    Each translation module assembles the recipe for its own component family and exports it;
    ``PypsaToSiennaMapComponents._map_one`` runs it (fill, filter, skip, enrich, translate).
    The carrier scope is resolved at runtime from the user carrier mapping
    (``get_carriers(sienna_component)``), not hardcoded here. Components whose flow does not
    fit this shape (buses, loads, lines' dynamic-rating guard, links' bus-scope filter) stay
    as bespoke step methods.

    A drop the whole source table shares, such as a bus that is not a translated AC bus,
    belongs to the step's per-table scope pass, not here. ``skip``, when set, drops the rows
    its expression rejects before enrichment, each with a ``COMPONENT_SKIPPED`` event of its
    own.
    """

    source_table: str
    carrier_col: str
    fill_defaults: Callable[[pl.DataFrame], pl.DataFrame]
    enrich: Callable[
        [pl.DataFrame, pl.LazyFrame | None, TimeSeriesInfo, CarrierMappings], pl.DataFrame
    ]
    translations: list[Translation]
    schema: dict[str, pl.DataType | type[pl.DataType]]
    sienna_component: SiennaComponent
    time_series_attr: str | None = None
    skip: SkipForSeries | None = None
    derived_series: DerivedSeries | None = None
    build_ts_association: (
        Callable[[pl.DataFrame, pl.DataFrame, TimeSeriesInfo], pl.DataFrame] | None
    ) = None
    extensions: ExtensionSpec | None = None
