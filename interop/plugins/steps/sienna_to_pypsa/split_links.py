"""The flow back of a two-way link that loses energy or costs money, as a link of its own.

PyPSA applies one efficiency and one marginal cost to both directions of a link, and its nodal
balance is linear in the flow. A flow back on one link therefore takes `efficiency` × the power
at bus1 and gives the full power at bus0, and earns the marginal cost instead of paying it. Two
one-way links, the second from bus1 to bus0, each lose and pay as the source states.
"""

from __future__ import annotations

import logging
from typing import Any, NamedTuple

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.pypsa_constants import (
    REVERSE_LINK_SUFFIX,
    PyPSADestinationTable,
    PyPSALinkCol,
    ReverseTimeSeriesMetadataCol,
)
from interop.plugins.shared.pypsa_time_series import append_metadata, find_table_series
from interop.plugins.shared.sienna_pypsa_translations.reporters import LinkReporter
from interop.plugins.shared.warning_text import name_a_few

log = logging.getLogger(__name__)

_NO_LOSS = 1.0
_NO_COST = 0.0
# A one-way link moves no power from bus1 to bus0.
_ONE_WAY_P_MIN_PU = 0.0
_UNSPLIT_WARNING = (
    "%d extendable link(s) flow both ways and lose energy or cost money, so each stays one "
    "link whose flow back gains what its forward flow loses: %s"
)
_TAKEN_WARNING = (
    "%d link(s) flow both ways and lose energy or cost money, but another link holds the name "
    "of their flow back, so each stays one link whose flow back gains what its forward flow "
    "loses: %s"
)


class LinkSplit(NamedTuple):
    """A two-way link, the name of the link that carries its flow back, and that link's limit."""

    forward: str
    reverse: str
    reverse_p_max_pu: float


class SplitLinks(NamedTuple):
    """The link rows, with a reverse row for each link that splits, and each split."""

    rows: list[dict[str, Any]]
    splits: list[LinkSplit]


class LinkSplitter:
    """Splits each two-way link that loses energy or costs money into two one-way links."""

    def __init__(self, reporter: LinkReporter) -> None:
        self._reporter = reporter

    def map_two_way_links(self, rows: list[dict[str, Any]]) -> SplitLinks:
        """The rows with each such link one way, and a reverse row for each that splits."""
        two_way = [row for row in rows if _is_lossy_two_way(row)]
        self._report_unsplit([row for row in two_way if row[PyPSALinkCol.P_NOM_EXTENDABLE]])
        fixed = [row for row in two_way if not row[PyPSALinkCol.P_NOM_EXTENDABLE]]
        names = {row[PyPSALinkCol.NAME] for row in rows}
        self._report_taken([row for row in fixed if _build_reverse_name(row) in names])
        splitting = [row for row in fixed if _build_reverse_name(row) not in names]
        reverse_rows = [_build_reverse_row(row) for row in splitting]
        for row, reverse in zip(splitting, reverse_rows, strict=True):
            self._reporter.record_split(row, reverse, row[PyPSALinkCol.P_MIN_PU])
        split_names = {row[PyPSALinkCol.NAME] for row in splitting}
        forward_rows = [_build_one_way_row(row, split_names) for row in rows]
        return SplitLinks([*forward_rows, *reverse_rows], [_build_split(row) for row in splitting])

    def _report_taken(self, rows: list[dict[str, Any]]) -> None:
        names = [row[PyPSALinkCol.NAME] for row in rows]
        for row in rows:
            self._reporter.record_reverse_name_taken(row, _build_reverse_name(row))
        if names:
            log.warning(_TAKEN_WARNING, len(names), name_a_few(names))

    def _report_unsplit(self, rows: list[dict[str, Any]]) -> None:
        names = [row[PyPSALinkCol.NAME] for row in rows]
        for row in rows:
            self._reporter.record_unsplit(row)
        if names:
            log.warning(_UNSPLIT_WARNING, len(names), name_a_few(names))


def add_reverse_series(state: State, splits: list[LinkSplit]) -> None:
    """Give each reverse link the series of its forward link, scaled by its own limit."""
    link_series = find_table_series(state, PyPSADestinationTable.LINKS)
    if link_series is None or not splits:
        return
    copies = [
        {
            **row,
            ReverseTimeSeriesMetadataCol.COMPONENT_NAME: split.reverse,
            ReverseTimeSeriesMetadataCol.SCALING_FACTOR: split.reverse_p_max_pu,
        }
        for split in splits
        for row in _list_component_series(link_series, split.forward)
    ]
    append_metadata(state, copies)


def _list_component_series(series: pl.DataFrame, name: str) -> list[dict[str, Any]]:
    rows = series.filter(pl.col(ReverseTimeSeriesMetadataCol.COMPONENT_NAME) == name)
    return list(rows.iter_rows(named=True))


def _is_lossy_two_way(row: dict[str, Any]) -> bool:
    marginal_cost = row[PyPSALinkCol.MARGINAL_COST]
    is_costly = marginal_cost is not None and marginal_cost != _NO_COST
    is_lossy = row[PyPSALinkCol.EFFICIENCY] < _NO_LOSS
    return row[PyPSALinkCol.P_MIN_PU] < 0 and (is_lossy or is_costly)


def _build_split(row: dict[str, Any]) -> LinkSplit:
    return LinkSplit(row[PyPSALinkCol.NAME], _build_reverse_name(row), -row[PyPSALinkCol.P_MIN_PU])


def _build_one_way_row(row: dict[str, Any], split_names: set[str]) -> dict[str, Any]:
    """The forward row of a link that splits flows one way; every other row stays as it is."""
    if row[PyPSALinkCol.NAME] not in split_names:
        return row
    return {**row, PyPSALinkCol.P_MIN_PU: _ONE_WAY_P_MIN_PU}


def _build_reverse_name(row: dict[str, Any]) -> str:
    return f"{row[PyPSALinkCol.NAME]}{REVERSE_LINK_SUFFIX}"


def _build_reverse_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        PyPSALinkCol.NAME: _build_reverse_name(row),
        PyPSALinkCol.BUS0: row[PyPSALinkCol.BUS1],
        PyPSALinkCol.BUS1: row[PyPSALinkCol.BUS0],
        PyPSALinkCol.P_MIN_PU: _ONE_WAY_P_MIN_PU,
        PyPSALinkCol.P_MAX_PU: -row[PyPSALinkCol.P_MIN_PU],
    }
