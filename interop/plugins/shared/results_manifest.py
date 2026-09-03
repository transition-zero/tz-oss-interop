"""The results run manifest: provenance that travels beside a results Parquet.

It records what produced the table and the zone its naive timestamps are in.
It deliberately carries no units or signs: those are fixed by the results
format itself, not asserted per run. The translator version is recorded because
comparison re-runs translation, so a table reflects the translator it was built
with rather than any earlier run's decisions.
"""

from __future__ import annotations

from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, field_validator


class ResultsFramework(StrEnum):
    """The source a results table was normalised from."""

    PYPSA = "pypsa"
    SIENNA = "sienna"
    CAISO_PLEXOS = "caiso-plexos"


class ResultsManifest(BaseModel):
    # A manifest is a fixed record of what produced a table, so instances are
    # immutable: provenance is not edited after the fact.
    model_config = ConfigDict(frozen=True)

    framework: ResultsFramework
    label: str
    timezone: str  # IANA zone name for the table's naive timestamps
    translator_version: str
    source_artifact: str  # the input file the table was normalised from

    @field_validator("timezone")
    @classmethod
    def _timezone_must_be_iana(cls, value: str) -> str:
        # The zone interprets the table's naive timestamps, so an invalid name
        # has to fail here rather than silently misread every timestamp later.
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"invalid IANA timezone: {value!r}") from exc
        return value
