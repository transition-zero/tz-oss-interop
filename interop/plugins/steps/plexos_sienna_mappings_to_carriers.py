"""Derive the carrier mappings file the PyPSA to Sienna leg reads.

`plexos-to-pypsa` gives a generator the name of its Fuel when it burns one, and its PLEXOS
category when it does not, so a `fuel` row and a `category` row both give a carrier that is
the name the user wrote. A `storage_kind` row gives the fixed carrier that leg writes
instead.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar, NamedTuple

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import ALL_COMPONENTS, Framework
from interop.plugins.shared.plexos_sienna_user_mappings import (
    CARRIER_BY_STORAGE_KIND,
    PLEXOS_MAPPINGS_TABLE,
    PlexosConcept,
    PlexosMappingCol,
    PlexosStorageKind,
)
from interop.plugins.shared.pypsa_sienna_user_mappings import (
    CARRIER_MAPPINGS_TABLE,
    CarrierMappingCol,
)
from interop.plugins.shared.sienna_constants import SiennaComponent, SiennaPrimeMovers
from interop.ports.errors import UserInputError
from interop.ports.outbound.reporting import (
    DestinationField,
    EventKind,
    SourceField,
    TranslationEvent,
)

CARRIER_MAPPINGS_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    CarrierMappingCol.PYPSA_CARRIER: pl.Utf8,
    CarrierMappingCol.SIENNA_COMPONENT_TYPE: pl.Utf8,
    CarrierMappingCol.SIENNA_FUEL_TYPE: pl.Utf8,
    CarrierMappingCol.SIENNA_PRIME_MOVER_TYPE: pl.Utf8,
}

# What each PLEXOS unit with a translator-written carrier becomes in Sienna, unless the
# user's file states a storage_kind row of its own.
_DEFAULT_BY_STORAGE_KIND: dict[PlexosStorageKind, tuple[SiennaComponent, SiennaPrimeMovers]] = {
    PlexosStorageKind.RESERVOIR_HYDRO: (SiennaComponent.HYDRO_DISPATCH, SiennaPrimeMovers.HY),
    PlexosStorageKind.PUMPED_STORAGE: (
        SiennaComponent.ENERGY_RESERVOIR_STORAGE,
        SiennaPrimeMovers.PS,
    ),
    PlexosStorageKind.BATTERY: (SiennaComponent.ENERGY_RESERVOIR_STORAGE, SiennaPrimeMovers.BA),
}

_DEFAULT_NOTE = "no storage_kind row states this unit, so the translator's default applies"

# The two columns a stated row loses; every other column it holds is already a Sienna target.
_PLEXOS_COLUMNS = (PlexosMappingCol.PLEXOS_CONCEPT, PlexosMappingCol.PLEXOS_NAME)


class _DerivedMapping(NamedTuple):
    """One carrier mappings row, beside the PLEXOS words it came from."""

    concept: str
    plexos_name: str
    carrier_row: dict[str, Any]


class PlexosSiennaMappingsToCarriers(TranslationStep):
    name: ClassVar[str] = "plexos_sienna_mappings_to_carriers"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def run(self, state: State, params: BaseModel | None) -> State:
        stated_rows = state.source_topology[PLEXOS_MAPPINGS_TABLE].collect()
        stated = [_derive_from(row) for row in stated_rows.iter_rows(named=True)]
        defaults = [_default_for(kind) for kind in _kinds_not_stated(stated_rows)]
        self._record(stated, EventKind.VALUE_DERIVED, None)
        self._record(defaults, EventKind.TRANSLATOR_DEFAULT_APPLIED, _DEFAULT_NOTE)
        state.destination_tables[CARRIER_MAPPINGS_TABLE] = pl.DataFrame(
            _one_row_per_carrier(stated + defaults), schema=CARRIER_MAPPINGS_SCHEMA
        )
        return state

    def _record(
        self, derived: Sequence[_DerivedMapping], kind: EventKind, note: str | None
    ) -> None:
        for entry in derived:
            self._recorder.append(_event(entry, kind, note))


def _one_row_per_carrier(derived: Sequence[_DerivedMapping]) -> list[dict[str, Any]]:
    """PyPSA holds one carrier per name, so a Fuel and a category of one name share a row.

    Two rows giving one carrier two different Sienna types cannot both hold, and nothing
    downstream can tell the two apart, so the user has to settle it.
    """
    by_carrier: dict[str, dict[str, Any]] = {}
    for entry in derived:
        carrier = entry.carrier_row[CarrierMappingCol.PYPSA_CARRIER]
        first = by_carrier.setdefault(carrier, entry.carrier_row)
        if first != entry.carrier_row:
            raise UserInputError(
                f"The PLEXOS mappings file gives the carrier {carrier!r} two different Sienna "
                f"targets: {first} and {entry.carrier_row}. A Fuel and a generator category of "
                "the same name become one PyPSA carrier, so state one target for it."
            )
    return list(by_carrier.values())


def _derive_from(row: dict[str, Any]) -> _DerivedMapping:
    """One row of the user's file, with its PLEXOS words replaced by the PyPSA carrier."""
    concept = PlexosConcept(row[PlexosMappingCol.PLEXOS_CONCEPT])
    plexos_name = row[PlexosMappingCol.PLEXOS_NAME]
    target = {name: value for name, value in row.items() if name not in _PLEXOS_COLUMNS}
    return _DerivedMapping(
        concept=str(concept),
        plexos_name=plexos_name,
        carrier_row={
            CarrierMappingCol.PYPSA_CARRIER: _carrier_for(concept, plexos_name),
            **target,
        },
    )


def _carrier_for(concept: PlexosConcept, plexos_name: str) -> str:
    if concept is PlexosConcept.STORAGE_KIND:
        return CARRIER_BY_STORAGE_KIND[PlexosStorageKind(plexos_name)]
    return plexos_name


def _default_for(kind: PlexosStorageKind) -> _DerivedMapping:
    component, prime_mover = _DEFAULT_BY_STORAGE_KIND[kind]
    return _DerivedMapping(
        concept=str(PlexosConcept.STORAGE_KIND),
        plexos_name=str(kind),
        carrier_row={
            CarrierMappingCol.PYPSA_CARRIER: CARRIER_BY_STORAGE_KIND[kind],
            CarrierMappingCol.SIENNA_COMPONENT_TYPE: str(component),
            CarrierMappingCol.SIENNA_FUEL_TYPE: None,
            CarrierMappingCol.SIENNA_PRIME_MOVER_TYPE: str(prime_mover),
        },
    )


def _kinds_not_stated(stated_rows: pl.DataFrame) -> list[PlexosStorageKind]:
    stated = set(
        stated_rows.filter(
            pl.col(PlexosMappingCol.PLEXOS_CONCEPT) == str(PlexosConcept.STORAGE_KIND)
        )[PlexosMappingCol.PLEXOS_NAME].to_list()
    )
    return [kind for kind in PlexosStorageKind if kind.value not in stated]


def _event(entry: _DerivedMapping, kind: EventKind, note: str | None) -> TranslationEvent:
    row = entry.carrier_row
    return TranslationEvent(
        kind=kind,
        sources=[
            SourceField(
                framework=Framework.PLEXOS,
                component=entry.concept,
                name=entry.plexos_name,
            )
        ],
        destinations=[
            DestinationField(
                framework=Framework.SIENNA,
                component=row[CarrierMappingCol.SIENNA_COMPONENT_TYPE],
                name=ALL_COMPONENTS,
                attribute=CarrierMappingCol.PYPSA_CARRIER,
                value=row[CarrierMappingCol.PYPSA_CARRIER],
            )
        ],
        note=note,
    )
