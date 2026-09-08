"""When a PLEXOS object comes into service, and when it goes out of it.

A model writes an expansion plan as a schedule of dated ``Units``: an object running none
of itself until a later year arrives in that year, and one whose units fall back to zero
leaves in the year they do. The window being translated holds one value per property, so
these years are read from the dated bands the source stages beside it, unclipped.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import NamedTuple

import polars as pl

from interop.plugins.shared.plexos_constants import (
    PlexosClass,
    PlexosDatedPropertyCol,
    PlexosProperty,
)
from interop.plugins.shared.plexos_dates import (
    DateBand,
    band_edges,
    latest_covering,
    opens_at,
)
from interop.plugins.shared.plexos_pypsa_translations._expansion import NOTHING_TO_REPORT
from interop.plugins.shared.plexos_pypsa_translations.constants import (
    EXT_RETIREMENT_YEAR_FIELD,
)
from interop.plugins.shared.plexos_pypsa_translations.decisions import (
    ComponentReporter,
    Decision,
    MappedColumns,
    SourceValue,
    maps_to,
)
from interop.plugins.shared.pypsa_constants import PyPSAGeneratorCol

# What a schedule runs while no band it states covers the moment.
_NOT_IN_SERVICE = 0.0

RETIREMENT_YEAR_COLUMN = MappedColumns((EXT_RETIREMENT_YEAR_FIELD,))

_BUILD_DERIVATION = "the first year the dated Units rise above zero"
_RETIREMENT_DERIVATION = "the first year the dated Units fall back to zero"


class Milestone(NamedTuple):
    """A year a schedule changes what an object runs, and what it runs from then on."""

    year: int
    units: float


class Lifespan(NamedTuple):
    """When a dated ``Units`` schedule brings an object in, and when it takes it out.

    Either end can be absent: a schedule may only build, only retire, or say neither.
    """

    build: Milestone | None
    retirement: Milestone | None


NO_LIFESPAN = Lifespan(None, None)


@dataclass(frozen=True)
class LifespanDecisions:
    build_year: Decision = maps_to(PyPSAGeneratorCol.BUILD_YEAR)
    # The sidecar carries the retirement year, since PyPSA has no column for it.
    retirement_year: Decision = NOTHING_TO_REPORT


class _UnitsBand(NamedTuple):
    dates: DateBand
    units: float


class _Change(NamedTuple):
    """A moment a schedule changes what it runs, and what it ran until then."""

    at: datetime
    units: float
    was: float


def read_lifespans(dated: pl.LazyFrame, plexos_class: PlexosClass) -> dict[str, Lifespan]:
    return {name: _read_lifespan(bands) for name, bands in _read_bands(dated, plexos_class).items()}


def derive_lifespan(plexos_class: PlexosClass, name: str, lifespan: Lifespan) -> LifespanDecisions:
    return LifespanDecisions(
        build_year=_derive_year(plexos_class, name, lifespan.build, _BUILD_DERIVATION),
        retirement_year=_derive_year(
            plexos_class, name, lifespan.retirement, _RETIREMENT_DERIVATION
        ),
    )


def record_lifespan(name: str, decisions: LifespanDecisions, reporter: ComponentReporter) -> None:
    reporter.record(name, RETIREMENT_YEAR_COLUMN, decisions.retirement_year)


def _derive_year(
    plexos_class: PlexosClass, name: str, milestone: Milestone | None, derivation: str
) -> Decision:
    if milestone is None:
        return Decision.unreported(None)
    source = SourceValue(plexos_class, name, PlexosProperty.UNITS, milestone.units)
    return Decision.derived(milestone.year, [source], derivation)


def read_year(decision: Decision) -> int | None:
    return None if decision.value is None else int(decision.value)


def _read_bands(dated: pl.LazyFrame, plexos_class: PlexosClass) -> dict[str, list[_UnitsBand]]:
    """Each object's ``Units`` rows, earliest band first, for the objects that date any.

    One row per object per band, so the frame is component-scale and safe to collect.
    """
    if PlexosDatedPropertyCol.CHILD_CLASS not in dated.collect_schema().names():
        return {}
    frame = (
        dated.filter(
            (pl.col(PlexosDatedPropertyCol.CHILD_CLASS) == plexos_class)
            & (pl.col(PlexosDatedPropertyCol.PROPERTY) == PlexosProperty.UNITS)
            & pl.col(PlexosDatedPropertyCol.VALUE).is_not_null()
        )
        .select(
            PlexosDatedPropertyCol.CHILD_OBJECT,
            PlexosDatedPropertyCol.DATE_FROM,
            PlexosDatedPropertyCol.DATE_TO,
            PlexosDatedPropertyCol.VALUE,
        )
        .collect()
    )
    bands: dict[str, list[_UnitsBand]] = {}
    for name, date_from, date_to, units in frame.iter_rows():
        bands.setdefault(name, []).append(_UnitsBand(DateBand(date_from, date_to), units))
    return {name: sorted(rows, key=opens_at) for name, rows in bands.items()}


def _read_lifespan(bands: list[_UnitsBand]) -> Lifespan:
    changes = _changes(bands)
    build = next((one for one in changes if not _runs(one.was) and _runs(one.units)), None)
    retirement = next(
        (
            one
            for one in changes
            if _runs(one.was) and not _runs(one.units) and (build is None or one.at > build.at)
        ),
        None,
    )
    return Lifespan(_milestone(build), _milestone(retirement))


def _milestone(change: _Change | None) -> Milestone | None:
    return None if change is None else Milestone(change.at.year, change.units)


def _runs(units: float) -> bool:
    return units > _NOT_IN_SERVICE


def _changes(bands: list[_UnitsBand]) -> list[_Change]:
    """What the schedule runs from each of its edges, beside what it ran before that edge."""
    changes: list[_Change] = []
    running = _units_at(bands, datetime.min)
    for moment in band_edges(bands):
        units = _units_at(bands, moment)
        changes.append(_Change(moment, units, running))
        running = units
    return changes


def _units_at(bands: list[_UnitsBand], moment: datetime) -> float:
    """What the schedule runs at a moment; no band covering it means none of the object."""
    units = latest_covering(bands, moment)
    return _NOT_IN_SERVICE if units is None else units
