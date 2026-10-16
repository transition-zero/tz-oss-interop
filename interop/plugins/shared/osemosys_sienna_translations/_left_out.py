"""The technologies that the operations system has no component for, each reported once.

A technology of kind `fuel_supply`, `export` or `conversion`, or of no kind, has no type in an
electricity-only operations system. Each other kind belongs to a component group, which
reports what it leaves out itself. A technology of no kind and with no flow in the year moves
no energy, so it is not reported.
"""

from __future__ import annotations

import polars as pl

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.osemosys_canonical.constants import (
    ELECTRICITY_CARRIER,
    FUEL,
    OSEMOSYS_FRAMEWORK,
    REGION,
    TECHNOLOGY,
    VALUE_COL,
    AnnotationColumn,
    FlowParameter,
    TechnologyKind,
)
from interop.plugins.shared.osemosys_sienna_constants import OSEMOSYS_TO_SIENNA_PIPELINE
from interop.plugins.shared.osemosys_sienna_translations._canonical import (
    read_annotations,
    read_parameter,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_columns import (
    TECHNOLOGY_NAME,
)
from interop.plugins.shared.osemosys_sienna_translations._names import express_report_name
from interop.plugins.shared.osemosys_sienna_translations._operations import OperationsYear
from interop.plugins.shared.translation_runner import (
    SkippedNames,
    SkipReport,
    SkipRule,
    filter_component,
)

IS_ALL_ELECTRICITY = "is_all_electricity"
HAS_FLOWS = "has_flows"

_KEYS = [REGION, TECHNOLOGY]
_FLOWS = (FlowParameter.INPUT_ACTIVITY_RATIO, FlowParameter.OUTPUT_ACTIVITY_RATIO)
_LEFT_OUT_KINDS = (TechnologyKind.FUEL_SUPPLY, TechnologyKind.EXPORT, TechnologyKind.CONVERSION)
_KIND = pl.col(AnnotationColumn.KIND)


def _build_skip(reason: str, note: str) -> SkipReport:
    return SkipReport(
        pipeline=OSEMOSYS_TO_SIENNA_PIPELINE,
        framework=OSEMOSYS_FRAMEWORK,
        component=TECHNOLOGY,
        name_col=TECHNOLOGY_NAME,
        reason=reason,
        counted_noun="technology(ies)",
        note=note,
        listed=SkippedNames(column=TECHNOLOGY_NAME, label="Technologies"),
        attribute_col=AnnotationColumn.KIND,
    )


FUEL_SUPPLY_SKIP = _build_skip(
    "supply a fuel that is not electricity",
    "the operations system holds electricity only, so a fuel_supply technology has no "
    "component; the fuel cost rule still reads its cost for each plant that burns its fuel",
)
EXPORT_SKIP = _build_skip(
    "take in a fuel and put out nothing",
    "the operations system has no component that takes energy out of the model, so an export "
    "of electricity is a demand that the system does not hold",
)
ELECTRICITY_CONVERSION_SKIP = _build_skip(
    "convert one electricity fuel into another at one location",
    "the electricity fuels of one location share one bus, so the conversion joins nothing; its "
    "loss is lost, and each demand stays at the value that the model states",
)
OTHER_CONVERSION_SKIP = _build_skip(
    "convert a fuel that is not electricity at one location",
    "the operations system holds electricity only, so electricity that the conversion takes "
    "in is a demand that the system does not hold",
)
NO_KIND_SKIP = _build_skip(
    "have no kind, for example because they move a fuel that is not electricity",
    "the technology fits no kind of the canonical stage, so the operations system has no "
    "component for it",
)

_SKIP_RULES = (
    SkipRule(_KIND.ne_missing(TechnologyKind.FUEL_SUPPLY), FUEL_SUPPLY_SKIP),
    SkipRule(_KIND.ne_missing(TechnologyKind.EXPORT), EXPORT_SKIP),
    SkipRule(
        ~(_KIND.eq_missing(TechnologyKind.CONVERSION) & pl.col(IS_ALL_ELECTRICITY)),
        ELECTRICITY_CONVERSION_SKIP,
    ),
    SkipRule(_KIND.ne_missing(TechnologyKind.CONVERSION), OTHER_CONVERSION_SKIP),
    SkipRule(_KIND.is_not_null() | ~pl.col(HAS_FLOWS), NO_KIND_SKIP),
)


def report_left_out_technologies(
    state: State, operations: OperationsYear, recorder: ScopedRecorder
) -> None:
    """Record one COMPONENT_SKIPPED for each technology, and warn once for each reason."""
    technologies = _read_left_out_technologies(state, operations)
    for rule in _SKIP_RULES:
        technologies, _ = filter_component(technologies, rule.keep, rule.report, recorder)


def _read_left_out_technologies(state: State, operations: OperationsYear) -> pl.DataFrame:
    technologies = (
        read_annotations(state, TECHNOLOGY)
        .filter(_KIND.is_null() | _KIND.is_in(_LEFT_OUT_KINDS))
        .with_columns(express_report_name(TECHNOLOGY).alias(TECHNOLOGY_NAME))
    )
    flows = _read_flow_carriers(state, operations)
    return technologies.join(flows, on=_KEYS, how="left").with_columns(
        pl.col(IS_ALL_ELECTRICITY).fill_null(False),  # noqa: FBT003
        pl.col(HAS_FLOWS).fill_null(False),  # noqa: FBT003
    )


def _read_flow_carriers(state: State, operations: OperationsYear) -> pl.DataFrame:
    """Whether each technology has a flow in the year, and whether each of its fuels is power."""
    carriers = read_annotations(state, FUEL).select(REGION, FUEL, AnnotationColumn.CARRIER)
    flows = pl.concat(
        [
            read_parameter(state, parameter, operations.year)
            .filter(pl.col(VALUE_COL) > 0)
            .select(*_KEYS, FUEL)
            for parameter in _FLOWS
        ]
    )
    is_electricity = pl.col(AnnotationColumn.CARRIER).eq_missing(ELECTRICITY_CARRIER)
    return (
        flows.join(carriers, on=[REGION, FUEL], how="left")
        .group_by(_KEYS)
        .agg(is_electricity.all().alias(IS_ALL_ELECTRICITY), pl.lit(True).alias(HAS_FLOWS))  # noqa: FBT003
    )
