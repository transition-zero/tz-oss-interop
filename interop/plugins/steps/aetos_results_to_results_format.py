"""Turn the staged AETOS results rows into the long-format results table.

Each annual row takes the timestamp of 1 January of its year. The step converts each value
from the unit of the model, which the `units:` part of the user mappings file states.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import ClassVar, NamedTuple

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.aetos_results_constants import (
    AETOS_RESULTS_CSV,
    AETOS_RESULTS_KEY,
    INDEX_FIELD_COUNT,
    AetosResultsCol,
    AetosVariable,
)
from interop.plugins.shared.constants import Framework
from interop.plugins.shared.osemosys_canonical.canonical_stage import build_table_key
from interop.plugins.shared.osemosys_canonical.constants import (
    CANONICAL_FRAMEWORK,
    ELECTRICITY_CARRIER,
    FUEL,
    OPERATING_MODE,
    POLLUTANT,
    REGION,
    TECHNOLOGY,
    VALUE_COL,
    YEAR,
    AnnotationColumn,
    FlowParameter,
    TableKind,
)
from interop.plugins.shared.osemosys_sienna_translations._names import (
    express_component_name,
    express_report_name,
)
from interop.plugins.shared.osemosys_sienna_translations._units import ModelUnits, parse_units
from interop.plugins.shared.results_constants import (
    RESULTS_SCHEMA,
    RESULTS_TABLE_KEY,
    VARIABLE_DTYPE,
    VARIABLE_UNIT,
    ResultsCol,
    ResultsVariable,
)
from interop.plugins.shared.warning_text import name_a_few
from interop.ports.outbound.reporting import (
    DestinationField,
    EventKind,
    SourceField,
    TranslationEvent,
)

log = logging.getLogger(__name__)

_RATIO = "ratio"
_REPORT_NAME = "report_name"
_INDEX_COUNT = "index_count"
_FIRST_MONTH = 1
_FIRST_DAY = 1

_WRONG_INDEX_NOTE = (
    "{count} row(s) hold {found} index field(s), not the {expected} that the variable has, "
    "so each is left out"
)
_WRONG_INDEX_WARNING = (
    "%d variable(s) of the results CSV have rows with the wrong number of index fields, "
    "so those rows are left out: %s"
)
_NO_ELECTRICITY_CAPACITY_NOTE = (
    "the technology puts out no fuel whose carrier is electricity, so its capacity need not be "
    "in the capacity unit of the model; its installed_capacity and new_capacity are left out"
)
_NO_ELECTRICITY_CAPACITY_WARNING = (
    "%d technology(ies) put out no electricity, so their installed and new capacity are left "
    "out: %s"
)
_NO_PRODUCTION_NOTE = (
    "no technology puts out a fuel whose carrier is electricity, so production has no rows; "
    "give each electricity fuel `carrier: electricity` in the user mappings file"
)

_CAPACITY_DERIVATION = "{variable} × the MW in one {unit} → {destination} at 1 January of the year"
_PRODUCTION_DERIVATION = (
    "Σ over modes of TotalAnnualTechnologyActivityByMode × output_activity_ratio on each fuel "
    "whose carrier is electricity, × the MWh in one {unit} → production at 1 January of the year"
)
_EMISSIONS_DERIVATION = "AnnualEmissions × the t in one {unit} → emissions at 1 January of the year"
_OBJECTIVE_DERIVATION = (
    "Σ ModelPeriodCostByRegion × the scale of the model currency → objective in {unit}"
)


class Derivation(NamedTuple):
    """`text` is a template that takes the source, the model unit and the destination."""

    source: AetosVariable
    destination: ResultsVariable
    text: str


class AnnualMapping(NamedTuple):
    """A variable of the CSV whose rows name one member in their first index field."""

    derivation: Derivation
    member: str


_INSTALLED_CAPACITY = AnnualMapping(
    Derivation(
        AetosVariable.TOTAL_CAPACITY_ANNUAL,
        ResultsVariable.INSTALLED_CAPACITY,
        _CAPACITY_DERIVATION,
    ),
    TECHNOLOGY,
)
_NEW_CAPACITY = AnnualMapping(
    Derivation(AetosVariable.NEW_CAPACITY, ResultsVariable.NEW_CAPACITY, _CAPACITY_DERIVATION),
    TECHNOLOGY,
)
_PRODUCTION = AnnualMapping(
    Derivation(
        AetosVariable.TOTAL_ANNUAL_TECHNOLOGY_ACTIVITY_BY_MODE,
        ResultsVariable.PRODUCTION,
        _PRODUCTION_DERIVATION,
    ),
    TECHNOLOGY,
)
_EMISSIONS = AnnualMapping(
    Derivation(AetosVariable.ANNUAL_EMISSIONS, ResultsVariable.EMISSIONS, _EMISSIONS_DERIVATION),
    POLLUTANT,
)
_OBJECTIVE = Derivation(
    AetosVariable.MODEL_PERIOD_COST_BY_REGION, ResultsVariable.OBJECTIVE, _OBJECTIVE_DERIVATION
)


_CAPACITY_MAPPINGS = (_INSTALLED_CAPACITY, _NEW_CAPACITY)


class Technologies(NamedTuple):
    """`electricity_ratios` holds the output ratio of each technology, mode and year onto all
    its electricity fuels."""

    categories: pl.DataFrame
    electricity_ratios: pl.DataFrame

    def build_electricity_producers(self) -> pl.DataFrame:
        return self.electricity_ratios.select(REGION, TECHNOLOGY).unique()


class AetosResultsToResultsFormat(TranslationStep):
    name: ClassVar[str] = "aetos_results_to_results_format"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def run(self, state: State, params: BaseModel | None) -> State:
        units = parse_units(state)
        technologies = _read_technologies(state)
        read = _read_variables(state)
        self._report_wrong_index_counts(read)
        variables = _reshape_variables(read)
        self._report_capacity_without_electricity(variables, technologies)
        pieces = [
            self._map_capacity(variables, _INSTALLED_CAPACITY, units, technologies),
            self._map_capacity(variables, _NEW_CAPACITY, units, technologies),
            self._map_production(variables, units, technologies),
            self._map_emissions(variables, units),
            self._map_objective(variables, units),
        ]
        state.destination_tables[RESULTS_TABLE_KEY] = _build_results_table(pieces)
        return state

    def _map_capacity(
        self,
        variables: dict[AetosVariable, pl.DataFrame],
        mapping: AnnualMapping,
        units: ModelUnits,
        technologies: Technologies,
    ) -> pl.DataFrame:
        rows = _drop_non_electricity_technologies(
            variables[mapping.derivation.source], technologies
        )
        if rows.is_empty():
            return _build_empty_results()
        self._record_derivation(mapping.derivation, units.capacity_unit)
        members = rows.join(technologies.categories, on=[REGION, TECHNOLOGY], how="left")
        return _build_annual_results(
            members, mapping, pl.col(AnnotationColumn.CATEGORY), units.convert_capacity_to_mw
        )

    def _map_production(
        self,
        variables: dict[AetosVariable, pl.DataFrame],
        units: ModelUnits,
        technologies: Technologies,
    ) -> pl.DataFrame:
        activity = variables[_PRODUCTION.derivation.source]
        if activity.is_empty():
            return _build_empty_results()
        production = _build_production(activity, technologies.electricity_ratios)
        if production.is_empty():
            self._report_no_production()
            return _build_empty_results()
        self._record_derivation(
            _PRODUCTION.derivation, units.energy_unit, _OUTPUT_ACTIVITY_RATIO_SOURCE
        )
        with_categories = production.join(
            technologies.categories, on=[REGION, TECHNOLOGY], how="left"
        )
        return _build_annual_results(
            with_categories,
            _PRODUCTION,
            pl.col(AnnotationColumn.CATEGORY),
            units.convert_energy_to_mwh,
        )

    def _map_emissions(
        self, variables: dict[AetosVariable, pl.DataFrame], units: ModelUnits
    ) -> pl.DataFrame:
        rows = variables[_EMISSIONS.derivation.source]
        if rows.is_empty():
            return _build_empty_results()
        self._record_derivation(_EMISSIONS.derivation, units.emissions_unit)
        pollutants = _enrich_with_first_index(rows, POLLUTANT)
        return _build_annual_results(
            pollutants, _EMISSIONS, pl.lit(None, dtype=pl.Utf8), units.convert_emissions_to_tonnes
        )

    def _map_objective(
        self, variables: dict[AetosVariable, pl.DataFrame], units: ModelUnits
    ) -> pl.DataFrame:
        rows = variables[_OBJECTIVE.source]
        if rows.is_empty():
            return _build_empty_results()
        self._record_derivation(_OBJECTIVE, units.currency_code)
        total = units.convert_currency_to_dollars(pl.col(AetosResultsCol.VALUE).sum())
        return rows.select(
            pl.lit(str(ResultsVariable.OBJECTIVE)).alias(ResultsCol.VARIABLE),
            pl.lit(None, dtype=pl.Utf8).alias(ResultsCol.COMPONENT),
            pl.lit(None, dtype=pl.Utf8).alias(ResultsCol.CATEGORY),
            pl.lit(None, dtype=RESULTS_SCHEMA[ResultsCol.TIMESTAMP]).alias(ResultsCol.TIMESTAMP),
            total.cast(pl.Float64).alias(ResultsCol.VALUE),
        )

    def _report_capacity_without_electricity(
        self, variables: dict[AetosVariable, pl.DataFrame], technologies: Technologies
    ) -> None:
        capacities = pl.concat(
            [variables[mapping.derivation.source] for mapping in _CAPACITY_MAPPINGS]
        )
        left_out = (
            _enrich_with_first_index(capacities, TECHNOLOGY)
            .join(technologies.build_electricity_producers(), on=[REGION, TECHNOLOGY], how="anti")
            .select(express_report_name(TECHNOLOGY).alias(_REPORT_NAME))
            .unique(maintain_order=True)[_REPORT_NAME]
            .to_list()
        )
        for name in left_out:
            self._recorder.append(
                TranslationEvent(
                    kind=EventKind.COMPONENT_SKIPPED,
                    sources=[
                        SourceField(framework=Framework.AETOS, component=TECHNOLOGY, name=name)
                    ],
                    note=_NO_ELECTRICITY_CAPACITY_NOTE,
                )
            )
        if left_out:
            log.warning(_NO_ELECTRICITY_CAPACITY_WARNING, len(left_out), name_a_few(left_out))

    def _report_wrong_index_counts(self, read: dict[AetosVariable, pl.DataFrame]) -> None:
        notes = {
            variable: note
            for variable, rows in read.items()
            if (note := _find_wrong_index_note(variable, rows)) is not None
        }
        for variable, note in notes.items():
            self._recorder.append(
                TranslationEvent(
                    kind=EventKind.COMPONENT_SKIPPED,
                    sources=[_build_csv_source(variable)],
                    note=note,
                )
            )
        if notes:
            log.warning(_WRONG_INDEX_WARNING, len(notes), name_a_few(notes))

    def _report_no_production(self) -> None:
        self._recorder.append(
            TranslationEvent(
                kind=EventKind.NOT_MAPPED,
                sources=[_build_csv_source(AetosVariable.TOTAL_ANNUAL_TECHNOLOGY_ACTIVITY_BY_MODE)],
                destinations=[_build_results_destination(ResultsVariable.PRODUCTION)],
                note=_NO_PRODUCTION_NOTE,
            )
        )
        log.warning("The results CSV gives activity, but %s", _NO_PRODUCTION_NOTE)

    def _record_derivation(
        self, derivation: Derivation, unit: str | None, *extra_sources: SourceField
    ) -> None:
        self._recorder.append(
            TranslationEvent(
                kind=EventKind.VALUE_DERIVED,
                sources=[_build_csv_source(derivation.source, unit), *extra_sources],
                destinations=[_build_results_destination(derivation.destination)],
                derivation=derivation.text.format(
                    variable=derivation.source, unit=unit, destination=derivation.destination
                ),
            )
        )


_OUTPUT_ACTIVITY_RATIO_SOURCE = SourceField(
    framework=CANONICAL_FRAMEWORK,
    component=TableKind.PARAMETER,
    name=FlowParameter.OUTPUT_ACTIVITY_RATIO,
)


def _build_csv_source(variable: AetosVariable, unit: str | None = None) -> SourceField:
    return SourceField(
        framework=Framework.AETOS, component=AETOS_RESULTS_CSV, name=variable, unit=unit
    )


def _build_results_destination(variable: ResultsVariable) -> DestinationField:
    return DestinationField(
        framework=Framework.RESULTS,
        component=RESULTS_TABLE_KEY,
        name=str(variable),
        attribute=ResultsCol.VARIABLE,
        unit=VARIABLE_UNIT[variable],
    )


def _find_wrong_index_note(variable: AetosVariable, rows: pl.DataFrame) -> str | None:
    expected = INDEX_FIELD_COUNT.get(variable)
    if expected is None:
        return None
    counts = (
        rows.select(pl.col(AetosResultsCol.INDEX).list.len().alias(_INDEX_COUNT))
        .filter(pl.col(_INDEX_COUNT) != expected)
        .group_by(_INDEX_COUNT)
        .len()
        .sort(_INDEX_COUNT)
    )
    notes = [
        _WRONG_INDEX_NOTE.format(count=count, found=found, expected=expected)
        for found, count in counts.rows()
    ]
    return "; ".join(notes) if notes else None


def _read_variables(state: State) -> dict[AetosVariable, pl.DataFrame]:
    stated = state.source_time_series[AETOS_RESULTS_KEY]
    return {
        variable: stated.filter(pl.col(AetosResultsCol.VARIABLE) == variable).collect()
        for variable in AetosVariable
    }


def _reshape_variables(
    read: dict[AetosVariable, pl.DataFrame],
) -> dict[AetosVariable, pl.DataFrame]:
    """One row for each year; the source has reported each value that is not a number."""
    return {
        variable: _reshape_by_year(_drop_wrong_index_counts(variable, rows)).drop_nulls(
            AetosResultsCol.VALUE
        )
        for variable, rows in read.items()
    }


def _drop_wrong_index_counts(variable: AetosVariable, rows: pl.DataFrame) -> pl.DataFrame:
    expected = INDEX_FIELD_COUNT.get(variable)
    if expected is None:
        return rows
    return rows.filter(pl.col(AetosResultsCol.INDEX).list.len() == expected)


def _reshape_by_year(rows: pl.DataFrame) -> pl.DataFrame:
    return rows.explode([AetosResultsCol.YEAR, AetosResultsCol.VALUE], empty_as_null=False)


def _enrich_with_first_index(rows: pl.DataFrame, member: str) -> pl.DataFrame:
    return rows.with_columns(pl.col(AetosResultsCol.INDEX).list.get(0).alias(member))


def _read_technologies(state: State) -> Technologies:
    return Technologies(
        categories=_read_technology_categories(state),
        electricity_ratios=_read_electricity_output_ratios(state),
    )


def _drop_non_electricity_technologies(
    rows: pl.DataFrame, technologies: Technologies
) -> pl.DataFrame:
    return _enrich_with_first_index(rows, TECHNOLOGY).join(
        technologies.build_electricity_producers(), on=[REGION, TECHNOLOGY], how="semi"
    )


def _read_technology_categories(state: State) -> pl.DataFrame:
    annotations = state.source_topology.get(build_table_key(TableKind.ANNOTATION, TECHNOLOGY))
    if annotations is None:
        return pl.DataFrame(
            schema=dict.fromkeys([REGION, TECHNOLOGY, AnnotationColumn.CATEGORY], pl.Utf8)
        )
    return annotations.select(REGION, TECHNOLOGY, AnnotationColumn.CATEGORY).collect()


def _read_electricity_output_ratios(state: State) -> pl.DataFrame:
    """The output ratio of each technology, mode and year onto all its electricity fuels."""
    ratios = state.source_time_series.get(
        (TableKind.PARAMETER, FlowParameter.OUTPUT_ACTIVITY_RATIO)
    )
    fuels = state.source_topology.get(build_table_key(TableKind.ANNOTATION, FUEL))
    if ratios is None or fuels is None:
        return _build_empty_ratios()
    electricity = fuels.filter(pl.col(AnnotationColumn.CARRIER) == ELECTRICITY_CARRIER).select(
        REGION, FUEL
    )
    return (
        ratios.join(electricity, on=[REGION, FUEL], how="semi")
        .group_by(REGION, TECHNOLOGY, OPERATING_MODE, pl.col(YEAR).cast(pl.Int64))
        .agg(pl.col(VALUE_COL).sum().alias(_RATIO))
        .collect()
    )


def _build_empty_ratios() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            REGION: pl.Utf8,
            TECHNOLOGY: pl.Utf8,
            OPERATING_MODE: pl.Utf8,
            YEAR: pl.Int64,
            _RATIO: pl.Float64,
        }
    )


def _build_production(activity: pl.DataFrame, ratios: pl.DataFrame) -> pl.DataFrame:
    by_mode = activity.with_columns(
        pl.col(AetosResultsCol.INDEX).list.get(0).alias(TECHNOLOGY),
        pl.col(AetosResultsCol.INDEX).list.get(1).alias(OPERATING_MODE),
    )
    return (
        by_mode.join(ratios, on=[REGION, TECHNOLOGY, OPERATING_MODE, YEAR], how="inner")
        .group_by(REGION, TECHNOLOGY, YEAR, maintain_order=True)
        .agg((pl.col(AetosResultsCol.VALUE) * pl.col(_RATIO)).sum().alias(AetosResultsCol.VALUE))
    )


def _build_annual_results(
    rows: pl.DataFrame,
    mapping: AnnualMapping,
    category: pl.Expr,
    convert: Callable[[pl.Expr], pl.Expr],
) -> pl.DataFrame:
    january_first = pl.datetime(pl.col(AetosResultsCol.YEAR), _FIRST_MONTH, _FIRST_DAY)
    return rows.select(
        pl.lit(str(mapping.derivation.destination)).alias(ResultsCol.VARIABLE),
        express_component_name(mapping.member).alias(ResultsCol.COMPONENT),
        category.alias(ResultsCol.CATEGORY),
        january_first.cast(RESULTS_SCHEMA[ResultsCol.TIMESTAMP]).alias(ResultsCol.TIMESTAMP),
        convert(pl.col(AetosResultsCol.VALUE)).cast(pl.Float64).alias(ResultsCol.VALUE),
    )


def _build_empty_results() -> pl.DataFrame:
    return pl.DataFrame(schema={**RESULTS_SCHEMA, ResultsCol.VARIABLE: pl.Utf8})


def _build_results_table(pieces: list[pl.DataFrame]) -> pl.DataFrame:
    return (
        pl.concat(pieces, how="vertical")
        .with_columns(pl.col(ResultsCol.VARIABLE).cast(VARIABLE_DTYPE))
        .select(list(RESULTS_SCHEMA))
    )
