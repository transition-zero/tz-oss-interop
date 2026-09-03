from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Protocol, runtime_checkable

import humanize

from interop.ports.inbound.overrides import NodeOverrides
from interop.ports.outbound.filesystem import Location

PROJECT_WRITES_LABEL = "wrote"
HANDOFF_WRITES_LABEL = "wrote hand-off files"

# Above this many, the list stops being readable and the count is the useful part.
_FILES_NAMED = 5


@dataclass(frozen=True)
class FileWrite:
    """A file a run wrote. A hand-off file passes one leg's output to the next leg, so it
    lands in the run's own scratch space rather than anywhere the user named.
    """

    location: Location
    size_bytes: int
    is_handoff: bool = False


@dataclass
class TranslateResult:
    writes: list[FileWrite] = field(default_factory=list)

    def summary(self, pipeline: str, duration_seconds: float) -> str:
        duration = humanize.precisedelta(
            timedelta(seconds=duration_seconds), minimum_unit="milliseconds"
        )
        return "; ".join([f"translated {pipeline} in {duration}", *self._describe_writes()])

    def _describe_writes(self) -> list[str]:
        groups = [
            (PROJECT_WRITES_LABEL, [write for write in self.writes if not write.is_handoff]),
            (HANDOFF_WRITES_LABEL, [write for write in self.writes if write.is_handoff]),
        ]
        return [f"{label} {_describe_files(writes)}" for label, writes in groups if writes]


def _describe_files(writes: list[FileWrite]) -> str:
    """Name the files written, or count them once an ensemble writes one per replication."""
    if len(writes) > _FILES_NAMED:
        total = humanize.naturalsize(sum(write.size_bytes for write in writes), binary=True)
        return f"{len(writes)} files ({total})"
    return ", ".join(
        f"{write.location} ({humanize.naturalsize(write.size_bytes, binary=True)})"
        for write in writes
    )


@runtime_checkable
class TranslateUseCase(Protocol):
    def __call__(
        self,
        source_framework: str,
        destination_framework: str,
        pipeline: str,
        *,
        overrides: NodeOverrides,
        keep_staging: bool = False,
        user_mappings_path: Location | None = None,
    ) -> TranslateResult: ...
