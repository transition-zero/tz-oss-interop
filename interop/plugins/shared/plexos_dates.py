"""When a dated PLEXOS value applies.

PLEXOS stamps a ``t_data`` row with the dates it applies between. The source narrows those
bands to the window being translated, and a mapping reading a schedule out of them -- the
year a unit arrives, the year it goes -- reads the same bands as the model states them, so
both sides share one reading of what a band covers.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import NamedTuple


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
