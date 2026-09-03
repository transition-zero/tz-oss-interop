"""Translation objects and helpers for PyPSA StorageUnit (carrier hydro) -> Sienna HydroDispatch.

Reservoir hydro is a PyPSA ``StorageUnit`` (it has an inflow series and a round-trip
efficiency), not a ``Generator``. Each such unit becomes a ``HydroDispatch`` dispatched under
``HydroDispatchRunOfRiverBudget``, which needs two time series:

- ``max_active_power``: the per-step active-power cap. PSI requires this even when constant,
  so a flat series of the static ``p_max_pu`` is synthesised over the inflow snapshots.
- ``hydro_budget``: the horizon energy budget = ``inflow * efficiency_dispatch / p_nom``
  (per-unit of base_power). This rides the raw inflow series with a per-unit scaling factor.

Only HydroDispatch's required fields are emitted; ramp_limits, time_limits, status,
time_at_status, and reactive_power_limits have no StorageUnit source and are omitted.
"""

from __future__ import annotations

from functools import partial
from typing import Any

import polars as pl

from interop.plugins.shared.constants import UNIT_MW
from interop.plugins.shared.pypsa_constants import (
    PyPSAComponent,
    PyPSAStorageUnitCol,
    PyPSATable,
    PyPSATimeSeriesCol,
)
from interop.plugins.shared.pypsa_sienna_translations._component_mapping import (
    ComponentMapping,
    DerivedSeries,
)
from interop.plugins.shared.pypsa_sienna_translations._prime_mover import enrich_prime_mover
from interop.plugins.shared.pypsa_sienna_translations._shared import (
    pypsa_skip_report,
    pypsa_source_field,
    sienna_dest_field,
    ts_association_row,
    variable_cost_curve,
)
from interop.plugins.shared.pypsa_sienna_translations._ts_info import TimeSeriesInfo
from interop.plugins.shared.pypsa_sienna_user_mappings import CarrierMappings
from interop.plugins.shared.pypsa_time_series import series_components
from interop.plugins.shared.sienna_constants import (
    ACTIVE_POWER_LIMITS_DTYPE,
    HYDRO_DISPATCH_DESTINATION_SCHEMA,
    HYDRO_GENERATION_COST_DTYPE,
    PRIME_MOVERS_DTYPE,
    SIENNA_TYPE_ATTRIBUTE,
    TIME_SERIES_ASSOCIATION_SCHEMA,
    SiennaComponent,
    SiennaCostType,
    SiennaHydroGeneratorCol,
    SiennaPrimeMovers,
    SiennaSeriesName,
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

# Synthetic source_time_series attribute under which the hydro step registers the flat
# max_active_power series so the h5 sink can stream it like any other source series.
HYDRO_MAX_ACTIVE_POWER_ATTR = "_hydro_max_active_power"

_PRIME_MOVER_COL = "_prime_mover_raw"
_EFFECTIVE_P_NOM = "_effective_p_nom"


_source = partial(pypsa_source_field, PyPSAComponent.STORAGE_UNIT)
_dest = partial(sienna_dest_field, SiennaComponent.HYDRO_DISPATCH)


HYDRO_NO_INFLOW_SKIP = pypsa_skip_report(
    component=PyPSAComponent.STORAGE_UNIT,
    name_col=PyPSAStorageUnitCol.NAME,
    counted_noun="hydro StorageUnit(s)",
    reason="state no inflow",
    note=(
        "no inflow time series, so it has no energy budget and would run at full "
        "output on water nobody stated"
    ),
)


def fill_hydro_defaults(table: pl.DataFrame) -> pl.DataFrame:
    """Add PyPSA StorageUnit columns absent when all units share the PyPSA default."""
    table = fill_defaults(
        table,
        [
            (PyPSAStorageUnitCol.P_NOM, 0.0),
            (PyPSAStorageUnitCol.P_NOM_OPT, 0.0),
            (PyPSAStorageUnitCol.P_MIN_PU, 0.0),
            (PyPSAStorageUnitCol.P_MAX_PU, 1.0),
            (PyPSAStorageUnitCol.MARGINAL_COST, 0.0),
            (PyPSAStorageUnitCol.EFFICIENCY_DISPATCH, 1.0),
        ],
        [(PyPSAStorageUnitCol.P_NOM_EXTENDABLE, False)],
    )
    return table.with_columns(
        pl.when(pl.col(PyPSAStorageUnitCol.P_NOM_EXTENDABLE))
        .then(pl.col(PyPSAStorageUnitCol.P_NOM_OPT))
        .otherwise(pl.col(PyPSAStorageUnitCol.P_NOM))
        .alias(_EFFECTIVE_P_NOM)
    )


def enrich_hydro_carrier(
    table: pl.DataFrame, prime_mover_map: dict[str, SiennaPrimeMovers]
) -> pl.DataFrame:
    """Pre-compute the prime_mover enrichment column from the user carrier mapping."""
    return enrich_prime_mover(table, PyPSAStorageUnitCol.CARRIER, _PRIME_MOVER_COL, prime_mover_map)


def build_hydro_max_active_power_series(
    table: pl.DataFrame,
    inflow_lf: pl.LazyFrame,
) -> pl.LazyFrame:
    """Synthesise the flat max_active_power series (static p_max_pu over inflow snapshots).

    Returns a (component, snapshot, value) LazyFrame the hydro step registers in
    ``State.source_time_series`` so the h5 sink streams it like any source series. The
    inflow's ``sample`` column comes with it where the inflow carries one, because a series
    with no sample belongs to every replication and this one belongs to the inflow's.
    """
    pmax_by_name = dict(
        zip(
            table[PyPSAStorageUnitCol.NAME].to_list(),
            table[PyPSAStorageUnitCol.P_MAX_PU].to_list(),
            strict=True,
        )
    )
    return (
        inflow_lf.filter(pl.col(PyPSATimeSeriesCol.COMPONENT).is_in(list(pmax_by_name)))
        .select(_kept_columns(inflow_lf))
        .with_columns(
            pl.col(PyPSATimeSeriesCol.COMPONENT)
            .replace_strict(pmax_by_name, return_dtype=pl.Float64)
            .alias(PyPSATimeSeriesCol.VALUE)
        )
    )


def _kept_columns(inflow_lf: pl.LazyFrame) -> list[str]:
    """The columns the synthesised series carries over from the inflow it is built on."""
    kept = [PyPSATimeSeriesCol.COMPONENT, PyPSATimeSeriesCol.SNAPSHOT]
    if PyPSATimeSeriesCol.SAMPLE in inflow_lf.collect_schema().names():
        kept.append(PyPSATimeSeriesCol.SAMPLE)
    return kept


def build_hydro_ts_associations(
    enriched_src: pl.DataFrame,
    dst: pl.DataFrame,
    ts_info: TimeSeriesInfo,
) -> pl.DataFrame:
    """Build the two TimeSeriesAssociation rows per hydro unit: max_active_power + hydro_budget.

    ``max_active_power`` points at the synthesised flat series (scaling_factor 1.0).
    ``hydro_budget`` rides the raw inflow series with scaling_factor ``p_nom /
    efficiency_dispatch``, so the stored shape is ``inflow * efficiency_dispatch / p_nom``
    (per-unit of base_power).
    """
    if dst.is_empty():
        return pl.DataFrame(schema=TIME_SERIES_ASSOCIATION_SCHEMA)
    name_to_id = dict(
        zip(
            dst[SiennaHydroGeneratorCol.NAME].to_list(),
            dst[SiennaHydroGeneratorCol.ID].to_list(),
            strict=True,
        )
    )
    rows: list[dict[str, Any]] = []
    for src_row in enriched_src.iter_rows(named=True):
        name = src_row[PyPSAStorageUnitCol.NAME]
        owner_id = name_to_id[name]
        rows.append(
            ts_association_row(
                owner_type=SiennaComponent.HYDRO_DISPATCH,
                owner_id=owner_id,
                component_name=name,
                series_name=SiennaSeriesName.MAX_ACTIVE_POWER,
                ts_info=ts_info,
                source_table=PyPSATable.STORAGE_UNITS,
                source_attribute=HYDRO_MAX_ACTIVE_POWER_ATTR,
                scaling_factor=1.0,
            )
        )
        rows.append(
            ts_association_row(
                owner_type=SiennaComponent.HYDRO_DISPATCH,
                owner_id=owner_id,
                component_name=name,
                series_name=SiennaSeriesName.HYDRO_BUDGET,
                ts_info=ts_info,
                source_table=PyPSATable.STORAGE_UNITS,
                source_attribute=PyPSAStorageUnitCol.INFLOW,
                scaling_factor=(
                    src_row[_EFFECTIVE_P_NOM] / src_row[PyPSAStorageUnitCol.EFFICIENCY_DISPATCH]
                ),
            )
        )
    return pl.DataFrame(rows, schema=TIME_SERIES_ASSOCIATION_SCHEMA)


# --- Translation constants ---

H = SiennaHydroGeneratorCol

_direct = partial(direct_translation, _source, _dest, name_col=PyPSAStorageUnitCol.NAME)
_default = partial(default_translation, _dest, name_col=PyPSAStorageUnitCol.NAME)

HYDRO_ID = row_position_id_translation(
    _dest,
    dest_name_col=H.NAME,
    id_col=H.ID,
    note="assigned by 1-based row position in hydro generators DataFrame",
)

HYDRO_NAME = _direct(source_col=PyPSAStorageUnitCol.NAME, dest_col=H.NAME)

HYDRO_AVAILABLE = _default(
    dest_col=H.AVAILABLE,
    value=True,
    note="PyPSA StorageUnit has no active field; defaulted to True",
)

HYDRO_BUS_NAME = _direct(source_col=PyPSAStorageUnitCol.BUS, dest_col=H.BUS_NAME)

HYDRO_SIENNA_TYPE = Translation(
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
                    SiennaComponent.HYDRO_DISPATCH,
                )
            ],
            derivation="hydro carrier -> HydroDispatch",
        )
    ],
)

HYDRO_PRIME_MOVER = _direct(
    source_col=PyPSAStorageUnitCol.CARRIER,
    dest_col=H.PRIME_MOVER_TYPE,
    expr=pl.col(_PRIME_MOVER_COL).cast(PRIME_MOVERS_DTYPE),
    derivation="carrier -> PrimeMovers via user defined mapping",
)

HYDRO_BASE_POWER = _direct(
    source_col=PyPSAStorageUnitCol.P_NOM,
    dest_col=H.BASE_POWER,
    expr=pl.col(_EFFECTIVE_P_NOM),
    unit=UNIT_MW,
    derivation="p_nom_opt when p_nom_extendable else p_nom",
)

HYDRO_ACTIVE_POWER = _direct(
    source_col=PyPSAStorageUnitCol.P_NOM,
    dest_col=H.ACTIVE_POWER,
    expr=pl.col(_EFFECTIVE_P_NOM) * pl.col(PyPSAStorageUnitCol.P_MIN_PU),
    unit=UNIT_MW,
    derivation="effective_p_nom * p_min_pu (initial dispatch = min operating point)",
)

HYDRO_REACTIVE_POWER = _default(
    dest_col=H.REACTIVE_POWER,
    value=0.0,
    note="PyPSA networks rarely model reactive power for storage units",
)

HYDRO_RATING = _direct(
    source_col=PyPSAStorageUnitCol.P_MAX_PU,
    dest_col=H.RATING,
    derivation="p_max_pu (per-unit nameplate rating; typically 1.0)",
)

HYDRO_APL = _direct(
    source_col=PyPSAStorageUnitCol.P_NOM,
    dest_col=H.ACTIVE_POWER_LIMITS,
    expr=pl.struct(
        min=(pl.col(_EFFECTIVE_P_NOM) * pl.col(PyPSAStorageUnitCol.P_MIN_PU)).cast(pl.Float64),
        max=(pl.col(_EFFECTIVE_P_NOM) * pl.col(PyPSAStorageUnitCol.P_MAX_PU)).cast(pl.Float64),
    ).cast(ACTIVE_POWER_LIMITS_DTYPE),
    unit=UNIT_MW,
    derivation="min=effective_p_nom*p_min_pu, max=effective_p_nom*p_max_pu",
)

HYDRO_COST = Translation(
    exprs=[
        pl.struct(
            cost_type=pl.lit(SiennaCostType.HYDRO_GEN),
            variable=variable_cost_curve(pl.col(PyPSAStorageUnitCol.MARGINAL_COST)),
            fixed=pl.lit(0.0),
        )
        .cast(HYDRO_GENERATION_COST_DTYPE)
        .alias(SiennaHydroGeneratorCol.OPERATION_COST)
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
                    f"{SiennaHydroGeneratorCol.OPERATION_COST}"
                    ".variable.value_curve.function_data.proportional_term",
                    old[PyPSAStorageUnitCol.MARGINAL_COST],
                )
            ],
            derivation="flat marginal_cost ($/MWh) -> single-segment linear CostCurve",
        )
    ],
)

HYDRO_DISPATCH_TRANSLATIONS: list[Translation] = [
    HYDRO_ID,
    HYDRO_NAME,
    HYDRO_AVAILABLE,
    HYDRO_BUS_NAME,
    HYDRO_SIENNA_TYPE,
    HYDRO_PRIME_MOVER,
    HYDRO_BASE_POWER,
    HYDRO_ACTIVE_POWER,
    HYDRO_REACTIVE_POWER,
    HYDRO_RATING,
    HYDRO_APL,
    HYDRO_COST,
]


def _enrich_hydro(
    table: pl.DataFrame,
    _series: pl.LazyFrame | None,
    _ts_info: TimeSeriesInfo,
    carrier_mappings: CarrierMappings,
) -> pl.DataFrame:
    return enrich_hydro_carrier(table, carrier_mappings.get_prime_mover_map())


def _skip_without_inflow(inflow: pl.LazyFrame | None) -> SkipRule:
    """A unit with no inflow has no energy budget, so it would run at full output on nothing."""
    named = [] if inflow is None else series_components(inflow)
    return SkipRule(
        keep=pl.col(PyPSAStorageUnitCol.NAME).is_in(named),
        report=HYDRO_NO_INFLOW_SKIP,
    )


HYDRO_DISPATCH_MAPPING = ComponentMapping(
    source_table=PyPSATable.STORAGE_UNITS,
    carrier_col=PyPSAStorageUnitCol.CARRIER,
    fill_defaults=fill_hydro_defaults,
    enrich=_enrich_hydro,
    translations=HYDRO_DISPATCH_TRANSLATIONS,
    schema=HYDRO_DISPATCH_DESTINATION_SCHEMA,
    sienna_component=SiennaComponent.HYDRO_DISPATCH,
    time_series_attr=PyPSAStorageUnitCol.INFLOW,
    skip=_skip_without_inflow,
    derived_series=DerivedSeries(
        attribute=HYDRO_MAX_ACTIVE_POWER_ATTR,
        build=build_hydro_max_active_power_series,
    ),
    build_ts_association=build_hydro_ts_associations,
)
