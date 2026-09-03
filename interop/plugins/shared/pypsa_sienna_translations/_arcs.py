"""Translation objects and helpers for Sienna Arc derivation.

An Arc is the topological edge two branches reference by integer id. Arcs are derived from
the already-translated branch tables (lines, links): one Arc per distinct ordered endpoint
pair, with ``from``/``to`` resolved to the buses' integer ids. The endpoint name columns
(bus0/bus1) are kept as enrichment for event attribution and dropped by finalise().
"""

from __future__ import annotations

import polars as pl

from interop.plugins.shared.constants import Framework
from interop.plugins.shared.pypsa_constants import PyPSALineCol
from interop.plugins.shared.sienna_constants import (
    SIENNA_TYPE_ATTRIBUTE,
    SiennaACBusCol,
    SiennaArcCol,
    SiennaComponent,
)
from interop.plugins.shared.translation_runner import Translation
from interop.ports.outbound.reporting import (
    DestinationField,
    EventKind,
    SourceField,
    TranslationEvent,
)


def build_arcs_source_table(
    branch_endpoints: pl.DataFrame, sienna_buses: pl.DataFrame
) -> pl.DataFrame:
    """One row per distinct ordered (bus0, bus1) pair with endpoint bus ids resolved.

    ``branch_endpoints`` is any frame carrying ``bus0``/``bus1`` name columns (the line and
    link destination tables). Returns the endpoint name columns plus ``from``/``to`` (the
    buses' integer ids); empty when there are no branches.
    """
    bus_lookup = sienna_buses.select([pl.col(SiennaACBusCol.NAME), pl.col(SiennaACBusCol.ID)])
    pairs = branch_endpoints.select([PyPSALineCol.BUS0, PyPSALineCol.BUS1]).unique(
        maintain_order=True
    )
    pairs = pairs.join(
        bus_lookup.rename(
            {SiennaACBusCol.NAME: PyPSALineCol.BUS0, SiennaACBusCol.ID: SiennaArcCol.FROM}
        ),
        on=PyPSALineCol.BUS0,
        how="left",
    )
    return pairs.join(
        bus_lookup.rename(
            {SiennaACBusCol.NAME: PyPSALineCol.BUS1, SiennaACBusCol.ID: SiennaArcCol.TO}
        ),
        on=PyPSALineCol.BUS1,
        how="left",
    )


def _arc_name(row: dict[str, object]) -> str:
    return f"{row[PyPSALineCol.BUS0]}->{row[PyPSALineCol.BUS1]}"


def _bus_source(name: str, attribute: str | None = None, value: object = None) -> SourceField:
    return SourceField(
        framework=Framework.SIENNA,
        component=SiennaComponent.AC_BUS,
        name=name,
        attribute=attribute,
        value=value,
    )


def _arc_dest(
    row: dict[str, object], attribute: str | None = None, value: object = None
) -> DestinationField:
    return DestinationField(
        framework=Framework.SIENNA,
        component=SiennaComponent.ARC,
        name=_arc_name(row),
        attribute=attribute,
        value=value,
    )


ARC_ID = Translation(
    exprs=[pl.int_range(1, pl.len() + 1, dtype=pl.Int64).alias(SiennaArcCol.ID)],
    make_events=lambda old, new: [
        TranslationEvent(
            kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
            destinations=[_arc_dest(old, SiennaArcCol.ID, new[SiennaArcCol.ID])],
            note="assigned by 1-based row position in arcs DataFrame",
        )
    ],
)

ARC_FROM = Translation(
    exprs=[pl.col(SiennaArcCol.FROM)],
    make_events=lambda old, new: [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                _bus_source(old[PyPSALineCol.BUS0], SiennaACBusCol.ID, old[SiennaArcCol.FROM])
            ],
            destinations=[_arc_dest(old, SiennaArcCol.FROM, new[SiennaArcCol.FROM])],
            derivation="bus0 name -> ACBus id",
        )
    ],
)

ARC_TO = Translation(
    exprs=[pl.col(SiennaArcCol.TO)],
    make_events=lambda old, new: [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[_bus_source(old[PyPSALineCol.BUS1], SiennaACBusCol.ID, old[SiennaArcCol.TO])],
            destinations=[_arc_dest(old, SiennaArcCol.TO, new[SiennaArcCol.TO])],
            derivation="bus1 name -> ACBus id",
        )
    ],
)

ARC_SIENNA_TYPE = Translation(
    exprs=[],
    make_events=lambda old, _: [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            destinations=[_arc_dest(old, SIENNA_TYPE_ATTRIBUTE, SiennaComponent.ARC)],
            derivation="Arc",
        )
    ],
)

ARC_TRANSLATIONS: list[Translation] = [ARC_ID, ARC_FROM, ARC_TO, ARC_SIENNA_TYPE]
