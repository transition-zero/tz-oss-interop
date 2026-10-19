"""The technologies of electricity that the operations system has no component for.

An export of electricity alone has no type in the operations system, so each is reported once;
extensions.json holds it as a conversion record. A conversion of electricity alone becomes a
line, and the line group reports what it leaves out. A technology of a fuel that is not
electricity, of kind `fuel_supply`, `export`, `conversion` or of no kind, has a record of
extensions.json from the fuel group, which reports what it leaves out itself. So does each
other kind, from its own component group.
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
    TableKind,
    TechnologyKind,
)
from interop.plugins.shared.osemosys_sienna_constants import (
    OSEMOSYS_TO_SIENNA_PIPELINE,
    TECHNOLOGIES_LABEL,
    TECHNOLOGY_COUNTED_NOUN,
)
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
        counted_noun=TECHNOLOGY_COUNTED_NOUN,
        note=note,
        listed=SkippedNames(column=TECHNOLOGY_NAME, label=TECHNOLOGIES_LABEL),
        attribute_col=AnnotationColumn.KIND,
    )


ELECTRICITY_EXPORT_SKIP = _build_skip(
    "take in electricity and put out nothing",
    "the operations system has no component that takes energy out of the model, so an export "
    "of electricity is a demand that the system does not hold; extensions.json holds it as a "
    "conversion record",
)
_SKIP_RULE = SkipRule(
    ~(_KIND.eq_missing(TechnologyKind.EXPORT) & pl.col(IS_ALL_ELECTRICITY)),
    ELECTRICITY_EXPORT_SKIP,
)


def report_left_out_technologies(
    state: State, operations: OperationsYear, recorder: ScopedRecorder
) -> None:
    """Record one COMPONENT_SKIPPED for each export of electricity, and warn once."""
    technologies = read_left_out_technologies(state, operations)
    filter_component(technologies, _SKIP_RULE.keep, _SKIP_RULE.report, recorder)


def read_left_out_technologies(state: State, operations: OperationsYear) -> pl.DataFrame:
    """Each technology of a kind with no component, with `is_all_electricity` and `has_flows`."""
    technologies = (
        read_annotations(state, TECHNOLOGY)
        .filter(_KIND.is_null() | _KIND.is_in(_LEFT_OUT_KINDS))
        .with_columns(express_report_name(TECHNOLOGY).alias(TECHNOLOGY_NAME))
    )
    carriers = _read_fuel_carriers(state)
    flows = _read_year_flows(state, operations)
    return (
        technologies.join(carriers, on=_KEYS, how="left")
        .join(flows, on=_KEYS, how="left")
        .with_columns(
            pl.col(IS_ALL_ELECTRICITY).fill_null(False),  # noqa: FBT003
            pl.col(HAS_FLOWS).fill_null(False),  # noqa: FBT003
        )
    )


def _read_fuel_carriers(state: State) -> pl.DataFrame:
    """Whether each fuel that a technology takes in or puts out, in any year, is electricity.

    These are the flows that gave the technology its kind, so a year without flows does not
    change the answer.
    """
    carriers = read_annotations(state, FUEL).select(REGION, FUEL, AnnotationColumn.CARRIER)
    is_electricity = pl.col(AnnotationColumn.CARRIER).eq_missing(ELECTRICITY_CARRIER)
    return (
        _read_flow_fuels(state)
        .join(carriers, on=[REGION, FUEL], how="left")
        .group_by(_KEYS)
        .agg(is_electricity.all().alias(IS_ALL_ELECTRICITY))
    )


def _read_flow_fuels(state: State) -> pl.DataFrame:
    """A flow table can hold millions of rows, so collect only the distinct key columns."""
    tables = [
        table.filter(pl.col(VALUE_COL) > 0).select(*_KEYS, FUEL).unique().collect()
        for parameter in _FLOWS
        if (table := state.source_time_series.get((TableKind.PARAMETER, parameter))) is not None
    ]
    if not tables:
        return pl.DataFrame(schema=dict.fromkeys([*_KEYS, FUEL], pl.Utf8))
    return pl.concat(tables).unique()


def _read_year_flows(state: State, operations: OperationsYear) -> pl.DataFrame:
    """The technologies that take in or put out a fuel in the operations year."""
    flows = pl.concat(
        [
            read_parameter(state, parameter, operations.year)
            .filter(pl.col(VALUE_COL) > 0)
            .select(_KEYS)
            for parameter in _FLOWS
        ]
    )
    return flows.unique().with_columns(pl.lit(True).alias(HAS_FLOWS))  # noqa: FBT003
