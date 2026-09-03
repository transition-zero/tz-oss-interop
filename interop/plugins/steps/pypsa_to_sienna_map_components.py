from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, NamedTuple

import polars as pl
from pydantic import BaseModel

from interop.core.extensions import (
    BusExtension,
    ExtensionKind,
    ExtensionReader,
    append_extensions,
)
from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import Framework
from interop.plugins.shared.pypsa_constants import (
    PYPSA_COMPONENT_NAMING,
    PyPSABusCol,
    PyPSACarrier,
    PyPSAComponentCol,
    PyPSAComponentNaming,
    PyPSALoadCol,
    PyPSATable,
)
from interop.plugins.shared.pypsa_sienna_translations import (
    BUS_SKIP,
    BUS_TRANSLATIONS,
    GENERATOR_LOAD_SHEDDING_SKIP,
    HYDRO_DISPATCH_MAPPING,
    INTERRUPTIBLE_LOAD_TRANSLATIONS_PHASE_1,
    INTERRUPTIBLE_LOAD_TRANSLATIONS_PHASE_2,
    LINE_DYNAMIC_RATING_SKIP,
    LINE_TRANSLATIONS,
    LINK_SKIP,
    LINK_TRANSLATIONS,
    LOAD_SKIP,
    LOAD_TRANSLATIONS_PHASE_1,
    LOAD_TRANSLATIONS_PHASE_2,
    PHS_STORAGE_MAPPING,
    RENEWABLE_DISPATCH_MAPPING,
    RENEWABLE_NON_DISPATCH_MAPPING,
    THERMAL_MAPPING,
    ComponentMapping,
    ScopeSkips,
    TimeSeriesInfo,
    build_bus_extensions,
    build_line_extensions,
    build_link_extensions,
    build_load_extensions,
    build_load_ts_association,
    carrier_scope_skips,
    choose_ensemble_samples,
    collect_ts_info,
    enrich_line_voltage,
    enrich_load_ts_stats,
    enrich_load_voll,
    fill_bus_defaults,
    fill_line_defaults,
    fill_link_defaults,
    fill_load_defaults,
    line_rating_is_static,
    lines_rated_by_a_series,
    link_in_scope,
    link_time_varying_owners,
    load_in_scope,
    load_is_interruptible,
)
from interop.plugins.shared.pypsa_sienna_user_mappings import CarrierMappings
from interop.plugins.shared.sienna_constants import (
    BUSES_DESTINATION_SCHEMA,
    HVDC_DESTINATION_SCHEMA,
    INTERRUPTIBLE_LOADS_DESTINATION_SCHEMA,
    LINES_DESTINATION_SCHEMA,
    LOADS_DESTINATION_SCHEMA,
    TIME_SERIES_ASSOCIATION_SCHEMA,
    SiennaACBusCol,
    SiennaComponent,
)
from interop.plugins.shared.translation_runner import (
    SkipRule,
    Translation,
    apply_translations,
    filter_component,
    finalise,
)
from interop.ports.outbound.reporting import EventKind, SourceField, TranslationEvent

# What this hop takes off a bus's sidecar record: its name, and the price a shortfall costs
# there. Anything else the record states is reported as dropped.
_BUS_FIELDS_READ = {"name", "value_of_lost_load"}
_BUS_FIELD_DROPPED_NOTE = (
    "this translation reads only the price of a shortfall off a bus record, so the record's "
    "other fields are dropped"
)


class _PreparedSource(NamedTuple):
    """One mapping's rows, ready to translate, beside the source series they were read with."""

    table: pl.DataFrame
    series: pl.LazyFrame | None
    ts_info: TimeSeriesInfo


@dataclass(frozen=True)
class _CarrierGroup:
    """One PyPSA source table, and every Sienna type its rows can become.

    Three drops apply to the whole table before any mapping runs, which ``scope_skips``
    builds from how the table's own class is named. Each mapping is then left with a silent
    filter that only picks its own rows out of what remains. Carrier-space disjointness is
    guaranteed upstream by CarrierMappings, which rejects a duplicate pypsa_carrier entry
    on load.
    """

    source_table: str
    mappings: tuple[ComponentMapping, ...]

    @property
    def naming(self) -> PyPSAComponentNaming:
        return PYPSA_COMPONENT_NAMING[self.source_table]

    def translated_types(self) -> tuple[SiennaComponent, ...]:
        return tuple(mapping.sienna_component for mapping in self.mappings)

    def scope_skips(self) -> ScopeSkips:
        return carrier_scope_skips(self.naming)


def _load_shedding_drop(priced_buses: list[str]) -> SkipRule:
    """The shedding generators an earlier hop of this translator added at a priced bus.

    The price and the generator are written together, so the price is an exact marker of
    this translator's own row. A carrier is free text, so a generator a user named for the
    same carrier stays translatable. The price reaches this hop on the bus's sidecar record,
    and the load it prices reads the same record.
    """
    return SkipRule(
        keep=(pl.col(PyPSAComponentCol.CARRIER) != PyPSACarrier.LOAD_SHEDDING)
        | ~pl.col(PyPSAComponentCol.BUS).is_in(priced_buses),
        report=GENERATOR_LOAD_SHEDDING_SKIP,
    )


_GENERATOR_GROUP = _CarrierGroup(
    source_table=PyPSATable.GENERATORS,
    mappings=(THERMAL_MAPPING, RENEWABLE_DISPATCH_MAPPING, RENEWABLE_NON_DISPATCH_MAPPING),
)
_STORAGE_GROUP = _CarrierGroup(
    source_table=PyPSATable.STORAGE_UNITS,
    mappings=(HYDRO_DISPATCH_MAPPING, PHS_STORAGE_MAPPING),
)


@dataclass(frozen=True)
class _LoadKind:
    """One of the two Sienna types a PyPSA load becomes.

    A load whose bus states a price for cutting it becomes the interruptible type, which
    carries that price and is the only one a solve may cut. Everything else about the two is
    the same, so they differ here by their type, their schema and their translations alone.
    """

    sienna_component: SiennaComponent
    schema: dict[str, pl.DataType | type[pl.DataType]]
    phase_1: list[Translation]
    phase_2: list[Translation]


_PLAIN_LOAD = _LoadKind(
    sienna_component=SiennaComponent.POWER_LOAD,
    schema=LOADS_DESTINATION_SCHEMA,
    phase_1=LOAD_TRANSLATIONS_PHASE_1,
    phase_2=LOAD_TRANSLATIONS_PHASE_2,
)
_INTERRUPTIBLE_LOAD = _LoadKind(
    sienna_component=SiennaComponent.INTERRUPTIBLE_POWER_LOAD,
    schema=INTERRUPTIBLE_LOADS_DESTINATION_SCHEMA,
    phase_1=INTERRUPTIBLE_LOAD_TRANSLATIONS_PHASE_1,
    phase_2=INTERRUPTIBLE_LOAD_TRANSLATIONS_PHASE_2,
)


class PypsaToSiennaMapComponents(TranslationStep):
    name: ClassVar[str] = "pypsa_to_sienna_map_components"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(
        self,
        recorder: ScopedRecorder,
        carrier_mappings: CarrierMappings,
    ) -> None:
        self._recorder = recorder
        self._carrier_mappings = carrier_mappings

    @staticmethod
    def _append(state: State, key: str, frame: pl.DataFrame) -> None:
        """Append rows to an accumulating aux table (extensions / time-series associations)."""
        state.destination_tables[key] = pl.concat([state.destination_tables[key], frame])

    def run(self, state: State, params: BaseModel | None) -> State:
        state.destination_tables[SiennaComponent.TIME_SERIES_ASSOCIATION] = pl.DataFrame(
            schema=TIME_SERIES_ASSOCIATION_SCHEMA
        )
        reader = ExtensionReader(state.source_extensions, Framework.PYPSA)
        state = self._map_buses(state)
        # Read once: the loads it prices and the shedding generators it identifies both want
        # it, and reading it twice would report each bus record's unread fields twice.
        voll_by_bus = self._voll_by_bus(state, reader)
        state = self._map_loads(state, voll_by_bus)
        state = self._map_generators(state, voll_by_bus)
        state = self._map_storage_units(state)
        state = self._map_lines(state)
        state = self._map_links(state)
        _relay_reserves(state, reader)
        choose_ensemble_samples(state, self._recorder)
        # A record no mapping here read is dropped and reported, rather than relayed into a
        # sidecar this hop's reader cannot say anything about.
        reader.report_unconsumed(self._recorder)
        return state

    def _map_generators(self, state: State, voll_by_bus: dict[str, float]) -> State:
        """The generators, less the shedding ones an earlier hop of this translator added."""
        return self._map_group(state, _GENERATOR_GROUP, (_load_shedding_drop(list(voll_by_bus)),))

    def _map_storage_units(self, state: State) -> State:
        return self._map_group(state, _STORAGE_GROUP)

    def _map_group(
        self, state: State, group: _CarrierGroup, own_rows: tuple[SkipRule, ...] = ()
    ) -> State:
        """Run every mapping one source table becomes, over the rows this leg can translate."""
        source = self._rows_in_scope(state, group, own_rows)
        if source is None:
            return state
        for mapping in group.mappings:
            state = self._map_one(state, mapping, source)
        return state

    def _rows_in_scope(
        self, state: State, group: _CarrierGroup, own_rows: tuple[SkipRule, ...]
    ) -> pl.DataFrame | None:
        """The rows of one source table this leg can translate, or None if it holds no table."""
        src = state.source_topology.get(group.source_table)
        if src is None:
            return None
        table = src.collect()
        for rule in self._scope_rules(state, group, own_rows):
            table, _ = filter_component(table, rule.keep, rule.report, self._recorder)
        return table

    def _scope_rules(
        self, state: State, group: _CarrierGroup, own_rows: tuple[SkipRule, ...]
    ) -> list[SkipRule]:
        """The drops a whole source table shares, in the order they apply.

        A carrier the user mappings file never names, a carrier it sends to a Sienna type
        this table does not become, and a bus that is not a translated AC bus are three
        different drops, so each gets its own report. ``own_rows`` holds the drops for rows
        an earlier hop of this translator wrote into the source model itself, which only the
        generators have. Order matters: a row the mappings file never names must not also
        report an unusable bus, and a row this translator wrote itself must report that
        rather than an unnamed carrier, because no mappings file entry would make it
        translatable.
        """
        carrier = pl.col(PyPSAComponentCol.CARRIER)
        skips = group.scope_skips()
        return [
            *own_rows,
            SkipRule(
                keep=carrier.is_in(list(self._carrier_mappings.get_carriers())),
                report=skips.unnamed_carrier,
            ),
            SkipRule(
                keep=carrier.is_in(list(self._translated_carriers(group))),
                report=skips.unsupported,
            ),
            SkipRule(
                keep=pl.col(PyPSAComponentCol.BUS).is_in(self._ac_bus_names(state)),
                report=skips.bus_scope,
            ),
        ]

    def _translated_carriers(self, group: _CarrierGroup) -> set[str]:
        carriers: set[str] = set()
        for component in group.translated_types():
            carriers |= self._carrier_mappings.get_carriers(component)
        return carriers

    def _map_one(self, state: State, mapping: ComponentMapping, source: pl.DataFrame) -> State:
        """Translate one carrier-filtered ComponentMapping into its Sienna destination table."""
        prepared = self._prepare_source(state, mapping, source)
        table = prepared.table
        self._add_derived_series(state, mapping, prepared)
        dst = apply_translations(table, mapping.translations, self._recorder)
        out = finalise(dst, mapping.schema, self._recorder, mapping.sienna_component)
        state.destination_tables[mapping.sienna_component] = out
        self._append_aux_tables(state, mapping, table, out, prepared.ts_info)
        return state

    def _prepare_source(
        self, state: State, mapping: ComponentMapping, source: pl.DataFrame
    ) -> _PreparedSource:
        """Fill defaults, take this mapping's carriers out of the group, skip and enrich."""
        carriers = self._carrier_mappings.get_carriers(mapping.sienna_component)
        table = mapping.fill_defaults(source)
        table = table.filter(pl.col(mapping.carrier_col).is_in(list(carriers)))
        series = self._source_time_series(state, mapping)
        if mapping.skip is not None:
            rule = mapping.skip(series)
            table, _ = filter_component(table, rule.keep, rule.report, self._recorder)
        ts_info = collect_ts_info(series)
        return _PreparedSource(
            table=mapping.enrich(table, series, ts_info, self._carrier_mappings),
            series=series,
            ts_info=ts_info,
        )

    def _add_derived_series(
        self, state: State, mapping: ComponentMapping, prepared: _PreparedSource
    ) -> None:
        """Put a series this mapping computes back among the source series, for the sink."""
        derived = mapping.derived_series
        if derived is None or prepared.series is None or prepared.table.is_empty():
            return
        state.source_time_series[(mapping.source_table, derived.attribute)] = derived.build(
            prepared.table, prepared.series
        )

    @staticmethod
    def _ac_bus_names(state: State) -> list[str]:
        buses = state.destination_tables.get(SiennaComponent.AC_BUS)
        return buses[SiennaACBusCol.NAME].to_list() if buses is not None else []

    def _source_time_series(self, state: State, mapping: ComponentMapping) -> pl.LazyFrame | None:
        """The component's source time series for its declared attribute, or None if it has none."""
        if mapping.time_series_attr is None:
            return None
        return state.source_time_series.get((mapping.source_table, mapping.time_series_attr))

    def _append_aux_tables(
        self,
        state: State,
        mapping: ComponentMapping,
        table: pl.DataFrame,
        out: pl.DataFrame,
        ts_info: TimeSeriesInfo,
    ) -> None:
        """Append the component's time-series associations and extension records, when present."""
        if mapping.build_ts_association is not None:
            self._append(
                state,
                SiennaComponent.TIME_SERIES_ASSOCIATION,
                mapping.build_ts_association(table, out, ts_info),
            )
        if mapping.extensions is not None:
            append_extensions(
                state.destination_extensions,
                mapping.extensions.kind,
                mapping.extensions.build(table, out),
            )

    def _map_buses(self, state: State) -> State:
        src = state.source_topology.get(PyPSATable.BUSES)
        if src is None:
            return state

        table = src.collect()
        table = fill_bus_defaults(table)
        table, _ = filter_component(
            table,
            pl.col(PyPSABusCol.CARRIER) == PyPSACarrier.AC,
            BUS_SKIP,
            self._recorder,
        )
        dst = apply_translations(table, BUS_TRANSLATIONS, self._recorder)
        state.destination_tables[SiennaComponent.AC_BUS] = finalise(
            dst,
            BUSES_DESTINATION_SCHEMA,
            self._recorder,
            SiennaComponent.AC_BUS,
        )
        append_extensions(
            state.destination_extensions,
            ExtensionKind.BUS,
            build_bus_extensions(table, state.destination_tables[SiennaComponent.AC_BUS]),
        )
        return state

    def _map_loads(self, state: State, voll_by_bus: dict[str, float]) -> State:
        """Translate the loads, as two Sienna types split on whether a solve may cut them."""
        src = state.source_topology.get(PyPSATable.LOADS)
        if src is None:
            return state
        table = fill_load_defaults(src.collect())
        table, _ = filter_component(
            table, load_in_scope(self._ac_bus_names(state)), LOAD_SKIP, self._recorder
        )
        ts_p = state.source_time_series.get((PyPSATable.LOADS, PyPSALoadCol.P_SET))
        table = enrich_load_ts_stats(table, ts_p)
        table = enrich_load_voll(table, voll_by_bus)
        ts_info = collect_ts_info(ts_p)
        self._map_load_type(state, table.filter(~load_is_interruptible()), ts_info, _PLAIN_LOAD)
        self._map_load_type(
            state, table.filter(load_is_interruptible()), ts_info, _INTERRUPTIBLE_LOAD
        )
        return state

    def _map_load_type(
        self, state: State, table: pl.DataFrame, ts_info: TimeSeriesInfo, kind: _LoadKind
    ) -> None:
        """Translate one of the two load types, leaving no destination table where none apply."""
        if table.is_empty():
            return
        dst = apply_translations(table, kind.phase_1, self._recorder)
        dst = apply_translations(dst, kind.phase_2, self._recorder)
        out = finalise(dst, kind.schema, self._recorder, kind.sienna_component)
        state.destination_tables[kind.sienna_component] = out
        self._append(
            state,
            SiennaComponent.TIME_SERIES_ASSOCIATION,
            build_load_ts_association(table, out, ts_info, kind.sienna_component),
        )
        append_extensions(
            state.destination_extensions, ExtensionKind.LOAD, build_load_extensions(table, out)
        )

    def _voll_by_bus(self, state: State, reader: ExtensionReader) -> dict[str, float]:
        """The price a shortfall costs at each bus, for the buses whose record states one.

        Asking a bus's record for the price is what marks the whole record read, so the
        fields this hop has no home for are reported here. Left to the reader, they would
        travel no further and be reported nowhere, because a record nobody asked for is the
        only thing it can report.
        """
        priced: dict[str, float] = {}
        lookup = reader.read(ExtensionKind.BUS)
        for name in self._ac_bus_names(state):
            record = lookup.get(name)
            self._report_unread_bus_fields(record)
            if record.value_of_lost_load is not None:
                priced[name] = record.value_of_lost_load
        return priced

    def _report_unread_bus_fields(self, record: BusExtension) -> None:
        """Report every field a bus record states that no mapping in this hop reads."""
        unread = record.model_dump(exclude_none=True, exclude=_BUS_FIELDS_READ)
        for attribute, value in unread.items():
            self._recorder.append(
                TranslationEvent(
                    kind=EventKind.NOT_MAPPED,
                    sources=[
                        SourceField(
                            framework=Framework.PYPSA,
                            component=ExtensionKind.BUS,
                            name=record.name,
                            attribute=attribute,
                            value=value,
                        )
                    ],
                    note=_BUS_FIELD_DROPPED_NOTE,
                )
            )

    def _map_lines(self, state: State) -> State:
        src = state.source_topology.get(PyPSATable.LINES)
        if src is None:
            return state
        buses = state.destination_tables.get(SiennaComponent.AC_BUS)
        if buses is None:
            return state

        table = fill_line_defaults(src.collect())
        table, _ = filter_component(
            table,
            line_rating_is_static(lines_rated_by_a_series(state.source_time_series)),
            LINE_DYNAMIC_RATING_SKIP,
            self._recorder,
        )
        table = enrich_line_voltage(table, buses)

        dst = apply_translations(table, LINE_TRANSLATIONS, self._recorder)
        state.destination_tables[SiennaComponent.LINE] = finalise(
            dst,
            LINES_DESTINATION_SCHEMA,
            self._recorder,
            SiennaComponent.LINE,
        )
        append_extensions(
            state.destination_extensions,
            ExtensionKind.LINE,
            build_line_extensions(table, state.destination_tables[SiennaComponent.LINE]),
        )
        return state

    def _map_links(self, state: State) -> State:
        src = state.source_topology.get(PyPSATable.LINKS)
        if src is None:
            return state
        buses = state.destination_tables.get(SiennaComponent.AC_BUS)
        if buses is None:
            return state

        table = fill_link_defaults(src.collect())
        table, _ = filter_component(
            table,
            link_in_scope(buses[SiennaACBusCol.NAME].to_list()),
            LINK_SKIP,
            self._recorder,
        )

        dst = apply_translations(table, LINK_TRANSLATIONS, self._recorder)
        hvdc = SiennaComponent.TWO_TERMINAL_GENERIC_HVDC_LINE
        state.destination_tables[hvdc] = finalise(
            dst,
            HVDC_DESTINATION_SCHEMA,
            self._recorder,
            hvdc,
        )
        append_extensions(
            state.destination_extensions,
            ExtensionKind.CONTROLLABLE_LINE,
            build_link_extensions(
                table,
                state.destination_tables[hvdc],
                link_time_varying_owners(state.source_time_series),
            ),
        )
        return state


def _relay_reserves(state: State, reader: ExtensionReader) -> None:
    """Carry each reserve the hop before set aside into this hop's own sidecar.

    Sienna has reserves and PyPSA has none, so a reserve crossing the PyPSA hub survives only
    in the sidecar. No Sienna component is built from one yet, so the record travels on as it
    stands rather than being read into a field, and its companion series travels with it.
    """
    append_extensions(
        state.destination_extensions, ExtensionKind.RESERVE, reader.relay(ExtensionKind.RESERVE)
    )
    series = state.source_extension_series.get(ExtensionKind.RESERVE)
    if series is not None:
        state.destination_extension_series[ExtensionKind.RESERVE] = series
