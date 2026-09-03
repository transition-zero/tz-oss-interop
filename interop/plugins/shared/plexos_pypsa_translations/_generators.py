"""PLEXOS Generator -> PyPSA Generator mapping.

Walks the staged Generator class once: each generator is derived into a
``GeneratorMapping``, its decisions recorded, and its destination row written. Generators
whose availability comes from a file-backed profile also get time-series metadata, which
the sink uses to write ``p_max_pu`` over the snapshots.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from interop.core.extensions import ExtensionKind, GeneratorExtension, append_extensions
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import UNIT_MW
from interop.plugins.shared.plexos_constants import (
    PlexosClass,
    PlexosCollection,
    PlexosObjectCol,
    PlexosProperty,
)
from interop.plugins.shared.plexos_pypsa_translations._generator_decisions import (
    GeneratorDecisions,
    decide_generator,
    record_generator,
)
from interop.plugins.shared.plexos_pypsa_translations._generator_derivation import (
    GeneratorMapping,
    ThermalCostTerms,
    derive_generator,
    has_infeasible_dispatch_range,
    read_source,
)
from interop.plugins.shared.plexos_pypsa_translations._generator_lookups import (
    Lookups,
    build_lookups,
)
from interop.plugins.shared.plexos_pypsa_translations._shared import outage_time_series
from interop.plugins.shared.plexos_pypsa_translations._storage_turbines import (
    storage_turbine_names,
)
from interop.plugins.shared.plexos_pypsa_translations.constants import (
    GENERATOR_EXT_CATEGORY_FIELD,
)
from interop.plugins.shared.plexos_pypsa_translations.decisions import (
    ComponentReporter,
    Decision,
    MappedColumns,
    SourceValue,
    destination_row,
)
from interop.plugins.shared.pypsa_constants import (
    GENERATORS_DESTINATION_SCHEMA,
    PyPSAComponent,
    PyPSADestinationTable,
    PyPSAGeneratorCol,
    ReverseTimeSeriesMetadataCol,
)
from interop.plugins.shared.pypsa_destination import append_destination_rows
from interop.plugins.shared.pypsa_time_series import (
    append_metadata,
    metadata_row,
    series_components,
    series_timing,
)
from interop.plugins.shared.warning_text import name_a_few

log = logging.getLogger(__name__)

_NO_BUS_NOTE = "a generator on no node has no bus to connect to"
_FILE_BACKED_NOTE = (
    "Max Capacity comes from a data file rather than a value, so the generator "
    "has no p_nom to size it or to per-unitise its availability against"
)
_RETIRED_NOTE = "Units = 0 marks a retired generator"
_CATEGORY_DERIVATION = "a PyPSA generator carries one carrier, so the category travels beside it"
_PROFILE_NOT_STAGED_NOTE = (
    "the source staged no series for this profile, so p_max_pu keeps the static "
    "availability instead"
)

# Stands in for the value of a file-backed property, which PLEXOS states as a path.
_DATA_FILE = "data file"
_PROFILE = "profile"

_CATEGORY_COLUMN = MappedColumns((GENERATOR_EXT_CATEGORY_FIELD,))


def map_generators(state: State, recorder: ScopedRecorder) -> None:
    """Translate staged PLEXOS Generators into the PyPSA generators destination table."""
    generators = state.source_topology.get(PlexosClass.GENERATOR)
    if generators is None:
        return
    lookups = build_lookups(state)
    reporter = ComponentReporter(recorder, PyPSAComponent.GENERATOR)
    storage_turbines = storage_turbine_names(state)
    translated = [
        one
        for generator in generators.collect().iter_rows(named=True)
        if generator[PlexosObjectCol.NAME] not in storage_turbines
        if (one := _map_one(generator, lookups, reporter)) is not None
    ]
    if not translated:
        return
    append_destination_rows(
        state,
        PyPSADestinationTable.GENERATORS,
        [
            destination_row(one.decisions, PyPSAGeneratorCol.NAME, one.mapping.name)
            for one in translated
        ],
        GENERATORS_DESTINATION_SCHEMA,
    )
    mappings = [one.mapping for one in translated]
    _carry_categories_to_extensions(state, mappings, reporter)
    _record_availability_time_series(state, mappings, reporter)


@dataclass(frozen=True)
class _TranslatedGenerator:
    """One generator's derived values and the destination decisions they justify."""

    mapping: GeneratorMapping
    decisions: GeneratorDecisions


def _carry_categories_to_extensions(
    state: State, mappings: list[GeneratorMapping], reporter: ComponentReporter
) -> None:
    """Put every generator's PLEXOS category in the sidecar, since only one of it and the
    fuel could become the carrier. The one that did not is what the report names.
    """
    for mapping in mappings:
        if mapping.carrier != mapping.category:
            reporter.record(mapping.name, _CATEGORY_COLUMN, _category_decision(mapping))
    records = [
        GeneratorExtension(name=mapping.name, category=mapping.category) for mapping in mappings
    ]
    append_extensions(state.destination_extensions, ExtensionKind.GENERATOR, records)


def _category_decision(mapping: GeneratorMapping) -> Decision:
    source = _source(mapping.name, PlexosObjectCol.CATEGORY, mapping.category)
    return Decision.derived(mapping.category, [source], _CATEGORY_DERIVATION)


def _map_one(
    generator: dict[str, Any], lookups: Lookups, reporter: ComponentReporter
) -> _TranslatedGenerator | None:
    name = generator[PlexosObjectCol.NAME]
    node = lookups.gen_to_node.get(name)
    if node is None:
        reporter.record_skipped(_source(name, PlexosCollection.NODES, None), _NO_BUS_NOTE)
        return None
    if PlexosProperty.MAX_CAPACITY in lookups.file_backed_properties.get(name, []):
        reporter.record_skipped(
            _source(name, PlexosProperty.MAX_CAPACITY, _DATA_FILE, UNIT_MW), _FILE_BACKED_NOTE
        )
        return None
    source = read_source(generator, name, lookups)
    if source.units == 0.0:
        reporter.record_skipped(_source(name, PlexosProperty.UNITS, source.units), _RETIRED_NOTE)
        return None
    if source.p_nom <= 0.0:
        reporter.record_skipped(
            _source(name, PlexosProperty.MAX_CAPACITY, None, UNIT_MW),
            f"generator dropped: p_nom is {source.p_nom} MW, so it can never dispatch",
        )
        return None
    mapping = derive_generator(source, node, lookups)
    if has_infeasible_dispatch_range(mapping):
        _report_infeasible_dispatch_range(mapping, reporter)
        return None
    decisions = decide_generator(mapping)
    record_generator(reporter, decisions)
    return _TranslatedGenerator(mapping, decisions)


def _report_infeasible_dispatch_range(
    mapping: GeneratorMapping, reporter: ComponentReporter
) -> None:
    p_min_pu = mapping.minimum.p_min_pu
    p_max_pu = mapping.availability.static_p_max_pu
    reporter.record_skipped(
        _source(mapping.name, mapping.minimum.source_property, mapping.minimum.source_value),
        f"p_min_pu {p_min_pu} sits above p_max_pu {p_max_pu}, which PyPSA cannot dispatch, "
        "so the generator is dropped",
    )
    log.warning(
        "plexos: dropping Generator %r: p_min_pu %s is above p_max_pu %s, which PyPSA "
        "cannot dispatch",
        mapping.name,
        p_min_pu,
        p_max_pu,
    )


def _source(
    name: str, attribute: str | None, value: object, unit: str | None = None
) -> SourceValue:
    return SourceValue(PlexosClass.GENERATOR, name, attribute, value, unit)


@dataclass(frozen=True)
class _ProfileOwner:
    """A generator whose p_max_pu comes from a file-backed profile, and its scaling."""

    name: str
    scale: float


def _record_availability_time_series(
    state: State, mappings: list[GeneratorMapping], reporter: ComponentReporter
) -> None:
    """Emit p_max_pu metadata for each generator carrying a Rating / Rating Factor profile."""
    owners_by_property: dict[str, list[_ProfileOwner]] = {}
    for mapping in mappings:
        profile = mapping.availability.profile
        if profile is not None:
            owner = _ProfileOwner(mapping.name, profile.scale)
            owners_by_property.setdefault(profile.property_name, []).append(owner)
    rows: list[dict[str, Any]] = []
    for property_name, owners in owners_by_property.items():
        if (PlexosClass.GENERATOR, property_name) in state.source_time_series:
            rows.extend(_metadata_rows(state, property_name, owners))
        else:
            _report_profile_not_staged(property_name, owners, reporter)
    availability = rows + _units_out_rows(state, mappings) + _dated_capacity_rows(state, mappings)
    append_metadata(
        state,
        availability
        + _minimum_follows_availability(availability, mappings)
        + _dated_fuel_price_rows(state, mappings),
    )


def _minimum_follows_availability(
    availability: list[dict[str, Any]], mappings: list[GeneratorMapping]
) -> list[dict[str, Any]]:
    """Let a minimum stable level fall with the availability above it.

    A unit derated to nothing has no minimum left to meet, and a floor that stayed put
    would ask PyPSA to dispatch the generator between a minimum and a ceiling beneath it.
    Each generator's minimum scales only its first series, because the sink multiplies
    every series it holds for one attribute together.
    """
    minimums = {
        mapping.name: mapping.minimum.p_min_pu for mapping in mappings if mapping.minimum.p_min_pu
    }
    already_scaled: set[str] = set()
    rows = []
    for row in availability:
        name = row[ReverseTimeSeriesMetadataCol.COMPONENT_NAME]
        if name in minimums:
            rows.append(_as_minimum(row, 1.0 if name in already_scaled else minimums[name]))
            already_scaled.add(name)
    return rows


def _as_minimum(row: dict[str, Any], minimum: float) -> dict[str, Any]:
    return {
        **row,
        ReverseTimeSeriesMetadataCol.ATTRIBUTE: PyPSAGeneratorCol.P_MIN_PU,
        ReverseTimeSeriesMetadataCol.SCALING_FACTOR: (
            row[ReverseTimeSeriesMetadataCol.SCALING_FACTOR] * minimum
        ),
        ReverseTimeSeriesMetadataCol.OFFSET: row[ReverseTimeSeriesMetadataCol.OFFSET] * minimum,
    }


def _report_profile_not_staged(
    property_name: str, owners: list[_ProfileOwner], reporter: ComponentReporter
) -> None:
    """A property the source could not read leaves its owners on their static availability."""
    for owner in owners:
        reporter.record_dropped(
            _source(owner.name, property_name, _PROFILE), _PROFILE_NOT_STAGED_NOTE
        )
    log.warning(
        "plexos: no staged series for Generator property '%s', so %s generators keep their "
        "static availability: %s",
        property_name,
        len(owners),
        name_a_few(sorted(owner.name for owner in owners)),
    )


def _units_out_rows(state: State, mappings: list[GeneratorMapping]) -> list[dict[str, Any]]:
    """Derate each generator by its units-out trace, against the unit count it states."""
    units_by_generator = {mapping.name: mapping.units for mapping in mappings if mapping.units}
    return outage_time_series(
        state,
        PlexosClass.GENERATOR,
        PyPSADestinationTable.GENERATORS,
        PyPSAGeneratorCol.P_MAX_PU,
        units_by_generator,
    )


def _dated_capacity_rows(state: State, mappings: list[GeneratorMapping]) -> list[dict[str, Any]]:
    """Hold each generator to the capacity its model dates it at, as a share of its greatest.

    ``p_nom`` is already the highest capacity the generator reaches in the window, so a date
    band stating a lower one is the fraction of that peak it can reach while the band runs.
    """
    frame = state.source_time_series.get((PlexosClass.GENERATOR, PlexosProperty.MAX_CAPACITY))
    if frame is None:
        return []
    timing = series_timing(frame)
    present = set(series_components(frame))
    return [
        metadata_row(
            component_table=PyPSADestinationTable.GENERATORS,
            component_name=mapping.name,
            attribute=PyPSAGeneratorCol.P_MAX_PU,
            source_owner_type=PlexosClass.GENERATOR,
            source_series_name=PlexosProperty.MAX_CAPACITY,
            scaling_factor=mapping.units / mapping.p_nom,
            timing=timing,
        )
        for mapping in mappings
        if mapping.name in present and mapping.p_nom
    ]


def _dated_fuel_price_rows(state: State, mappings: list[GeneratorMapping]) -> list[dict[str, Any]]:
    """Cost each generator's output at the fuel price in force, hour by hour.

    A fuel priced by date moves marginal cost with it: the sink reads the fuel's own series
    through the burning generator's heat rate, and adds the rest of that generator's cost.
    """
    frame = state.source_time_series.get((PlexosClass.FUEL, PlexosProperty.PRICE))
    if frame is None:
        return []
    timing = series_timing(frame)
    priced_by_date = set(series_components(frame))
    return [
        _fuel_price_row(mapping, terms, timing)
        for mapping in mappings
        if (terms := mapping.cost.thermal_terms) is not None and terms.fuel_name in priced_by_date
    ]


def _fuel_price_row(
    mapping: GeneratorMapping, terms: ThermalCostTerms, timing: tuple[int, str, int]
) -> dict[str, Any]:
    return metadata_row(
        component_table=PyPSADestinationTable.GENERATORS,
        component_name=mapping.name,
        attribute=PyPSAGeneratorCol.MARGINAL_COST,
        source_owner_type=PlexosClass.FUEL,
        source_component_name=terms.fuel_name,
        source_series_name=PlexosProperty.PRICE,
        scaling_factor=terms.heat_rate,
        offset=terms.cost_without_fuel,
        timing=timing,
    )


def _metadata_rows(
    state: State, property_name: str, owners: list[_ProfileOwner]
) -> list[dict[str, Any]]:
    """The source stages one series per file-backed property, stamped with the generator
    that reads it, so every owner here has rows in that series."""
    timing = series_timing(state.source_time_series[(PlexosClass.GENERATOR, property_name)])
    return [
        metadata_row(
            component_table=PyPSADestinationTable.GENERATORS,
            component_name=owner.name,
            attribute=PyPSAGeneratorCol.P_MAX_PU,
            source_owner_type=PlexosClass.GENERATOR,
            source_series_name=property_name,
            scaling_factor=owner.scale,
            timing=timing,
        )
        for owner in owners
    ]
