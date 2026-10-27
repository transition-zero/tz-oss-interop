"""The event fields and events of the OSeMOSYS to Sienna translation."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import partial
from typing import Any

import polars as pl

from interop.plugins.shared.constants import Framework
from interop.plugins.shared.osemosys_canonical.constants import OSEMOSYS_FRAMEWORK
from interop.plugins.shared.osemosys_sienna_constants import OSEMOSYS_TO_SIENNA_PIPELINE
from interop.plugins.shared.translation_runner import (
    DestinationFieldFactory,
    SkipReport,
    Translation,
)
from interop.ports.outbound.reporting import (
    DestinationField,
    EventKind,
    SourceField,
    TranslationEvent,
)

# Every drop that the operations step reports is an OSeMOSYS value that the system leaves out.
osemosys_skip_report = partial(
    SkipReport, pipeline=OSEMOSYS_TO_SIENNA_PIPELINE, framework=OSEMOSYS_FRAMEWORK
)


def build_osemosys_field(
    component: str,
    name: str,
    attribute: str | None = None,
    value: Any = None,
    unit: str | None = None,
) -> SourceField:
    """One value of the canonical stage that an event reads."""
    return SourceField(
        framework=OSEMOSYS_FRAMEWORK,
        component=component,
        name=name,
        attribute=attribute,
        value=value,
        unit=unit,
    )


def build_sienna_field(
    sienna_type: str, name: str, attribute: str, value: Any = None, unit: str | None = None
) -> DestinationField:
    """One Sienna value that an event writes."""
    return DestinationField(
        framework=Framework.SIENNA,
        component=sienna_type,
        name=name,
        attribute=attribute,
        value=value,
        unit=unit,
    )


def build_sienna_source(
    sienna_type: str, name: str, attribute: str, value: Any = None, unit: str | None = None
) -> SourceField:
    """A Sienna value that an earlier translation wrote, read as the source of a later one."""
    return SourceField(
        framework=Framework.SIENNA,
        component=sienna_type,
        name=name,
        attribute=attribute,
        value=value,
        unit=unit,
    )


def build_derived(
    sources: Sequence[SourceField], destinations: Sequence[DestinationField], derivation: str
) -> list[TranslationEvent]:
    return [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=list(sources),
            destinations=list(destinations),
            derivation=derivation,
        )
    ]


def build_defaulted(destinations: Sequence[DestinationField], note: str) -> list[TranslationEvent]:
    return [
        TranslationEvent(
            kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
            destinations=list(destinations),
            note=note,
        )
    ]


@dataclass(frozen=True)
class ComputedValues:
    """The Sienna field of each computed value, and the column that names the component."""

    dest: DestinationFieldFactory
    name_col: str

    def build_translation(
        self,
        dest_col: str,
        expr: pl.Expr,
        sources: Callable[[dict[str, Any]], list[SourceField]],
        derivation: str,
        unit: str | None = None,
    ) -> Translation:
        """A value that the expression computes, and the event that names its sources."""
        return Translation(
            exprs=[expr.alias(dest_col)],
            make_events=lambda old, new: build_derived(
                sources(old),
                [self.dest(old[self.name_col], dest_col, new[dest_col], unit)],
                derivation,
            ),
        )
