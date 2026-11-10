"""The parts of a Sienna system that a PyPSA network cannot hold.

PyPSA has no load zone, no reserve, no reservoir apart from a StorageUnit, no service
membership and no supplemental attribute such as a forced outage. The hop leaves each one
out, records an event for each, and writes one warning for each type that names three.
"""

from __future__ import annotations

import logging
from itertools import groupby
from typing import Any

import polars as pl

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.pypsa_time_series import series_components
from interop.plugins.shared.sienna_constants import (
    SIENNA_NAME_COLUMN,
    SiennaComponent,
    SiennaGeneratorCol,
    SiennaHydroReservoirCol,
    SiennaStagedAssociationCol,
    SiennaTable,
)
from interop.plugins.shared.sienna_pypsa_translations.constants import SIENNA_TO_PYPSA
from interop.plugins.shared.sienna_pypsa_translations.reporters import UnheldReporter
from interop.plugins.shared.warning_text import name_a_few

log = logging.getLogger(__name__)

# The values of a HydroReservoir that a hydro StorageUnit would hold as its reservoir.
_RESERVOIR_VALUES: tuple[str, ...] = (
    SiennaHydroReservoirCol.STORAGE_LEVEL_LIMITS,
    SiennaHydroReservoirCol.INITIAL_LEVEL,
    SiennaHydroReservoirCol.INFLOW,
    SiennaHydroReservoirCol.OUTFLOW,
)
_COMPONENT_WARNING = (
    f"{SIENNA_TO_PYPSA}: %d %s(s) have no PyPSA counterpart, so each is left out: %s"
)
_RESERVOIR_WARNING = (
    f"{SIENNA_TO_PYPSA}: %d HydroReservoir(s) have no PyPSA counterpart, so each is left out "
    "with its levels and its inflow: %s"
)
_SERVICE_WARNING = (
    f"{SIENNA_TO_PYPSA}: %d component(s) contribute to a service of the type %s, which PyPSA "
    "does not have, so each contribution is left out: %s"
)
_ATTRIBUTE_WARNING = (
    f"{SIENNA_TO_PYPSA}: %d component(s) state an attribute of the type %s, which PyPSA "
    "does not have, so each is left out: %s"
)


def report_unheld(state: State, recorder: ScopedRecorder) -> None:
    """Record and warn about each part of the system that the network cannot hold."""
    reporter = UnheldReporter(recorder)
    _report_other_components(state, reporter)
    _report_reservoirs(state, reporter)
    _report_service_members(state, reporter)
    _report_attribute_owners(state, reporter)


def _report_other_components(state: State, reporter: UnheldReporter) -> None:
    rows = _list_rows(state, SiennaTable.OTHER_COMPONENTS, SiennaGeneratorCol.SIENNA_TYPE)
    for sienna_type, group in groupby(rows, key=lambda row: row[SiennaGeneratorCol.SIENNA_TYPE]):
        names = [row[SIENNA_NAME_COLUMN] for row in group]
        for name in names:
            reporter.record_component_skipped(sienna_type, name)
        log.warning(_COMPONENT_WARNING, len(names), sienna_type, name_a_few(sorted(names)))


def _report_reservoirs(state: State, reporter: UnheldReporter) -> None:
    rows = _list_rows(state, SiennaTable.RESERVOIRS, SiennaHydroReservoirCol.NAME)
    if not rows:
        return
    reservoir = SiennaComponent.HYDRO_RESERVOIR
    for row in rows:
        reporter.record_reservoir_skipped(reservoir, row[SiennaHydroReservoirCol.NAME])
        for attribute in _RESERVOIR_VALUES:
            if row.get(attribute) is not None:
                reporter.record_reservoir_value(
                    reservoir, row[SiennaHydroReservoirCol.NAME], attribute, row[attribute]
                )
    _report_reservoir_series(state, reporter)
    names = sorted(row[SiennaHydroReservoirCol.NAME] for row in rows)
    log.warning(_RESERVOIR_WARNING, len(names), name_a_few(names))


def _report_reservoir_series(state: State, reporter: UnheldReporter) -> None:
    for (owner_type, series), frame in sorted(state.source_time_series.items()):
        if owner_type == SiennaComponent.HYDRO_RESERVOIR:
            for name in sorted(series_components(frame)):
                reporter.record_reservoir_series(owner_type, name, series)


def _report_service_members(state: State, reporter: UnheldReporter) -> None:
    rows = _list_rows(state, SiennaTable.SERVICE_MEMBERS, SiennaStagedAssociationCol.SERVICE_TYPE)
    for service_type, group in groupby(
        rows, key=lambda row: row[SiennaStagedAssociationCol.SERVICE_TYPE]
    ):
        members = list(group)
        for row in members:
            reporter.record_service_member(
                row[SiennaStagedAssociationCol.COMPONENT_TYPE],
                row[SiennaStagedAssociationCol.COMPONENT_NAME],
                service_type,
                row[SiennaStagedAssociationCol.SERVICE_NAME],
            )
        names = sorted({row[SiennaStagedAssociationCol.COMPONENT_NAME] for row in members})
        log.warning(_SERVICE_WARNING, len(names), service_type, name_a_few(names))


def _report_attribute_owners(state: State, reporter: UnheldReporter) -> None:
    rows = _list_rows(
        state, SiennaTable.ATTRIBUTE_OWNERS, SiennaStagedAssociationCol.ATTRIBUTE_TYPE
    )
    for attribute_type, group in groupby(
        rows, key=lambda row: row[SiennaStagedAssociationCol.ATTRIBUTE_TYPE]
    ):
        owners = list(group)
        for row in owners:
            reporter.record_attribute(
                row[SiennaStagedAssociationCol.COMPONENT_TYPE],
                row[SiennaStagedAssociationCol.COMPONENT_NAME],
                attribute_type,
            )
        names = sorted({row[SiennaStagedAssociationCol.COMPONENT_NAME] for row in owners})
        log.warning(_ATTRIBUTE_WARNING, len(names), attribute_type, name_a_few(names))


def _list_rows(state: State, table_key: str, sort_column: str) -> list[dict[str, Any]]:
    """Every row of one staged table, sorted so that the rows of one type sit together."""
    table = state.source_topology.get(table_key)
    if table is None:
        return []
    return list(table.sort(pl.col(sort_column)).collect().iter_rows(named=True))
