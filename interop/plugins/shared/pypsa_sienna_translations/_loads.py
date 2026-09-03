"""Translation objects and helpers for PyPSA Load → Sienna PowerLoad.

map_components handles all load translation, including what was previously in
pypsa_to_sienna_process_time_series. The helpers below prepare the source table
and compute time-series metadata after translations complete.
"""

from __future__ import annotations

import uuid as _uuid
from functools import partial

import polars as pl

from interop.core.extensions import LoadExtension
from interop.plugins.shared.constants import (
    UNIT_DOLLARS_PER_MWH,
    UNIT_MVA,
    UNIT_MVAR,
    UNIT_MW,
    Framework,
)
from interop.plugins.shared.pypsa_constants import (
    PYPSA_COMPONENT_NAMING,
    PYPSA_LOAD_SIGN,
    PyPSAComponent,
    PyPSALoadCol,
    PyPSATable,
    PyPSATimeSeriesCol,
)
from interop.plugins.shared.pypsa_sienna_translations._shared import (
    NOT_AN_ELECTRICITY_BUS_NOTE,
    NOT_AN_ELECTRICITY_BUS_REASON,
    load_cost,
    pypsa_skip_report,
    pypsa_source_field,
    sienna_dest_field,
)
from interop.plugins.shared.pypsa_sienna_translations._ts_info import TimeSeriesInfo
from interop.plugins.shared.sienna_constants import (
    LOAD_CONFORMITY_DTYPE,
    SIENNA_TYPE_ATTRIBUTE,
    TIME_SERIES_ASSOCIATION_SCHEMA,
    LoadConformity,
    SiennaComponent,
    SiennaLoadCol,
    SiennaTimeSeriesAssociationCol,
    time_series_uuid,
)
from interop.plugins.shared.staged_samples import choose_reference_sample, filter_to_sample
from interop.plugins.shared.translation_runner import (
    DestinationFieldFactory,
    Translation,
    default_translation,
    direct_translation,
    row_position_id_translation,
)
from interop.ports.outbound.reporting import (
    EventKind,
    SourceField,
    TranslationEvent,
)


def load_in_scope(ac_bus_names: list[str]) -> pl.Expr:
    """A load is in scope when its bus is an electricity (AC) bus."""
    return pl.col(PyPSALoadCol.BUS).is_in(ac_bus_names)


LOAD_SKIP = pypsa_skip_report(
    component=PyPSAComponent.LOAD,
    name_col=PyPSALoadCol.NAME,
    counted_noun=PYPSA_COMPONENT_NAMING[PyPSATable.LOADS].plural,
    reason=NOT_AN_ELECTRICITY_BUS_REASON,
    note=NOT_AN_ELECTRICITY_BUS_NOTE,
)


# Translation-specific defaults
_MIN_BASE_POWER_MVA: float = 0.1
"""Floor applied to PowerLoad.base_power; ensures per-unit quantities stay near 1.0."""
_DEFAULT_LOAD_CONFORMITY: LoadConformity = LoadConformity.UNDEFINED

# Enrichment column names added by enrich_load_ts_stats; never written to destination table.
_TS_PEAK = "ts_peak"
_TS_FIRST = "ts_first"

# Enrichment column added by enrich_load_voll: the $/MWh a shortfall at this load's bus
# costs, or null where no bus record states one.
_VOLL = "value_of_lost_load"


def fill_load_defaults(table: pl.DataFrame) -> pl.DataFrame:
    """Add any PyPSA load columns omitted from NetCDF export and fill nulls/NaNs.

    PyPSA only writes non-default attribute values; p_set and q_set both default
    to 0.0 and may be absent.
    """
    if PyPSALoadCol.P_SET not in table.columns:
        table = table.with_columns(pl.lit(0.0).alias(PyPSALoadCol.P_SET))
    if PyPSALoadCol.Q_SET not in table.columns:
        table = table.with_columns(pl.lit(0.0).alias(PyPSALoadCol.Q_SET))
    return table.with_columns(
        [
            pl.col(PyPSALoadCol.P_SET).fill_null(0.0),
            pl.col(PyPSALoadCol.Q_SET).fill_null(0.0),
        ]
    )


def enrich_load_voll(table: pl.DataFrame, voll_by_bus: dict[str, float]) -> pl.DataFrame:
    """Add the price a shortfall costs at each load's bus, null where no bus states one.

    PyPSA has no field for the price, so it reaches this hop in the sidecar. A load with a
    price becomes an InterruptiblePowerLoad, which is the Sienna type a solve can cut.
    """
    return table.with_columns(
        pl.col(PyPSALoadCol.BUS)
        .replace_strict(voll_by_bus, default=None, return_dtype=pl.Float64)
        .alias(_VOLL)
    )


def load_is_interruptible() -> pl.Expr:
    """Whether a load's bus states a price for cutting it, which is what makes it cuttable."""
    return pl.col(_VOLL).is_not_null()


def enrich_load_ts_stats(
    table: pl.DataFrame,
    ts_p: pl.LazyFrame | None,
) -> pl.DataFrame:
    """Join per-load time-series stats onto the source table as regular columns.

    Adds ``ts_peak`` (max p_set) and ``ts_first`` (first p_set value) as Float64
    columns — null for any load without a time series. Both are component-scale
    aggregations and safe to collect.
    """
    if ts_p is None:
        return table.with_columns(
            [
                pl.lit(None, dtype=pl.Float64).alias(_TS_PEAK),
                pl.lit(None, dtype=pl.Float64).alias(_TS_FIRST),
            ]
        )
    stats = _peak_by_component(ts_p).join(
        _first_by_component(ts_p), on=PyPSATimeSeriesCol.COMPONENT, how="left"
    )
    return table.join(
        stats,
        left_on=PyPSALoadCol.NAME,
        right_on=PyPSATimeSeriesCol.COMPONENT,
        how="left",
    )


def _peak_by_component(ts_p: pl.LazyFrame) -> pl.DataFrame:
    """The highest value each load reaches, over every replication the frame holds.

    One peak for the whole ensemble is what makes every replication's stored shape read
    against the same base, so the numbers of two replications compare directly.
    """
    return (
        ts_p.group_by(PyPSATimeSeriesCol.COMPONENT)
        .agg(pl.col(PyPSATimeSeriesCol.VALUE).max().alias(_TS_PEAK))
        .collect()
    )


def _first_by_component(ts_p: pl.LazyFrame) -> pl.DataFrame:
    """Each load's value at the earliest snapshot, read from one replication.

    Every replication states a value at that snapshot, so without narrowing to one the
    answer is whichever row the frame happens to hold first.
    """
    return (
        filter_to_sample(ts_p, choose_reference_sample(ts_p))
        .group_by(PyPSATimeSeriesCol.COMPONENT)
        .agg(
            pl.col(PyPSATimeSeriesCol.VALUE)
            .sort_by(PyPSATimeSeriesCol.SNAPSHOT)
            .first()
            .alias(_TS_FIRST)
        )
        .collect()
    )


def build_load_ts_association(
    enriched_src: pl.DataFrame,
    dst: pl.DataFrame,
    ts_info: TimeSeriesInfo,
    component: SiennaComponent = SiennaComponent.POWER_LOAD,
) -> pl.DataFrame:
    """Build time_series_association rows for loads that have a p_set time series.

    The absolute MW p_set series is stored as a per-unit shape: ``scaling_factor`` carries
    the series peak (= max_active_power) as the divisor the h5 sink applies, and
    ``get_max_active_power`` is declared as the multiplier that reverses it on read.

    ``component`` is the Sienna type the rows belong to, because a series is looked up by
    its owner's type as well as its name.
    """
    with_ts = enriched_src.filter(pl.col(_TS_PEAK).is_not_null())
    names_with_ts = with_ts[PyPSALoadCol.NAME].to_list()
    if not names_with_ts:
        return pl.DataFrame(schema=TIME_SERIES_ASSOCIATION_SCHEMA)
    peak_by_name = dict(zip(names_with_ts, with_ts[_TS_PEAK].to_list(), strict=True))
    name_to_id = dict(
        zip(
            dst[SiennaLoadCol.NAME].to_list(),
            dst[SiennaLoadCol.ID].to_list(),
            strict=True,
        )
    )
    col = SiennaTimeSeriesAssociationCol
    rows = [
        {
            col.TIME_SERIES_UUID: time_series_uuid(component, name, SiennaLoadCol.MAX_ACTIVE_POWER),
            col.TIME_SERIES_TYPE: "SingleTimeSeries",
            col.INITIAL_TIMESTAMP: (
                ts_info.initial_timestamp.isoformat()
                if ts_info.initial_timestamp is not None
                else None
            ),
            col.RESOLUTION: ts_info.resolution,
            col.LENGTH: ts_info.length,
            col.NAME: SiennaLoadCol.MAX_ACTIVE_POWER,
            col.OWNER_ID: name_to_id[name],
            col.OWNER_TYPE: component,
            col.OWNER_CATEGORY: "Component",
            col.FEATURES: "[]",
            col.SCALING_FACTOR_MULTIPLIER: "PowerSystems.get_max_active_power",
            col.METADATA_UUID: str(_uuid.uuid4()),
            col.COMPONENT_NAME: name,
            col.SOURCE_TABLE: PyPSATable.LOADS,
            col.SOURCE_ATTRIBUTE: PyPSALoadCol.P_SET,
            # An all-zero series has peak 0.0; divide by 1.0 to keep the stored zeros.
            col.SCALING_FACTOR: peak_by_name[name] or 1.0,
        }
        for name in names_with_ts
    ]
    return pl.DataFrame(rows, schema=TIME_SERIES_ASSOCIATION_SCHEMA)


def build_load_extensions(
    enriched_src: pl.DataFrame,
    dst: pl.DataFrame,
) -> list[LoadExtension]:
    """Build extension records for all translated loads.

    Every load produces a record with its direct PyPSA Load fields that have no
    Sienna home: ``carrier``, ``type``, and ``sign`` (always −1 in PyPSA).
    """
    name_to_src = {row[PyPSALoadCol.NAME]: row for row in enriched_src.iter_rows(named=True)}
    records = [
        LoadExtension(
            name=name,
            carrier=name_to_src[name].get(PyPSALoadCol.CARRIER, ""),
            type=name_to_src[name].get(PyPSALoadCol.TYPE, ""),
            sign=PYPSA_LOAD_SIGN,
        )
        for name in dst[SiennaLoadCol.NAME].to_list()
    ]
    return records


# --- Translation constants ---
# Every field a load fills, whatever Sienna type it becomes. The Sienna component is a
# parameter because an interruptible load fills the same fields as a plain one, and each
# report must name the type the pipeline actually wrote.

_ID_NOTE = "assigned by 1-based row position in loads DataFrame"
_AVAILABLE_NOTE = "PyPSA Load has no active input field; always True"
_BUS_NAME_NOTE = "bus string name; FK resolution to ACBus deferred"
_Q_SET_NOTE = "time-varying q_set deferred"
_CONFORMITY_NOTE = "PyPSA Load has no conformity concept"
_BASE_POWER_DERIVATION = f"max(max_active_power, {_MIN_BASE_POWER_MVA}) MVA"
_OPERATION_COST_DERIVATION = (
    "the value of lost load its bus carries becomes the LoadCost variable cost curve, so "
    "cutting this load costs that much per MWh"
)

_source = partial(pypsa_source_field, PyPSAComponent.LOAD)
_bus_source = partial(pypsa_source_field, PyPSAComponent.BUS)


def _load_translations(component: SiennaComponent) -> list[Translation]:
    """Every field a load fills from the source table alone."""
    dest = partial(sienna_dest_field, component)
    direct = partial(direct_translation, _source, dest, name_col=PyPSALoadCol.NAME)
    default = partial(default_translation, dest, name_col=PyPSALoadCol.NAME)
    return [
        row_position_id_translation(
            dest, dest_name_col=SiennaLoadCol.NAME, id_col=SiennaLoadCol.ID, note=_ID_NOTE
        ),
        direct(source_col=PyPSALoadCol.NAME, dest_col=SiennaLoadCol.NAME),
        default(dest_col=SiennaLoadCol.AVAILABLE, value=True, note=_AVAILABLE_NOTE),
        direct(source_col=PyPSALoadCol.BUS, dest_col=SiennaLoadCol.BUS_NAME, note=_BUS_NAME_NOTE),
        _load_sienna_type(dest, component),
        _load_active_power(dest),
        _load_max_active_power(dest),
        direct(
            source_col=PyPSALoadCol.Q_SET,
            dest_col=SiennaLoadCol.REACTIVE_POWER,
            unit=UNIT_MVAR,
            note=_Q_SET_NOTE,
        ),
        direct(
            source_col=PyPSALoadCol.Q_SET,
            dest_col=SiennaLoadCol.MAX_REACTIVE_POWER,
            unit=UNIT_MVAR,
            note=_Q_SET_NOTE,
        ),
        default(
            dest_col=SiennaLoadCol.CONFORMITY,
            value=_DEFAULT_LOAD_CONFORMITY,
            note=_CONFORMITY_NOTE,
            dtype=LOAD_CONFORMITY_DTYPE,
        ),
    ]


def _load_sienna_type(dest: DestinationFieldFactory, component: SiennaComponent) -> Translation:
    """The Sienna type a PyPSA Load becomes, which has no destination column of its own."""
    return Translation(
        exprs=[],
        make_events=lambda old, _: [
            TranslationEvent(
                kind=EventKind.VALUE_DERIVED,
                sources=[_source(old[PyPSALoadCol.NAME])],
                destinations=[dest(old[PyPSALoadCol.NAME], SIENNA_TYPE_ATTRIBUTE, component)],
                derivation=f"PyPSA Load -> {component}",
            )
        ],
    )


def _load_active_power(dest: DestinationFieldFactory) -> Translation:
    """The starting operating point, which a time-varying p_set takes from its first snapshot."""
    return Translation(
        exprs=[
            pl.when(pl.col(_TS_FIRST).is_not_null())
            .then(pl.col(_TS_FIRST))
            .otherwise(pl.col(PyPSALoadCol.P_SET))
            .alias(SiennaLoadCol.ACTIVE_POWER)
        ],
        make_events=lambda old, new: [
            TranslationEvent(
                kind=EventKind.VALUE_DERIVED,
                sources=[
                    _source(
                        old[PyPSALoadCol.NAME],
                        PyPSALoadCol.P_SET,
                        float(old[PyPSALoadCol.P_SET] or 0.0),
                        UNIT_MW,
                    )
                ],
                destinations=[
                    dest(
                        old[PyPSALoadCol.NAME],
                        SiennaLoadCol.ACTIVE_POWER,
                        new[SiennaLoadCol.ACTIVE_POWER],
                        UNIT_MW,
                    )
                ],
                derivation=(
                    "p_set static value; time-varying p_set uses first timestep"
                    if old[_TS_FIRST] is not None
                    else "direct"
                ),
            )
        ],
    )


def _load_max_active_power(dest: DestinationFieldFactory) -> Translation:
    """The ceiling, which is the peak of a time-varying p_set where the load carries one."""
    return Translation(
        exprs=[
            pl.when(pl.col(_TS_PEAK).is_not_null())
            .then(pl.col(_TS_PEAK))
            .otherwise(pl.col(PyPSALoadCol.P_SET))
            .alias(SiennaLoadCol.MAX_ACTIVE_POWER)
        ],
        make_events=lambda old, new: [
            TranslationEvent(
                kind=EventKind.VALUE_DERIVED,
                sources=[
                    _source(
                        old[PyPSALoadCol.NAME],
                        (
                            f"{PyPSATable.LOADS}_t.{PyPSALoadCol.P_SET}"
                            if old[_TS_PEAK] is not None
                            else PyPSALoadCol.P_SET
                        ),
                        (
                            None
                            if old[_TS_PEAK] is not None
                            else float(old[PyPSALoadCol.P_SET] or 0.0)
                        ),
                        None if old[_TS_PEAK] is not None else UNIT_MW,
                    )
                ],
                destinations=[
                    dest(
                        old[PyPSALoadCol.NAME],
                        SiennaLoadCol.MAX_ACTIVE_POWER,
                        new[SiennaLoadCol.MAX_ACTIVE_POWER],
                        UNIT_MW,
                    )
                ],
                derivation=(
                    "peak of n.loads_t.p_set time series"
                    if old[_TS_PEAK] is not None
                    else "n.loads.p_set static value; no time series present"
                ),
            )
        ],
    )


def _load_base_power(component: SiennaComponent) -> Translation:
    """The MVA base, which reads the max_active_power Phase 1 wrote rather than a source column."""
    dest = partial(sienna_dest_field, component)
    return Translation(
        exprs=[
            pl.max_horizontal(
                pl.col(SiennaLoadCol.MAX_ACTIVE_POWER),
                pl.lit(_MIN_BASE_POWER_MVA),
            ).alias(SiennaLoadCol.BASE_POWER)
        ],
        make_events=lambda old, new: [
            TranslationEvent(
                kind=EventKind.VALUE_DERIVED,
                sources=[
                    SourceField(
                        framework=Framework.SIENNA,
                        component=component,
                        name=old[SiennaLoadCol.NAME],
                        attribute=SiennaLoadCol.MAX_ACTIVE_POWER,
                        value=old[SiennaLoadCol.MAX_ACTIVE_POWER],
                        unit=UNIT_MW,
                    )
                ],
                destinations=[
                    dest(
                        old[SiennaLoadCol.NAME],
                        SiennaLoadCol.BASE_POWER,
                        new[SiennaLoadCol.BASE_POWER],
                        UNIT_MVA,
                    )
                ],
                derivation=_BASE_POWER_DERIVATION,
            )
        ],
    )


def _load_operation_cost() -> Translation:
    """The price the solve pays for the load it serves, which only an interruptible load has."""
    dest = partial(sienna_dest_field, SiennaComponent.INTERRUPTIBLE_POWER_LOAD)
    return Translation(
        exprs=[load_cost(pl.col(_VOLL)).alias(SiennaLoadCol.OPERATION_COST)],
        make_events=lambda old, new: [
            TranslationEvent(
                kind=EventKind.VALUE_DERIVED,
                sources=[
                    _bus_source(old[PyPSALoadCol.BUS], _VOLL, old[_VOLL], UNIT_DOLLARS_PER_MWH)
                ],
                destinations=[
                    dest(
                        old[PyPSALoadCol.NAME],
                        f"{SiennaLoadCol.OPERATION_COST}"
                        ".variable.value_curve.function_data.proportional_term",
                        old[_VOLL],
                        UNIT_DOLLARS_PER_MWH,
                    )
                ],
                derivation=_OPERATION_COST_DERIVATION,
            )
        ],
    )


# base_power depends on max_active_power from Phase 1
LOAD_TRANSLATIONS_PHASE_1: list[Translation] = _load_translations(SiennaComponent.POWER_LOAD)
LOAD_TRANSLATIONS_PHASE_2: list[Translation] = [_load_base_power(SiennaComponent.POWER_LOAD)]

INTERRUPTIBLE_LOAD_TRANSLATIONS_PHASE_1: list[Translation] = _load_translations(
    SiennaComponent.INTERRUPTIBLE_POWER_LOAD
)
INTERRUPTIBLE_LOAD_TRANSLATIONS_PHASE_2: list[Translation] = [
    _load_base_power(SiennaComponent.INTERRUPTIBLE_POWER_LOAD),
    _load_operation_cost(),
]
