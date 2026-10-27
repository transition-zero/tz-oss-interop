"""What each technology type of the portfolio states once, beside the builder of its candidates.

The step maps the candidates of each type, writes their records of extensions.json, and lists
their existing fleet, through one loop over the kinds.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from typing import NamedTuple

import polars as pl

from interop.plugins.shared.osemosys_canonical.constants import REGION, TECHNOLOGY
from interop.plugins.shared.pypsa_sienna_investments_translations import PortfolioTable, Schema
from interop.plugins.shared.sienna_constants import SiennaComponent
from interop.plugins.shared.sienna_investments_constants import SiennaInvestmentsComponent
from interop.plugins.shared.translation_runner import Translation

# The translations of one type, from the year of its costs and the first id that it takes.
BuildKindTranslations = Callable[[int, int], list[Translation]]


class YearlyField(NamedTuple):
    """The yearly column that fills a record field, and the parameter that it comes from."""

    column: str
    parameter: str


@dataclass(frozen=True)
class CandidateKind:
    """One technology type of the portfolio.

    `fields` names the record fields of extensions.json, and `keys` the columns that name one
    candidate. `applied` names the parameters that the portfolio applies to each candidate
    beside them. A base system component of a type in `base_types`, with the name of a
    candidate, is a device of `device_class` in its fleet. `technology_cols` name the columns
    that hold a technology of a candidate.
    """

    component: SiennaInvestmentsComponent
    schema: Schema
    build: BuildKindTranslations
    fields: Mapping[str, YearlyField]
    keys: Sequence[str]
    device_class: str
    base_types: Sequence[SiennaComponent]
    applied: tuple[str, ...] = ()
    technology_cols: tuple[str, ...] = (TECHNOLOGY,)

    def build_table(self, cost_year: int) -> PortfolioTable:
        """The destination table of the type, with its costs quoted in `cost_year`."""
        return PortfolioTable(self.component, self.schema, partial(self.build, cost_year))


@dataclass(frozen=True)
class Candidates:
    """The candidates of one kind: one row for each, and one row for each one and year."""

    kind: CandidateKind
    table: pl.DataFrame
    yearly: pl.DataFrame

    def build_technology_keys(self) -> pl.DataFrame:
        """The region and the technology of each technology of the candidates."""
        keys = [
            self.table.select(REGION, pl.col(column).alias(TECHNOLOGY))
            for column in self.kind.technology_cols
        ]
        return pl.concat(keys).unique()
