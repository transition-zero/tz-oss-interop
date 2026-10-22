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
from interop.plugins.shared.pypsa_time_series import append_metadata
from interop.plugins.shared.sienna_pypsa_translations.reporters import LinkReporter
from interop.plugins.shared.warning_text import name_a_few

log = logging.getLogger(__name__)

_NO_LOSS = 1.0
_NO_COST = 0.0
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


class LinkSplitter:
    """Splits each two-way link that loses energy or costs money into two one-way links."""

    def __init__(self, reporter: LinkReporter) -> None:
        self._reporter = reporter

    def split_links(self, rows: list[dict[str, Any]]) -> list[LinkSplit]:
        """Add a reverse row for each such link, and set the forward row to one way."""
        two_way = [row for row in rows if _is_lossy_two_way(row)]
        self._report_unsplit([row for row in two_way if row[PyPSALinkCol.P_NOM_EXTENDABLE]])
        fixed = [row for row in two_way if not row[PyPSALinkCol.P_NOM_EXTENDABLE]]
        names = {row[PyPSALinkCol.NAME] for row in rows}
        taken = [row for row in fixed if _build_reverse_name(row) in names]
        self._report_taken(taken)
        return [self._split(row, rows) for row in fixed if _build_reverse_name(row) not in names]

    def _split(self, row: dict[str, Any], rows: list[dict[str, Any]]) -> LinkSplit:
        reverse = _build_reverse_row(row)
        rows.append(reverse)
        p_min_pu = row[PyPSALinkCol.P_MIN_PU]
        row[PyPSALinkCol.P_MIN_PU] = 0.0
        self._reporter.record_split(row, reverse, p_min_pu)
        return LinkSplit(row[PyPSALinkCol.NAME], reverse[PyPSALinkCol.NAME], -p_min_pu)

    def _report_taken(self, rows: list[dict[str, Any]]) -> None:
        names = [row[PyPSALinkCol.NAME] for row in rows]
        for row in rows:
            self._reporter.record_reverse_name_taken(
                row[PyPSALinkCol.NAME], _build_reverse_name(row)
            )
        if names:
            log.warning(_TAKEN_WARNING, len(names), name_a_few(names))

    def _report_unsplit(self, rows: list[dict[str, Any]]) -> None:
        names = [row[PyPSALinkCol.NAME] for row in rows]
        for name in names:
            self._reporter.record_unsplit(name)
        if names:
            log.warning(_UNSPLIT_WARNING, len(names), name_a_few(names))


def add_reverse_series(state: State, splits: list[LinkSplit]) -> None:
    """Give each reverse link the series of its forward link, scaled by its own limit."""
    metadata = state.destination_tables.get(PyPSADestinationTable.TIME_SERIES_METADATA)
    if metadata is None or not splits:
        return
    copies = [
        {
            **row,
            ReverseTimeSeriesMetadataCol.COMPONENT_NAME: split.reverse,
            ReverseTimeSeriesMetadataCol.SCALING_FACTOR: split.reverse_p_max_pu,
        }
        for split in splits
        for row in _list_link_series(metadata, split.forward)
    ]
    append_metadata(state, copies)


def _list_link_series(metadata: pl.DataFrame, name: str) -> list[dict[str, Any]]:
    rows = metadata.filter(
        (pl.col(ReverseTimeSeriesMetadataCol.COMPONENT_TABLE) == PyPSADestinationTable.LINKS)
        & (pl.col(ReverseTimeSeriesMetadataCol.COMPONENT_NAME) == name)
    )
    return list(rows.iter_rows(named=True))


def _is_lossy_two_way(row: dict[str, Any]) -> bool:
    marginal_cost = row[PyPSALinkCol.MARGINAL_COST]
    is_costly = marginal_cost is not None and marginal_cost != _NO_COST
    is_lossy = row[PyPSALinkCol.EFFICIENCY] < _NO_LOSS
    return row[PyPSALinkCol.P_MIN_PU] < 0 and (is_lossy or is_costly)


def _build_reverse_name(row: dict[str, Any]) -> str:
    return f"{row[PyPSALinkCol.NAME]}{REVERSE_LINK_SUFFIX}"


def _build_reverse_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        PyPSALinkCol.NAME: _build_reverse_name(row),
        PyPSALinkCol.BUS0: row[PyPSALinkCol.BUS1],
        PyPSALinkCol.BUS1: row[PyPSALinkCol.BUS0],
        PyPSALinkCol.P_MIN_PU: 0.0,
        PyPSALinkCol.P_MAX_PU: -row[PyPSALinkCol.P_MIN_PU],
    }
