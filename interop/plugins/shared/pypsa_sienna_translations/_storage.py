"""Translation objects and helpers for PyPSA StorageUnit (carrier PHS) -> EnergyReservoirStorage.

Pumped-storage hydro is a PyPSA ``StorageUnit`` with ``p_min_pu < 0`` (pumping/charging) and
``p_max_pu > 0`` (generating/discharging). Each becomes a Sienna ``EnergyReservoirStorage``:
a self-contained battery-style device with input/output power limits, a ``storage_capacity``
(= ``max_hours``), an in/out efficiency, and a ``StorageCost``. With ``cyclic_state_of_charge``
the ``storage_target`` pins the end-of-horizon SoC and symmetric shortage/surplus penalties make
it a hard constraint. Both are per component, so a unit that does not cycle takes a target of
zero and no penalty beside one that does, and a fleet may mix the two. inflow, spill_cost, ramp
limits, and up/down times have no home and are dropped (the model is a closed loop).
"""

from __future__ import annotations

from functools import partial

import polars as pl

from interop.core.extensions import ExtensionKind, StorageExtension
from interop.plugins.shared.pypsa_constants import (
    PYPSA_COMPONENT_NAMING,
    PyPSAComponent,
    PyPSAStorageUnitCol,
    PyPSATable,
)
from interop.plugins.shared.pypsa_sienna_translations._component_mapping import (
    ComponentMapping,
    ExtensionSpec,
)
from interop.plugins.shared.pypsa_sienna_translations._prime_mover import enrich_prime_mover
from interop.plugins.shared.pypsa_sienna_translations._shared import (
    pypsa_skip_report,
    pypsa_source_field,
    sienna_dest_field,
    variable_cost_curve,
)
from interop.plugins.shared.pypsa_sienna_translations._ts_info import TimeSeriesInfo
from interop.plugins.shared.pypsa_sienna_user_mappings import CarrierMappings
from interop.plugins.shared.sienna_constants import (
    CYCLIC_ENERGY_PENALTY,
    DEFAULT_CYCLE_LIMITS,
    EFFICIENCY_DTYPE,
    ENERGY_RESERVOIR_STORAGE_DESTINATION_SCHEMA,
    MIN_MAX_DTYPE,
    PRIME_MOVERS_DTYPE,
    SIENNA_TYPE_ATTRIBUTE,
    STORAGE_COST_DTYPE,
    MinMaxField,
    SiennaComponent,
    SiennaCostType,
    SiennaEnergyReservoirStorageCol,
    SiennaPrimeMovers,
    SiennaStorageTech,
    SiennaStructField,
)
from interop.plugins.shared.translation_runner import (
    SkipRule,
    Translation,
    default_translation,
    direct_translation,
    fill_defaults,
    row_position_id_translation,
)
from interop.ports.outbound.reporting import (
    EventKind,
    TranslationEvent,
)

_PRIME_MOVER_COL = "_prime_mover_raw"
_EFFECTIVE_P_NOM = "_effective_p_nom"


_source = partial(pypsa_source_field, PyPSAComponent.STORAGE_UNIT)
_dest = partial(sienna_dest_field, SiennaComponent.ENERGY_RESERVOIR_STORAGE)


def fill_storage_defaults(table: pl.DataFrame) -> pl.DataFrame:
    """Add PyPSA StorageUnit columns absent when all units share the PyPSA default."""
    table = fill_defaults(
        table,
        [
            (PyPSAStorageUnitCol.P_NOM, 0.0),
            (PyPSAStorageUnitCol.P_NOM_OPT, 0.0),
            (PyPSAStorageUnitCol.P_MIN_PU, -1.0),
            (PyPSAStorageUnitCol.P_MAX_PU, 1.0),
            (PyPSAStorageUnitCol.MARGINAL_COST, 0.0),
            (PyPSAStorageUnitCol.MAX_HOURS, 0.0),
            (PyPSAStorageUnitCol.EFFICIENCY_STORE, 1.0),
            (PyPSAStorageUnitCol.EFFICIENCY_DISPATCH, 1.0),
            (PyPSAStorageUnitCol.STATE_OF_CHARGE_INITIAL, 0.0),
        ],
        [
            (PyPSAStorageUnitCol.CYCLIC_STATE_OF_CHARGE, False),
            (PyPSAStorageUnitCol.P_NOM_EXTENDABLE, False),
        ],
    )
    return table.with_columns(
        pl.when(pl.col(PyPSAStorageUnitCol.P_NOM_EXTENDABLE))
        .then(pl.col(PyPSAStorageUnitCol.P_NOM_OPT))
        .otherwise(pl.col(PyPSAStorageUnitCol.P_NOM))
        .alias(_EFFECTIVE_P_NOM)
    )


def build_storage_extensions(
    enriched_src: pl.DataFrame, dst: pl.DataFrame
) -> list[StorageExtension]:
    """Build extension records for every translated PHS unit.

    Records each unit's PyPSA ``p_nom_extendable`` value regardless of whether it is True
    or False — it has no SiennaSchemas home, and the translation makes no capacity-expansion
    decision, so the source value is preserved for round-trip purposes.
    """
    name_to_src = {row[PyPSAStorageUnitCol.NAME]: row for row in enriched_src.iter_rows(named=True)}
    records = [
        StorageExtension(
            name=name,
            p_nom_extendable=name_to_src[name][PyPSAStorageUnitCol.P_NOM_EXTENDABLE],
        )
        for name in dst[SiennaEnergyReservoirStorageCol.NAME].to_list()
    ]
    return records


def enrich_storage_carrier(
    table: pl.DataFrame, prime_mover_map: dict[str, SiennaPrimeMovers]
) -> pl.DataFrame:
    """Pre-compute the prime_mover enrichment column from the user carrier mapping."""
    return enrich_prime_mover(table, PyPSAStorageUnitCol.CARRIER, _PRIME_MOVER_COL, prime_mover_map)


STORAGE_NO_ENERGY_SKIP = pypsa_skip_report(
    component=PyPSAComponent.STORAGE_UNIT,
    name_col=PyPSAStorageUnitCol.NAME,
    counted_noun=PYPSA_COMPONENT_NAMING[PyPSATable.STORAGE_UNITS].plural,
    reason="state no storage hours",
    note=lambda row: (
        f"max_hours is {row[PyPSAStorageUnitCol.MAX_HOURS]}, so it holds no energy and "
        "can neither charge nor discharge"
    ),
    attribute_col=PyPSAStorageUnitCol.MAX_HOURS,
)


def _skip_without_energy(_series: pl.LazyFrame | None) -> SkipRule:
    """A unit of no storage hours holds no energy, whatever series it carries."""
    return SkipRule(keep=pl.col(PyPSAStorageUnitCol.MAX_HOURS) > 0, report=STORAGE_NO_ENERGY_SKIP)


# --- Reusable expressions ---

# state_of_charge_initial / (effective_p_nom * max_hours), clamped to [0, 1].
# Defaults to 0.0 when capacity is zero (e.g. unsolved extendable unit) to
# avoid a division-by-zero that would clip to 1.0 (incorrectly "fully charged").
_initial_level = (
    pl.when(pl.col(_EFFECTIVE_P_NOM) * pl.col(PyPSAStorageUnitCol.MAX_HOURS) > 0)
    .then(
        pl.col(PyPSAStorageUnitCol.STATE_OF_CHARGE_INITIAL)
        / (pl.col(_EFFECTIVE_P_NOM) * pl.col(PyPSAStorageUnitCol.MAX_HOURS))
    )
    .otherwise(0.0)
    .clip(0.0, 1.0)
)

_is_cyclic = pl.col(PyPSAStorageUnitCol.CYCLIC_STATE_OF_CHARGE)


def _min_max(max_expr: pl.Expr) -> pl.Expr:
    return pl.struct(
        pl.lit(0.0).alias(MinMaxField.MIN),
        max_expr.cast(pl.Float64).alias(MinMaxField.MAX),
    ).cast(MIN_MAX_DTYPE)


# --- Translation constants ---

S = SiennaEnergyReservoirStorageCol

_direct = partial(direct_translation, _source, _dest, name_col=PyPSAStorageUnitCol.NAME)
_default = partial(default_translation, _dest, name_col=PyPSAStorageUnitCol.NAME)

STORAGE_ID = row_position_id_translation(
    _dest,
    dest_name_col=S.NAME,
    id_col=S.ID,
    note="assigned by 1-based row position in storage DataFrame",
)

STORAGE_NAME = _direct(source_col=PyPSAStorageUnitCol.NAME, dest_col=S.NAME)

STORAGE_AVAILABLE = _default(
    dest_col=S.AVAILABLE,
    value=True,
    note="PyPSA StorageUnit has no active field; defaulted to True",
)

STORAGE_BUS_NAME = _direct(source_col=PyPSAStorageUnitCol.BUS, dest_col=S.BUS_NAME)

STORAGE_SIENNA_TYPE = Translation(
    exprs=[],
    make_events=lambda old, _: [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                _source(
                    old[PyPSAStorageUnitCol.NAME],
                    PyPSAStorageUnitCol.CARRIER,
                    old[PyPSAStorageUnitCol.CARRIER],
                )
            ],
            destinations=[
                _dest(
                    old[PyPSAStorageUnitCol.NAME],
                    SIENNA_TYPE_ATTRIBUTE,
                    SiennaComponent.ENERGY_RESERVOIR_STORAGE,
                )
            ],
            derivation="PHS carrier -> EnergyReservoirStorage",
        )
    ],
)

STORAGE_PRIME_MOVER = _direct(
    source_col=PyPSAStorageUnitCol.CARRIER,
    dest_col=S.PRIME_MOVER_TYPE,
    expr=pl.col(_PRIME_MOVER_COL).cast(PRIME_MOVERS_DTYPE),
    derivation="carrier -> PrimeMovers via user defined mapping",
)

STORAGE_TECH = _default(
    dest_col=S.STORAGE_TECHNOLOGY_TYPE,
    value=SiennaStorageTech.OTHER_MECH,
    note="StorageTech enum has no PHS-specific value; OTHER_MECH is the closest fit",
)

STORAGE_CAPACITY = _direct(
    source_col=PyPSAStorageUnitCol.MAX_HOURS,
    dest_col=S.STORAGE_CAPACITY,
    derivation="max_hours (pu-hours of base_power)",
)

STORAGE_LEVEL_LIMITS = Translation(
    exprs=[
        pl.struct(
            pl.lit(0.0).alias(MinMaxField.MIN),
            pl.lit(1.0).alias(MinMaxField.MAX),
        )
        .cast(MIN_MAX_DTYPE)
        .alias(S.STORAGE_LEVEL_LIMITS)
    ],
    make_events=lambda old, new: [
        TranslationEvent(
            kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
            destinations=[
                _dest(
                    old[PyPSAStorageUnitCol.NAME],
                    S.STORAGE_LEVEL_LIMITS,
                    new[S.STORAGE_LEVEL_LIMITS],
                )
            ],
            note="allowable SoC band as a ratio of storage_capacity; full range [0, 1]",
        )
    ],
)

STORAGE_INITIAL_LEVEL = _direct(
    source_col=PyPSAStorageUnitCol.STATE_OF_CHARGE_INITIAL,
    dest_col=S.INITIAL_STORAGE_CAPACITY_LEVEL,
    expr=_initial_level,
    derivation="state_of_charge_initial / (effective_p_nom * max_hours), clamped to [0, 1]",
)

STORAGE_RATING = _direct(
    source_col=PyPSAStorageUnitCol.P_MAX_PU,
    dest_col=S.RATING,
    derivation="p_max_pu (discharge-side rating, pu of base_power)",
)

STORAGE_ACTIVE_POWER = _default(
    dest_col=S.ACTIVE_POWER,
    value=0.0,
    note="PHS at rest at start of horizon",
)

STORAGE_INPUT_LIMITS = _direct(
    source_col=PyPSAStorageUnitCol.P_MIN_PU,
    dest_col=S.INPUT_ACTIVE_POWER_LIMITS,
    expr=_min_max(pl.col(PyPSAStorageUnitCol.P_MIN_PU).abs()),
    derivation="(0, abs(p_min_pu)) charging capacity",
)

STORAGE_OUTPUT_LIMITS = _direct(
    source_col=PyPSAStorageUnitCol.P_MAX_PU,
    dest_col=S.OUTPUT_ACTIVE_POWER_LIMITS,
    expr=_min_max(pl.col(PyPSAStorageUnitCol.P_MAX_PU)),
    derivation="(0, p_max_pu) discharging capacity",
)

STORAGE_EFFICIENCY = _direct(
    source_col=PyPSAStorageUnitCol.EFFICIENCY_STORE,
    dest_col=S.EFFICIENCY,
    expr=pl.struct(
        pl.col(PyPSAStorageUnitCol.EFFICIENCY_STORE).alias(SiennaStructField.IN),
        pl.col(PyPSAStorageUnitCol.EFFICIENCY_DISPATCH).alias(SiennaStructField.OUT),
    ).cast(EFFICIENCY_DTYPE),
    derivation="(in=efficiency_store, out=efficiency_dispatch)",
)

STORAGE_REACTIVE_POWER = _default(
    dest_col=S.REACTIVE_POWER,
    value=0.0,
    note="PyPSA networks rarely model reactive power for storage units",
)

STORAGE_BASE_POWER = _direct(
    source_col=PyPSAStorageUnitCol.P_NOM,
    dest_col=S.BASE_POWER,
    expr=pl.col(_EFFECTIVE_P_NOM),
    derivation="p_nom_opt when p_nom_extendable else p_nom",
)

STORAGE_COST = Translation(
    exprs=[
        pl.struct(
            cost_type=pl.lit(SiennaCostType.STORAGE),
            charge_variable_cost=variable_cost_curve(pl.lit(0.0)),
            discharge_variable_cost=variable_cost_curve(pl.col(PyPSAStorageUnitCol.MARGINAL_COST)),
            fixed=pl.lit(0.0),
            start_up=pl.lit(0.0),
            shut_down=pl.lit(0.0),
            energy_shortage_cost=pl.when(_is_cyclic)
            .then(pl.lit(CYCLIC_ENERGY_PENALTY))
            .otherwise(pl.lit(0.0)),
            energy_surplus_cost=pl.when(_is_cyclic)
            .then(pl.lit(CYCLIC_ENERGY_PENALTY))
            .otherwise(pl.lit(0.0)),
        )
        .cast(STORAGE_COST_DTYPE)
        .alias(S.OPERATION_COST)
    ],
    make_events=lambda old, _: [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                _source(
                    old[PyPSAStorageUnitCol.NAME],
                    PyPSAStorageUnitCol.MARGINAL_COST,
                    old[PyPSAStorageUnitCol.MARGINAL_COST],
                )
            ],
            destinations=[
                _dest(
                    old[PyPSAStorageUnitCol.NAME],
                    f"{S.OPERATION_COST}.discharge_variable_cost"
                    ".value_curve.function_data.proportional_term",
                    old[PyPSAStorageUnitCol.MARGINAL_COST],
                )
            ],
            derivation=(
                "discharge_variable_cost = marginal_cost; charge cost 0; "
                "symmetric energy shortage/surplus penalty when cyclic"
            ),
        )
    ],
)

STORAGE_CONVERSION_FACTOR = _default(
    dest_col=S.CONVERSION_FACTOR,
    value=1.0,
    note="no unit conversion between storage_capacity and the energy variable",
)

STORAGE_TARGET = _direct(
    source_col=PyPSAStorageUnitCol.CYCLIC_STATE_OF_CHARGE,
    dest_col=S.STORAGE_TARGET,
    expr=pl.when(_is_cyclic)
    .then(_initial_level * pl.col(PyPSAStorageUnitCol.MAX_HOURS))
    .otherwise(pl.lit(0.0)),
    derivation="initial_storage_capacity_level * max_hours if cyclic else 0.0",
)

STORAGE_CYCLE_LIMITS = _default(
    dest_col=S.CYCLE_LIMITS,
    value=DEFAULT_CYCLE_LIMITS,
    note="cycling_limits formulation attribute disabled; storage_target covers cycling",
    dtype=pl.Int64,
)

ENERGY_RESERVOIR_STORAGE_TRANSLATIONS: list[Translation] = [
    STORAGE_ID,
    STORAGE_NAME,
    STORAGE_AVAILABLE,
    STORAGE_BUS_NAME,
    STORAGE_SIENNA_TYPE,
    STORAGE_PRIME_MOVER,
    STORAGE_TECH,
    STORAGE_CAPACITY,
    STORAGE_LEVEL_LIMITS,
    STORAGE_INITIAL_LEVEL,
    STORAGE_RATING,
    STORAGE_ACTIVE_POWER,
    STORAGE_INPUT_LIMITS,
    STORAGE_OUTPUT_LIMITS,
    STORAGE_EFFICIENCY,
    STORAGE_REACTIVE_POWER,
    STORAGE_BASE_POWER,
    STORAGE_COST,
    STORAGE_CONVERSION_FACTOR,
    STORAGE_TARGET,
    STORAGE_CYCLE_LIMITS,
]


def _enrich_storage(
    table: pl.DataFrame,
    _ts: pl.LazyFrame | None,
    _ts_info: TimeSeriesInfo,
    mappings: CarrierMappings,
) -> pl.DataFrame:
    return enrich_storage_carrier(table, mappings.get_prime_mover_map())


PHS_STORAGE_MAPPING = ComponentMapping(
    source_table=PyPSATable.STORAGE_UNITS,
    carrier_col=PyPSAStorageUnitCol.CARRIER,
    fill_defaults=fill_storage_defaults,
    enrich=_enrich_storage,
    translations=ENERGY_RESERVOIR_STORAGE_TRANSLATIONS,
    schema=ENERGY_RESERVOIR_STORAGE_DESTINATION_SCHEMA,
    sienna_component=SiennaComponent.ENERGY_RESERVOIR_STORAGE,
    skip=_skip_without_energy,
    extensions=ExtensionSpec(ExtensionKind.STORAGE, build_storage_extensions),
)
