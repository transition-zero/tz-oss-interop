"""Turn the staged AETOS results rows into the long-format results table.

Each annual row takes the timestamp of 1 January of its year. The step converts each value
from the unit of the model, which the `units:` part of the user mappings file states.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace
from typing import Any, ClassVar, NamedTuple

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.annual_results import build_annual_rows, build_results_destination
from interop.plugins.shared.constants import Framework
from interop.plugins.shared.osemosys_canonical.constants import (
    CANONICAL_FRAMEWORK,
    OPERATING_MODE,
    POLLUTANT,
    REGION,
    STORAGE,
    TECHNOLOGY,
    AnnotationColumn,
    FlowParameter,
    TableKind,
    TechnologyKind,
)
from interop.plugins.shared.osemosys_sienna_translations._canonical import (
    find_parameter_default,
)
from interop.plugins.shared.osemosys_sienna_translations._names import express_report_name
from interop.plugins.shared.osemosys_sienna_translations._units import ModelUnits, parse_units
from interop.plugins.shared.results_constants import (
    RESULTS_SCHEMA,
    RESULTS_TABLE_KEY,
    VARIABLE_DTYPE,
    ResultsCol,
    ResultsVariable,
)
from interop.plugins.shared.sienna_results_constants import AnnualCol
from interop.plugins.shared.translation_runner import SkipReport, SkipRule, filter_component
from interop.plugins.shared.yearly_results_csv_constants import (
    RESULTS_CSV_COMPONENT,
    YEARLY_RESULTS_KEY,
    OsemosysResultVariable,
    YearlyResultsCol,
)
from interop.plugins.shared.yearly_results_csv_model import (
    COMPONENT,
    RATIO,
    STORAGE_COMPONENT,
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

# The pipeline name that each warning of the step starts with.
_PIPELINE = "aetos-to-results"
_REPORT_NAME = "report_name"
_DEFAULT_ATTRIBUTE = "default"
_IS_KNOWN = "is_known"
_IS_PRODUCER = "is_producer"
_IS_CONVERSION = "is_conversion"

_NO_PRODUCTION_NOTE = (
    "no technology puts out a fuel whose carrier is electricity, so production has no rows; "
    "give each electricity fuel `carrier: electricity` in the user mappings file"
)
_NO_PRODUCTION_WARNING = "The results CSV gives activity, but %s"
_UNREAD_DEFAULT_NOTE = (
    "a default other than zero would give every technology this ratio for every fuel and "
    "every mode, so the results read only the rows that the model states, as the Sienna "
    "translation does"
)
_UNREAD_DEFAULT_WARNING = (
    "%s: %s has the default %g, which the results do not apply. They read only the rows that "
    "the model states."
)

_CAPACITY_DERIVATION = "{variable} × the MW in one {unit} → {destination} at 1 January of the year"
_PRODUCTION_DERIVATION = (
    "Σ over modes of TotalAnnualTechnologyActivityByMode × output_activity_ratio on each fuel "
    "whose carrier is electricity that the model states, × the MWh in one {unit} → production "
    "at 1 January of the year"
)
_EMISSIONS_DERIVATION = (
    "Σ over regions of AnnualEmissions × the t in one {unit} → emissions of the pollutant at "
    "1 January of the year, because the Sienna system keys an emission rate by the pollutant alone"
)
_OBJECTIVE_DERIVATION = (
    "Σ ModelPeriodCostByRegion × the scale of {unit} → objective, in the same currency"
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
_CAPACITY_VARIABLES = (_INSTALLED_CAPACITY, _NEW_CAPACITY)
# The variables of a technology, which the Sienna system states for its own components only.
_TECHNOLOGY_VARIABLES = (*_CAPACITY_VARIABLES, _PRODUCTION)
_TECHNOLOGY_VARIABLE_NAMES = (
    f"{_INSTALLED_CAPACITY.destination}, {_NEW_CAPACITY.destination} and {_PRODUCTION.destination}"
)

_STORAGE_NAME_DERIVATION = (
    "the Sienna system names a storage after the OSeMOSYS storage and rates it with the "
    "technology that discharges it, so that technology states its {variables} under the "
    "Sienna name of the storage"
)
_TECHNOLOGY_NOUN = "technology(ies)"


def _build_technology_report(reason: str, note: str) -> SkipReport:
    return SkipReport(
        pipeline=_PIPELINE,
        framework=Framework.AETOS,
        component=TECHNOLOGY,
        name_col=_REPORT_NAME,
        reason=reason,
        counted_noun=_TECHNOLOGY_NOUN,
        note=f"{note}, so its {_TECHNOLOGY_VARIABLE_NAMES} rows are left out",
    )


# Each technology that states a row in a technology variable takes the first rule it fails.
_TECHNOLOGY_RULES = (
    SkipRule(
        keep=pl.col(_IS_KNOWN),
        report=_build_technology_report(
            "of the results CSV are not technologies of the model",
            "the region holds no technology of this name in the model",
        ),
    ),
    SkipRule(
        keep=~pl.col(_IS_CONVERSION),
        report=_build_technology_report(
            "convert electricity at one location",
            "the technology converts one electricity fuel into another at one location, and "
            "the Sienna system leaves such a technology out",
        ),
    ),
    SkipRule(
        keep=pl.col(_IS_PRODUCER),
        report=_build_technology_report(
            "put out no electricity",
            "the technology puts out no fuel whose carrier is electricity, and the results "
            "compare electricity only",
        ),
    ),
)
_UNKNOWN_POLLUTANT = SkipReport(
    pipeline=_PIPELINE,
    framework=Framework.AETOS,
    component=POLLUTANT,
    name_col=_REPORT_NAME,
    reason="of the results CSV are not pollutants of the model",
    counted_noun="pollutant(s)",
    note="the region holds no pollutant of this name in the model, so its emissions rows are "
    "left out",
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
        self._report_unread_ratio_default(state)
        inputs = MappingInputs(
            _reshape_variables(_read_stated_variables(state)),
            read_results_model(state),
            parse_units(state),
        )
        technologies = self._map_kept_technologies(inputs)
        self._record_storage_names(inputs.model, technologies)
        pieces = [
            *(
                self._map_capacity(inputs, technologies, derivation)
                for derivation in _CAPACITY_VARIABLES
            ),
            self._map_production(inputs, technologies),
            self._map_emissions(inputs),
            self._map_objective(inputs),
        ]
        state.destination_tables[RESULTS_TABLE_KEY] = _build_results_table(pieces)
        return state

    def _map_kept_technologies(self, inputs: MappingInputs) -> pl.DataFrame:
        """The technologies whose rows the results keep. It reports each other technology once,
        for the three technology variables."""
        technologies = _build_stated_technologies(inputs)
        for rule in _TECHNOLOGY_RULES:
            technologies, _ = filter_component(technologies, rule.keep, rule.report, self._recorder)
        return technologies.select(REGION, TECHNOLOGY)

    def _record_storage_names(self, model: ResultsModel, technologies: pl.DataFrame) -> None:
        """One event for each kept technology that takes the name of a storage."""
        renamed = model.storages.join(technologies, on=[REGION, TECHNOLOGY], how="semi")
        named = renamed.with_columns(express_report_name(TECHNOLOGY).alias(_REPORT_NAME))
        for row in named.sort(_REPORT_NAME).iter_rows(named=True):
            self._recorder.append(_build_storage_name_event(row))

    def _map_capacity(
        self, inputs: MappingInputs, technologies: pl.DataFrame, derivation: Derivation
    ) -> pl.LazyFrame:
        rows = _build_technology_rows(inputs, technologies, derivation)
        if rows.is_empty():
            return _build_empty_results()
        self._record_derivation(derivation, inputs.units.capacity_unit)
        named = _build_storage_named_rows(rows, inputs.model)
        return _build_converted_rows(named, derivation, inputs.units.convert_capacity_to_mw)

    def _map_production(self, inputs: MappingInputs, technologies: pl.DataFrame) -> pl.LazyFrame:
        if _has_activity_without_producers(inputs):
            self._report_no_production()
        activity = _build_technology_rows(inputs, technologies, _PRODUCTION)
        if activity.is_empty():
            return _build_empty_results()
        self._record_derivation(
            _PRODUCTION, inputs.units.energy_unit, _OUTPUT_ACTIVITY_RATIO_SOURCE
        )
        production = _build_storage_named_rows(
            _build_production(activity, inputs.model), inputs.model
        )
        return _build_converted_rows(production, _PRODUCTION, inputs.units.convert_energy_to_mwh)

    def _map_emissions(self, inputs: MappingInputs) -> pl.LazyFrame:
        rows = _enrich_with_member(inputs.variables[_EMISSIONS.source], POLLUTANT)
        pollutants, _ = filter_component(
            _build_stated_pollutants(rows, inputs.model),
            pl.col(_IS_KNOWN),
            _UNKNOWN_POLLUTANT,
            self._recorder,
        )
        rows = rows.join(pollutants, on=[REGION, POLLUTANT], how="semi")
        if rows.is_empty():
            return _build_empty_results()
        self._record_derivation(_EMISSIONS, inputs.units.emissions_unit)
        named = _build_emissions(rows, inputs.model)
        return _build_converted_rows(named, _EMISSIONS, inputs.units.convert_emissions_to_tonnes)

    def _map_objective(self, inputs: MappingInputs) -> pl.LazyFrame:
        rows = inputs.variables[_OBJECTIVE.source]
        if rows.is_empty():
            return _build_empty_results()
        self._record_derivation(_OBJECTIVE, inputs.units.currency_unit)
        total = inputs.units.convert_currency_to_dollars(pl.col(YearlyResultsCol.VALUE).sum())
        return rows.lazy().select(
            pl.lit(str(ResultsVariable.OBJECTIVE)).alias(ResultsCol.VARIABLE),
            pl.lit(None, dtype=pl.Utf8).alias(ResultsCol.COMPONENT),
            pl.lit(None, dtype=pl.Utf8).alias(ResultsCol.CATEGORY),
            pl.lit(None, dtype=RESULTS_SCHEMA[ResultsCol.TIMESTAMP]).alias(ResultsCol.TIMESTAMP),
            total.cast(pl.Float64).alias(ResultsCol.VALUE),
        )

    def _report_unread_ratio_default(self, state: State) -> None:
        default = find_parameter_default(state, FlowParameter.OUTPUT_ACTIVITY_RATIO)
        if not default:
            return
        self._recorder.append(
            TranslationEvent(
                kind=EventKind.NOT_MAPPED,
                sources=[
                    replace(
                        _OUTPUT_ACTIVITY_RATIO_SOURCE, attribute=_DEFAULT_ATTRIBUTE, value=default
                    )
                ],
                destinations=[build_results_destination(ResultsVariable.PRODUCTION)],
                note=_UNREAD_DEFAULT_NOTE,
            )
        )
        log.warning(
            _UNREAD_DEFAULT_WARNING, _PIPELINE, FlowParameter.OUTPUT_ACTIVITY_RATIO, default
        )

    def _report_no_production(self) -> None:
        self._recorder.append(
            TranslationEvent(
                kind=EventKind.NOT_MAPPED,
                sources=[_build_csv_source(_PRODUCTION.source)],
                destinations=[build_results_destination(ResultsVariable.PRODUCTION)],
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
                destinations=[build_results_destination(derivation.destination)],
                derivation=derivation.text.format(
                    variable=derivation.source, unit=unit, destination=derivation.destination
                ),
            )
        )


def _build_csv_source(variable: OsemosysResultVariable, unit: str | None = None) -> SourceField:
    return SourceField(
        framework=Framework.AETOS, component=RESULTS_CSV_COMPONENT, name=variable, unit=unit
    )


def _read_stated_variables(state: State) -> dict[OsemosysResultVariable, pl.DataFrame]:
    """The rows of each variable that the step reads. Each is an annual variable with no
    timeslice, so its rows are one for each component."""
    stated = state.source_time_series[YEARLY_RESULTS_KEY]
    columns = [
        YearlyResultsCol.REGION,
        YearlyResultsCol.INDEX,
        YearlyResultsCol.YEAR,
        YearlyResultsCol.VALUE,
    ]
    return {
        variable: stated.filter(pl.col(YearlyResultsCol.VARIABLE) == variable)
        .select(columns)
        .collect()
        for variable in OsemosysResultVariable
    }


def _reshape_variables(
    stated: dict[OsemosysResultVariable, pl.DataFrame],
) -> dict[OsemosysResultVariable, pl.DataFrame]:
    """One row for each year; the source has reported each value that is not a number."""
    return {
        variable: _reshape_by_year(rows).drop_nulls(YearlyResultsCol.VALUE)
        for variable, rows in stated.items()
    }


def _reshape_by_year(rows: pl.DataFrame) -> pl.DataFrame:
    return rows.explode([YearlyResultsCol.YEAR, YearlyResultsCol.VALUE], empty_as_null=False)


def _enrich_with_member(rows: pl.DataFrame, member: str) -> pl.DataFrame:
    return rows.with_columns(pl.col(YearlyResultsCol.INDEX).list.get(0).alias(member))


def _build_stated_technologies(inputs: MappingInputs) -> pl.DataFrame:
    """Each technology that states a row in a technology variable, with what the model says of
    it: is it a technology of the model, does it put out electricity, and is it a conversion."""
    keys = [REGION, TECHNOLOGY]
    stated = pl.concat(
        [
            _enrich_with_member(inputs.variables[derivation.source], TECHNOLOGY).select(keys)
            for derivation in _TECHNOLOGY_VARIABLES
        ]
    ).unique()
    is_conversion = pl.col(AnnotationColumn.KIND) == TechnologyKind.CONVERSION
    known = inputs.model.technologies.select(
        *keys, is_conversion.fill_null(False).alias(_IS_CONVERSION), pl.lit(True).alias(_IS_KNOWN)
    )
    producers = build_electricity_producers(inputs.model).with_columns(
        pl.lit(True).alias(_IS_PRODUCER)
    )
    return (
        stated.join(known, on=keys, how="left")
        .join(producers, on=keys, how="left")
        .with_columns(
            pl.col(_IS_KNOWN, _IS_PRODUCER).fill_null(False),
            (pl.col(_IS_CONVERSION) & pl.col(_IS_PRODUCER)).fill_null(False).alias(_IS_CONVERSION),
            express_report_name(TECHNOLOGY).alias(_REPORT_NAME),
        )
        .sort(_REPORT_NAME)
    )


def _build_stated_pollutants(rows: pl.DataFrame, model: ResultsModel) -> pl.DataFrame:
    """Each pollutant that states a row, and whether it is a pollutant of the model."""
    keys = [REGION, POLLUTANT]
    known = model.pollutants.select(*keys, pl.lit(True).alias(_IS_KNOWN))
    return (
        rows.select(keys)
        .unique()
        .join(known, on=keys, how="left")
        .with_columns(
            pl.col(_IS_KNOWN).fill_null(False),
            express_report_name(POLLUTANT).alias(_REPORT_NAME),
        )
        .sort(_REPORT_NAME)
        .select(*keys, _IS_KNOWN, _REPORT_NAME)
    )


def _build_technology_rows(
    inputs: MappingInputs, technologies: pl.DataFrame, derivation: Derivation
) -> pl.DataFrame:
    """The rows of the kept technologies in one variable, with their name and category."""
    rows = _enrich_with_member(inputs.variables[derivation.source], TECHNOLOGY)
    kept = rows.join(technologies, on=[REGION, TECHNOLOGY], how="semi")
    return kept.join(inputs.model.technologies, on=[REGION, TECHNOLOGY])


def _has_activity_without_producers(inputs: MappingInputs) -> bool:
    has_activity = not inputs.variables[_PRODUCTION.source].is_empty()
    return has_activity and build_electricity_producers(inputs.model).is_empty()


def _build_storage_named_rows(rows: pl.DataFrame, model: ResultsModel) -> pl.DataFrame:
    """Each technology that discharges a storage takes the name of the storage.

    Two technologies that discharge one storage give one row, which sums their values.
    """
    links = model.storages.select(REGION, TECHNOLOGY, STORAGE_COMPONENT)
    named = rows.join(links, on=[REGION, TECHNOLOGY], how="left").with_columns(
        pl.coalesce(STORAGE_COMPONENT, COMPONENT).alias(COMPONENT)
    )
    return named.group_by(COMPONENT, YearlyResultsCol.YEAR, maintain_order=True).agg(
        pl.col(AnnotationColumn.CATEGORY).first(), pl.col(YearlyResultsCol.VALUE).sum()
    )


def _build_storage_name_event(row: dict[str, Any]) -> TranslationEvent:
    return TranslationEvent(
        kind=EventKind.VALUE_DERIVED,
        sources=[
            SourceField(
                framework=Framework.AETOS,
                component=TECHNOLOGY,
                name=row[_REPORT_NAME],
                attribute=FlowParameter.TECHNOLOGY_FROM_STORAGE,
                value=row[STORAGE],
            )
        ],
        destinations=[
            DestinationField(
                framework=Framework.RESULTS,
                component=RESULTS_TABLE_KEY,
                name=row[STORAGE_COMPONENT],
                attribute=ResultsCol.COMPONENT,
            )
        ],
        derivation=_STORAGE_NAME_DERIVATION.format(variables=_TECHNOLOGY_VARIABLE_NAMES),
    )


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


def _build_emissions(rows: pl.DataFrame, model: ResultsModel) -> pl.DataFrame:
    """One row for each pollutant and year, the sum over the regions that state it."""
    return (
        rows.join(model.pollutants, on=[REGION, POLLUTANT])
        .group_by(COMPONENT, YearlyResultsCol.YEAR, maintain_order=True)
        .agg(pl.col(YearlyResultsCol.VALUE).sum())
        .with_columns(pl.lit(None, dtype=pl.Utf8).alias(AnnotationColumn.CATEGORY))
    )


def _build_converted_rows(
    rows: pl.DataFrame, derivation: Derivation, convert: Callable[[pl.Expr], pl.Expr]
) -> pl.LazyFrame:
    """The results rows of one annual variable, with each value in the results unit."""
    converted = rows.select(
        pl.col(COMPONENT).alias(ResultsCol.COMPONENT),
        pl.col(AnnotationColumn.CATEGORY).alias(ResultsCol.CATEGORY),
        pl.col(YearlyResultsCol.YEAR).alias(AnnualCol.YEAR),
        convert(pl.col(YearlyResultsCol.VALUE)).alias(ResultsCol.VALUE),
    )
    return build_annual_rows(converted, derivation.destination)


def _build_empty_results() -> pl.LazyFrame:
    return pl.LazyFrame(schema={**RESULTS_SCHEMA, ResultsCol.VARIABLE: pl.Utf8})


def _build_results_table(pieces: list[pl.LazyFrame]) -> pl.DataFrame:
    return (
        pl.concat(pieces, how="vertical")
        .with_columns(pl.col(ResultsCol.VARIABLE).cast(VARIABLE_DTYPE))
        .select(list(RESULTS_SCHEMA))
        .collect()
    )
