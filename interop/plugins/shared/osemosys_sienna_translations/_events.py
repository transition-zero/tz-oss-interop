"""The event fields and events of the OSeMOSYS to Sienna translation.

The Sienna fields and events come from `sienna_events`, which every translator into Sienna
shares.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import Any

import polars as pl

from interop.plugins.shared.osemosys_canonical.constants import OSEMOSYS_FRAMEWORK
from interop.plugins.shared.osemosys_sienna_constants import OSEMOSYS_TO_SIENNA_PIPELINE

# The Sienna factories stay importable from here for the modules that import them from here.
from interop.plugins.shared.sienna_events import build_defaulted as build_defaulted
from interop.plugins.shared.sienna_events import build_derived as build_derived
from interop.plugins.shared.sienna_events import build_sienna_field as build_sienna_field
from interop.plugins.shared.sienna_events import build_sienna_source as build_sienna_source
from interop.plugins.shared.translation_runner import (
    DestinationFieldFactory,
    SkipReport,
    Translation,
)
from interop.ports.outbound.reporting import SourceField

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
