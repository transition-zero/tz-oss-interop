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
from interop.plugins.shared.constants import Framework
from interop.plugins.shared.osemosys_canonical.constants import (
    CANONICAL_FRAMEWORK,
    OPERATING_MODE,
    POLLUTANT,
    REGION,
    TECHNOLOGY,
    AnnotationColumn,
    FlowParameter,
    TableKind,
    TechnologyKind,
)
from interop.plugins.shared.osemosys_sienna_translations._names import express_report_name
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
from interop.plugins.shared.yearly_results_csv_constants import (
    INDEX_FIELD_COUNT,
    RESULTS_CSV_COMPONENT,
    YEARLY_RESULTS_KEY,
    OsemosysResultVariable,
    YearlyResultsCol,
)
from interop.plugins.shared.yearly_results_csv_model import (
    COMPONENT,
    RATIO,
    ResultsModel,
    build_electricity_producers,
    build_electricity_ratios,
    read_results_model,
)
from interop.ports.outbound.reporting import (
    DestinationField,
    EventKind,
    SourceField,
    TranslationEvent,
)

log = logging.getLogger(__name__)

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
_NO_PRODUCTION_NOTE = (
    "no technology puts out a fuel whose carrier is electricity, so production has no rows; "
    "give each electricity fuel `carrier: electricity` in the user mappings file"
)
_NO_PRODUCTION_WARNING = "The results CSV gives activity, but %s"

_CAPACITY_DERIVATION = "{variable} × the MW in one {unit} → {destination} at 1 January of the year"
_PRODUCTION_DERIVATION = (
    "Σ over modes of TotalAnnualTechnologyActivityByMode × output_activity_ratio on each fuel "
    "whose carrier is electricity (a fuel with no row takes the default of "
    "output_activity_ratio), × the MWh in one {unit} → production at 1 January of the year"
)
_EMISSIONS_DERIVATION = "AnnualEmissions × the t in one {unit} → emissions at 1 January of the year"
_OBJECTIVE_DERIVATION = (
    "Σ ModelPeriodCostByRegion × the scale of the model currency → objective in {unit}"
)


class LeftOutReport(NamedTuple):
    """Why the rows of some members are left out. `note` and `warning` take `{variable}`;
    `warning` then takes the count and a few names."""

    member: str
    note: str
    warning: str


_UNKNOWN_TECHNOLOGY = LeftOutReport(
    TECHNOLOGY,
    "the region holds no technology of this name in the model, so its {variable} rows are left out",
    "%d technology(ies) of the results CSV are not technologies of the model, so their "
    "{variable} rows are left out: %s",
)
_UNKNOWN_POLLUTANT = LeftOutReport(
    POLLUTANT,
    "the region holds no pollutant of this name in the model, so its {variable} rows are left out",
    "%d pollutant(s) of the results CSV are not pollutants of the model, so their {variable} "
    "rows are left out: %s",
)
_NO_ELECTRICITY = LeftOutReport(
    TECHNOLOGY,
    "the technology puts out no fuel whose carrier is electricity, and the results compare "
    "electricity only, so its {variable} rows are left out",
    "%d technology(ies) put out no electricity, so their {variable} rows are left out: %s",
)
_CONVERSION = LeftOutReport(
    TECHNOLOGY,
    "the technology converts one electricity fuel into another at one location, and the "
    "Sienna system leaves such a technology out, so its {variable} rows are left out",
    "%d technology(ies) convert electricity at one location, so their {variable} rows are "
    "left out: %s",
)


class Derivation(NamedTuple):
    """`text` is a template that takes the source, the model unit and the destination."""

    source: OsemosysResultVariable
    destination: ResultsVariable
    text: str


_INSTALLED_CAPACITY = Derivation(
    OsemosysResultVariable.TOTAL_CAPACITY_ANNUAL,
    ResultsVariable.INSTALLED_CAPACITY,
    _CAPACITY_DERIVATION,
)
_NEW_CAPACITY = Derivation(
    OsemosysResultVariable.NEW_CAPACITY, ResultsVariable.NEW_CAPACITY, _CAPACITY_DERIVATION
)
_PRODUCTION = Derivation(
    OsemosysResultVariable.TOTAL_ANNUAL_TECHNOLOGY_ACTIVITY_BY_MODE,
    ResultsVariable.PRODUCTION,
    _PRODUCTION_DERIVATION,
)
_EMISSIONS = Derivation(
    OsemosysResultVariable.ANNUAL_EMISSIONS, ResultsVariable.EMISSIONS, _EMISSIONS_DERIVATION
)
_OBJECTIVE = Derivation(
    OsemosysResultVariable.MODEL_PERIOD_COST_BY_REGION,
    ResultsVariable.OBJECTIVE,
    _OBJECTIVE_DERIVATION,
)

_OUTPUT_ACTIVITY_RATIO_SOURCE = SourceField(
    framework=CANONICAL_FRAMEWORK,
    component=TableKind.PARAMETER,
    name=FlowParameter.OUTPUT_ACTIVITY_RATIO,
)


class MappingInputs(NamedTuple):
    variables: dict[OsemosysResultVariable, pl.DataFrame]
    model: ResultsModel
    units: ModelUnits


class AetosResultsToResultsFormat(TranslationStep):
    name: ClassVar[str] = "aetos_results_to_results_format"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def run(self, state: State, params: BaseModel | None) -> State:
        stated = _read_stated_variables(state)
        self._report_wrong_index_counts(stated)
        inputs = MappingInputs(
            _reshape_variables(stated), read_results_model(state), parse_units(state)
        )
        state.destination_tables[RESULTS_TABLE_KEY] = self._map_variables(inputs)
        return state

    def _map_variables(self, inputs: MappingInputs) -> pl.DataFrame:
        pieces = [
            self._map_capacity(inputs, _INSTALLED_CAPACITY),
            self._map_capacity(inputs, _NEW_CAPACITY),
            self._map_production(inputs),
            self._map_emissions(inputs),
            self._map_objective(inputs),
        ]
        return _build_results_table(pieces)

    def _map_capacity(self, inputs: MappingInputs, derivation: Derivation) -> pl.DataFrame:
        rows = self._build_known_technology_rows(inputs, derivation)
        rows = self._drop_left_out_members(
            rows, build_electricity_producers(inputs.model), _NO_ELECTRICITY, derivation
        )
        if rows.is_empty():
            return _build_empty_results()
        self._record_derivation(derivation, inputs.units.capacity_unit)
        return _build_annual_results(rows, derivation, inputs.units.convert_capacity_to_mw)

    def _map_production(self, inputs: MappingInputs) -> pl.DataFrame:
        activity = self._build_known_technology_rows(inputs, _PRODUCTION)
        if activity.is_empty():
            return _build_empty_results()
        if build_electricity_producers(inputs.model).is_empty():
            self._report_no_production()
            return _build_empty_results()
        activity = self._drop_sienna_absent_technologies(activity, inputs.model)
        self._record_derivation(
            _PRODUCTION, inputs.units.energy_unit, _OUTPUT_ACTIVITY_RATIO_SOURCE
        )
        production = _build_production(activity, inputs.model)
        return _build_annual_results(production, _PRODUCTION, inputs.units.convert_energy_to_mwh)

    def _drop_sienna_absent_technologies(
        self, activity: pl.DataFrame, model: ResultsModel
    ) -> pl.DataFrame:
        """The activity of the technologies that the Sienna system holds; it reports the rest."""
        producers = build_electricity_producers(model)
        activity = self._drop_left_out_members(activity, producers, _NO_ELECTRICITY, _PRODUCTION)
        return self._drop_left_out_members(
            activity, _list_non_conversion(model), _CONVERSION, _PRODUCTION
        )

    def _map_emissions(self, inputs: MappingInputs) -> pl.DataFrame:
        rows = _enrich_with_member(inputs.variables[_EMISSIONS.source], POLLUTANT)
        rows = self._drop_left_out_members(
            rows, inputs.model.pollutants, _UNKNOWN_POLLUTANT, _EMISSIONS
        )
        if rows.is_empty():
            return _build_empty_results()
        self._record_derivation(_EMISSIONS, inputs.units.emissions_unit)
        named = rows.join(inputs.model.pollutants, on=[REGION, POLLUTANT]).with_columns(
            pl.lit(None, dtype=pl.Utf8).alias(AnnotationColumn.CATEGORY)
        )
        return _build_annual_results(named, _EMISSIONS, inputs.units.convert_emissions_to_tonnes)

    def _map_objective(self, inputs: MappingInputs) -> pl.DataFrame:
        rows = inputs.variables[_OBJECTIVE.source]
        if rows.is_empty():
            return _build_empty_results()
        self._record_derivation(_OBJECTIVE, inputs.units.currency_code)
        total = inputs.units.convert_currency_to_dollars(pl.col(YearlyResultsCol.VALUE).sum())
        return rows.select(
            pl.lit(str(ResultsVariable.OBJECTIVE)).alias(ResultsCol.VARIABLE),
            pl.lit(None, dtype=pl.Utf8).alias(ResultsCol.COMPONENT),
            pl.lit(None, dtype=pl.Utf8).alias(ResultsCol.CATEGORY),
            pl.lit(None, dtype=RESULTS_SCHEMA[ResultsCol.TIMESTAMP]).alias(ResultsCol.TIMESTAMP),
            total.cast(pl.Float64).alias(ResultsCol.VALUE),
        )

    def _build_known_technology_rows(
        self, inputs: MappingInputs, derivation: Derivation
    ) -> pl.DataFrame:
        """The rows of the technologies that the model holds, with their name, category and
        kind."""
        rows = _enrich_with_member(inputs.variables[derivation.source], TECHNOLOGY)
        technologies = inputs.model.technologies
        rows = self._drop_left_out_members(rows, technologies, _UNKNOWN_TECHNOLOGY, derivation)
        return rows.join(technologies, on=[REGION, TECHNOLOGY])

    def _drop_left_out_members(
        self, rows: pl.DataFrame, kept: pl.DataFrame, report: LeftOutReport, derivation: Derivation
    ) -> pl.DataFrame:
        """The rows whose region and member `kept` holds; it reports each member it drops."""
        keys = [REGION, report.member]
        self._report_left_out(_list_left_out_names(rows, kept, keys), report, derivation)
        return rows.join(kept.select(keys), on=keys, how="semi")

    def _report_left_out(
        self, names: list[str], report: LeftOutReport, derivation: Derivation
    ) -> None:
        note = report.note.format(variable=derivation.destination)
        for name in names:
            self._recorder.append(
                TranslationEvent(
                    kind=EventKind.COMPONENT_SKIPPED,
                    sources=[
                        SourceField(framework=Framework.AETOS, component=report.member, name=name)
                    ],
                    note=note,
                )
            )
        if names:
            warning = report.warning.format(variable=derivation.destination)
            log.warning(warning, len(names), name_a_few(names))

    def _report_wrong_index_counts(
        self, stated: dict[OsemosysResultVariable, pl.DataFrame]
    ) -> None:
        notes = {
            variable: note
            for variable, rows in stated.items()
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
                sources=[_build_csv_source(_PRODUCTION.source)],
                destinations=[_build_results_destination(ResultsVariable.PRODUCTION)],
                note=_NO_PRODUCTION_NOTE,
            )
        )
        log.warning(_NO_PRODUCTION_WARNING, _NO_PRODUCTION_NOTE)

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


def _build_csv_source(variable: OsemosysResultVariable, unit: str | None = None) -> SourceField:
    return SourceField(
        framework=Framework.AETOS, component=RESULTS_CSV_COMPONENT, name=variable, unit=unit
    )


def _build_results_destination(variable: ResultsVariable) -> DestinationField:
    return DestinationField(
        framework=Framework.RESULTS,
        component=RESULTS_TABLE_KEY,
        name=str(variable),
        attribute=ResultsCol.VARIABLE,
        unit=VARIABLE_UNIT[variable],
    )


def _read_stated_variables(state: State) -> dict[OsemosysResultVariable, pl.DataFrame]:
    stated = state.source_time_series[YEARLY_RESULTS_KEY]
    return {
        variable: stated.filter(pl.col(YearlyResultsCol.VARIABLE) == variable).collect()
        for variable in OsemosysResultVariable
    }


def _find_wrong_index_note(variable: OsemosysResultVariable, rows: pl.DataFrame) -> str | None:
    expected = INDEX_FIELD_COUNT.get(variable)
    if expected is None:
        return None
    counts = (
        rows.select(pl.col(YearlyResultsCol.INDEX).list.len().alias(_INDEX_COUNT))
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


def _reshape_variables(
    stated: dict[OsemosysResultVariable, pl.DataFrame],
) -> dict[OsemosysResultVariable, pl.DataFrame]:
    """One row for each year; the source has reported each value that is not a number."""
    return {
        variable: _reshape_by_year(_drop_wrong_index_counts(variable, rows)).drop_nulls(
            YearlyResultsCol.VALUE
        )
        for variable, rows in stated.items()
    }


def _drop_wrong_index_counts(variable: OsemosysResultVariable, rows: pl.DataFrame) -> pl.DataFrame:
    expected = INDEX_FIELD_COUNT.get(variable)
    if expected is None:
        return rows
    return rows.filter(pl.col(YearlyResultsCol.INDEX).list.len() == expected)


def _reshape_by_year(rows: pl.DataFrame) -> pl.DataFrame:
    return rows.explode([YearlyResultsCol.YEAR, YearlyResultsCol.VALUE], empty_as_null=False)


def _enrich_with_member(rows: pl.DataFrame, member: str) -> pl.DataFrame:
    return rows.with_columns(pl.col(YearlyResultsCol.INDEX).list.get(0).alias(member))


def _list_left_out_names(rows: pl.DataFrame, kept: pl.DataFrame, keys: list[str]) -> list[str]:
    left_out = rows.join(kept.select(keys), on=keys, how="anti")
    names = left_out.select(express_report_name(keys[1]).alias(_REPORT_NAME))
    return [str(name) for name in names.unique(maintain_order=True)[_REPORT_NAME].to_list()]


def _list_non_conversion(model: ResultsModel) -> pl.DataFrame:
    is_conversion = pl.col(AnnotationColumn.KIND) == TechnologyKind.CONVERSION
    return model.technologies.filter(~is_conversion.fill_null(False)).select(REGION, TECHNOLOGY)


def _build_production(activity: pl.DataFrame, model: ResultsModel) -> pl.DataFrame:
    by_mode = activity.with_columns(
        pl.col(YearlyResultsCol.INDEX).list.get(1).alias(OPERATING_MODE)
    )
    output = (pl.col(YearlyResultsCol.VALUE) * pl.col(RATIO)).sum().alias(YearlyResultsCol.VALUE)
    return (
        build_electricity_ratios(by_mode, model.ratios)
        .group_by(
            REGION,
            TECHNOLOGY,
            COMPONENT,
            AnnotationColumn.CATEGORY,
            YearlyResultsCol.YEAR,
            maintain_order=True,
        )
        .agg(output)
    )


def _build_annual_results(
    rows: pl.DataFrame, derivation: Derivation, convert: Callable[[pl.Expr], pl.Expr]
) -> pl.DataFrame:
    january_first = pl.datetime(pl.col(YearlyResultsCol.YEAR), _FIRST_MONTH, _FIRST_DAY)
    return rows.select(
        pl.lit(str(derivation.destination)).alias(ResultsCol.VARIABLE),
        pl.col(COMPONENT).alias(ResultsCol.COMPONENT),
        pl.col(AnnotationColumn.CATEGORY).alias(ResultsCol.CATEGORY),
        january_first.cast(RESULTS_SCHEMA[ResultsCol.TIMESTAMP]).alias(ResultsCol.TIMESTAMP),
        convert(pl.col(YearlyResultsCol.VALUE)).cast(pl.Float64).alias(ResultsCol.VALUE),
    )


def _build_empty_results() -> pl.DataFrame:
    return pl.DataFrame(schema={**RESULTS_SCHEMA, ResultsCol.VARIABLE: pl.Utf8})


def _build_results_table(pieces: list[pl.DataFrame]) -> pl.DataFrame:
    return (
        pl.concat(pieces, how="vertical")
        .with_columns(pl.col(ResultsCol.VARIABLE).cast(VARIABLE_DTYPE))
        .select(list(RESULTS_SCHEMA))
    )
