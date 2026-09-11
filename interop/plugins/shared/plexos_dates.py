"""When a dated PLEXOS value applies."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta
from typing import NamedTuple, TypeVar


class DateBand(NamedTuple):
    """When a ``t_data`` value applies. An open end runs from, or until, forever."""

    date_from: datetime | None
    date_to: datetime | None

    @property
    def ends(self) -> datetime | None:
        """A ``date_to`` names a whole day, so the band runs to the end of it."""
        return None if self.date_to is None else self.date_to + timedelta(days=1)

    def covers(self, moment: datetime) -> bool:
        return (self.date_from is None or self.date_from <= moment) and (
            self.ends is None or moment < self.ends
        )


UNDATED = DateBand(None, None)

T = TypeVar("T")


def latest_covering(bands: Sequence[tuple[DateBand, T]], moment: datetime) -> T | None:
    covering = [value for band, value in bands if band.covers(moment)]
    return covering[-1] if covering else None


def band_edges(bands: Iterable[tuple[DateBand, object]]) -> list[datetime]:
    """Every moment a band opens or closes, earliest first."""
    moments = {edge for band, _ in bands for edge in (band.date_from, band.ends)}
    return sorted(moment for moment in moments if moment is not None)


def opens_at(band: tuple[DateBand, object]) -> datetime:
    """A sort key putting an undated band first, since it stands before any dated one begins."""
    return band[0].date_from or datetime.min
