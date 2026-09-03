"""Translation objects and helpers for PyPSA Generator -> Sienna RenewableDispatch.

Only generators whose carrier is mapped to RenewableDispatch / RenewableNonDispatch in the
user carrier mapping are translated here. The carrier's prime_mover comes from that mapping.
RenewableDispatch is curtailable: it has no active_power_limits, ramp_limits, must_run,
status, or fuel_type. Its ceiling is the static rating (p_max_pu) unless p_max_pu is
time-varying, in which case a max_active_power time series carries the per-unit shape
unchanged (the formulation multiplies it by rating * base_power at solve time, so the
translator must not pre-multiply by p_nom). A flat per-unit profile is skipped.
"""

from __future__ import annotations

from functools import partial

import polars as pl

from interop.core.extensions import ExtensionKind, GeneratorExtension
from interop.plugins.shared.constants import UNIT_MW
from interop.plugins.shared.pypsa_constants import (
    PyPSAComponent,
    PyPSAGeneratorCol,
    PyPSATable,
    PyPSATimeSeriesCol,
)
from interop.plugins.shared.pypsa_sienna_translations._component_mapping import (
    ComponentMapping,
    ExtensionSpec,
)
from interop.plugins.shared.pypsa_sienna_translations._prime_mover import enrich_prime_mover
from interop.plugins.shared.pypsa_sienna_translations._shared import (
    pypsa_source_field,
    sienna_dest_field,
    ts_association_row,
    variable_cost_curve,
)
from interop.plugins.shared.pypsa_sienna_translations._ts_info import TimeSeriesInfo
from interop.plugins.shared.pypsa_sienna_user_mappings import CarrierMappings
from interop.plugins.shared.sienna_constants import (
    FLAT_TIME_SERIES_EPSILON,
    PRIME_MOVERS_DTYPE,
    REACTIVE_POWER_LIMITS_DTYPE,
    RENEWABLE_DISPATCH_DESTINATION_SCHEMA,
    RENEWABLE_GENERATION_COST_DTYPE,
    RENEWABLE_NON_DISPATCH_DESTINATION_SCHEMA,
    SIENNA_TYPE_ATTRIBUTE,
    TIME_SERIES_ASSOCIATION_SCHEMA,
    SiennaComponent,
    SiennaCostType,
    SiennaPrimeMovers,
    SiennaRenewableGeneratorCol,
    SiennaSeriesName,
)
from interop.plugins.shared.translation_runner import (
    DestinationFieldFactory,
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

# Enrichment column names added before translations; never written to destination table.
_PRIME_MOVER_COL = "_prime_mover_raw"
_TS_PTP = "_ts_ptp_pmax"
_EFFECTIVE_P_NOM = "_effective_p_nom"


_source = partial(pypsa_source_field, PyPSAComponent.GENERATOR)
_dest = partial(sienna_dest_field, SiennaComponent.RENEWABLE_DISPATCH)
_dest_nd = partial(sienna_dest_field, SiennaComponent.RENEWABLE_NON_DISPATCH)


def fill_renewable_defaults(table: pl.DataFrame) -> pl.DataFrame:
    """Add PyPSA generator columns absent when all generators share the PyPSA default."""
    table = fill_defaults(
        table,
        [
            (PyPSAGeneratorCol.P_NOM, 0.0),
            (PyPSAGeneratorCol.P_NOM_OPT, 0.0),
            (PyPSAGeneratorCol.P_MIN_PU, 0.0),
            (PyPSAGeneratorCol.P_MAX_PU, 1.0),
            (PyPSAGeneratorCol.MARGINAL_COST, 0.0),
        ],
        [(PyPSAGeneratorCol.P_NOM_EXTENDABLE, False)],
    )
    return table.with_columns(
        pl.when(pl.col(PyPSAGeneratorCol.P_NOM_EXTENDABLE))
        .then(pl.col(PyPSAGeneratorCol.P_NOM_OPT))
        .otherwise(pl.col(PyPSAGeneratorCol.P_NOM))
        .alias(_EFFECTIVE_P_NOM)
    )


def build_renewable_extensions(
    enriched_src: pl.DataFrame, dst: pl.DataFrame
) -> list[GeneratorExtension]:
    """Build extension records with each renewable's ``carrier`` and ``p_nom_extendable``.

    ``carrier`` is kept so carriers that share a prime mover (e.g. offwind-ac and offwind-dc,
    both WS) round-trip exactly rather than collapsing to the reverse map's canonical carrier;
    ``p_nom_extendable`` has no SiennaSchemas home.
    """
    name_to_src = {row[PyPSAGeneratorCol.NAME]: row for row in enriched_src.iter_rows(named=True)}
    records = [
        GeneratorExtension(
            name=name,
            carrier=name_to_src[name][PyPSAGeneratorCol.CARRIER],
            p_nom_extendable=name_to_src[name][PyPSAGeneratorCol.P_NOM_EXTENDABLE],
        )
        for name in dst[SiennaRenewableGeneratorCol.NAME].to_list()
    ]
    return records


def enrich_renewable_carrier(
    table: pl.DataFrame, prime_mover_map: dict[str, SiennaPrimeMovers]
) -> pl.DataFrame:
    """Pre-compute the prime_mover enrichment column from the user carrier mapping."""
    return enrich_prime_mover(table, PyPSAGeneratorCol.CARRIER, _PRIME_MOVER_COL, prime_mover_map)


def enrich_renewable_ts_stats(
    table: pl.DataFrame,
    ts_p_max_pu: pl.LazyFrame | None,
) -> pl.DataFrame:
    """Left-join the peak-to-trough range of each generator's p_max_pu series.

    Adds ``_ts_ptp_pmax`` (max - min) as Float64 — null for any generator without a
    series. Component-scale aggregation; safe to collect.
    """
    if ts_p_max_pu is not None:
        stats = (
            ts_p_max_pu.group_by(PyPSATimeSeriesCol.COMPONENT)
            .agg(
                (
                    pl.col(PyPSATimeSeriesCol.VALUE).max() - pl.col(PyPSATimeSeriesCol.VALUE).min()
                ).alias(_TS_PTP)
            )
            .collect()
        )
        return table.join(
            stats,
            left_on=PyPSAGeneratorCol.NAME,
            right_on=PyPSATimeSeriesCol.COMPONENT,
            how="left",
        )
    return table.with_columns(pl.lit(None, dtype=pl.Float64).alias(_TS_PTP))


def build_renewable_ts_association(
    enriched_src: pl.DataFrame,
    dst: pl.DataFrame,
    ts_info: TimeSeriesInfo,
    owner_type: str,
) -> pl.DataFrame:
    """Build max_active_power time_series_association rows for non-flat p_max_pu series.

    ``owner_type`` is the Sienna component (RenewableDispatch or RenewableNonDispatch) the
    series attaches to. The series is stored unchanged in per-unit of base_power
    (scaling_factor 1.0); the declared ``get_max_active_power`` multiplier
    (rating * base_power) reconstructs the absolute MW availability at solve time. Flat or
    absent profiles emit no row.
    """
    varying = enriched_src.filter(pl.col(_TS_PTP) > FLAT_TIME_SERIES_EPSILON)
    names_with_ts = varying[PyPSAGeneratorCol.NAME].to_list()
    if not names_with_ts:
        return pl.DataFrame(schema=TIME_SERIES_ASSOCIATION_SCHEMA)
    name_to_id = dict(
        zip(
            dst[SiennaRenewableGeneratorCol.NAME].to_list(),
            dst[SiennaRenewableGeneratorCol.ID].to_list(),
            strict=True,
        )
    )
    rows = [
        ts_association_row(
            owner_type=owner_type,
            owner_id=name_to_id[name],
            component_name=name,
            series_name=SiennaSeriesName.MAX_ACTIVE_POWER,
            ts_info=ts_info,
            source_table=PyPSATable.GENERATORS,
            source_attribute=PyPSAGeneratorCol.P_MAX_PU,
            # Stored unchanged in per-unit of base_power: divide by 1.0.
            scaling_factor=1.0,
        )
        for name in names_with_ts
    ]
    return pl.DataFrame(rows, schema=TIME_SERIES_ASSOCIATION_SCHEMA)


# --- Translation constants ---

R = SiennaRenewableGeneratorCol


def _sienna_type(
    dest: DestinationFieldFactory, sienna_component: str, derivation: str
) -> Translation:
    """The carrier -> Sienna renewable type event (no destination column of its own)."""
    return Translation(
        exprs=[],
        make_events=lambda old, _: [
            TranslationEvent(
                kind=EventKind.VALUE_DERIVED,
                sources=[
                    _source(
                        old[PyPSAGeneratorCol.NAME],
                        PyPSAGeneratorCol.CARRIER,
                        old[PyPSAGeneratorCol.CARRIER],
                    )
                ],
                destinations=[
                    dest(old[PyPSAGeneratorCol.NAME], SIENNA_TYPE_ATTRIBUTE, sienna_component)
                ],
                derivation=derivation,
            )
        ],
    )


def _renewable_translations(
    dest: DestinationFieldFactory,
    *,
    sienna_component: str,
    id_note: str,
    sienna_type_derivation: str,
    active_power_expr: pl.Expr,
    active_power_derivation: str,
    tail: list[Translation],
) -> list[Translation]:
    """Shared RenewableDispatch / RenewableNonDispatch translation list.

    The two Sienna renewable types share the same destination schema and differ only in the
    destination component (``dest`` / ``sienna_component``), the initial-dispatch operating point
    (``active_power_expr``), and the trailing cost / reactive-power handling (``tail``).
    """
    direct = partial(direct_translation, _source, dest, name_col=PyPSAGeneratorCol.NAME)
    default = partial(default_translation, dest, name_col=PyPSAGeneratorCol.NAME)
    return [
        row_position_id_translation(dest, dest_name_col=R.NAME, id_col=R.ID, note=id_note),
        direct(source_col=PyPSAGeneratorCol.NAME, dest_col=R.NAME),
        default(
            dest_col=R.AVAILABLE,
            value=True,
            note="PyPSA Generator has no active field; defaulted to True",
        ),
        direct(source_col=PyPSAGeneratorCol.BUS, dest_col=R.BUS_NAME),
        _sienna_type(dest, sienna_component, sienna_type_derivation),
        direct(
            source_col=PyPSAGeneratorCol.CARRIER,
            dest_col=R.PRIME_MOVER_TYPE,
            expr=pl.col(_PRIME_MOVER_COL).cast(PRIME_MOVERS_DTYPE),
            derivation="carrier -> PrimeMovers via user defined mapping",
        ),
        direct(
            source_col=PyPSAGeneratorCol.P_NOM,
            dest_col=R.BASE_POWER,
            expr=pl.col(_EFFECTIVE_P_NOM),
            unit=UNIT_MW,
            derivation="p_nom_opt when p_nom_extendable else p_nom",
        ),
        direct(
            source_col=PyPSAGeneratorCol.P_NOM,
            dest_col=R.ACTIVE_POWER,
            expr=active_power_expr,
            unit=UNIT_MW,
            derivation=active_power_derivation,
        ),
        default(
            dest_col=R.REACTIVE_POWER,
            value=0.0,
            note="PyPSA networks rarely model reactive power for generators",
        ),
        direct(
            source_col=PyPSAGeneratorCol.P_MAX_PU,
            dest_col=R.RATING,
            derivation="p_max_pu (per-unit nameplate rating; typically 1.0)",
        ),
        default(
            dest_col=R.POWER_FACTOR,
            value=1.0,
            note="PyPSA generator schema has no scalar power factor; defaulted to 1.0",
        ),
        *tail,
    ]


def _renewable_reactive_power_limits(dest: DestinationFieldFactory) -> Translation:
    return default_translation(
        dest,
        name_col=PyPSAGeneratorCol.NAME,
        dest_col=R.REACTIVE_POWER_LIMITS,
        value=None,
        note="PyPSA does not model reactive power limits for generators in v1",
        dtype=REACTIVE_POWER_LIMITS_DTYPE,
    )


def _renewable_cost(dest: DestinationFieldFactory) -> Translation:
    return Translation(
        exprs=[
            pl.struct(
                cost_type=pl.lit(SiennaCostType.RENEWABLE),
                variable=variable_cost_curve(pl.col(PyPSAGeneratorCol.MARGINAL_COST)),
                fixed=pl.lit(0.0),
            )
            .cast(RENEWABLE_GENERATION_COST_DTYPE)
            .alias(R.OPERATION_COST)
        ],
        make_events=lambda old, _: [
            TranslationEvent(
                kind=EventKind.VALUE_DERIVED,
                sources=[
                    _source(
                        old[PyPSAGeneratorCol.NAME],
                        PyPSAGeneratorCol.MARGINAL_COST,
                        old[PyPSAGeneratorCol.MARGINAL_COST],
                    )
                ],
                destinations=[
                    dest(
                        old[PyPSAGeneratorCol.NAME],
                        f"{R.OPERATION_COST}.variable.value_curve.function_data.proportional_term",
                        old[PyPSAGeneratorCol.MARGINAL_COST],
                    )
                ],
                derivation="flat marginal_cost ($/MWh) -> single-segment linear CostCurve",
            )
        ],
    )


def _renewable_cost_loss(dest: DestinationFieldFactory) -> Translation:
    """RenewableNonDispatch has no operation_cost field; record dropped non-zero marginal_cost."""
    return Translation(
        exprs=[],
        make_events=lambda old, _: (
            [
                TranslationEvent(
                    kind=EventKind.NOT_MAPPED,
                    sources=[
                        _source(
                            old[PyPSAGeneratorCol.NAME],
                            PyPSAGeneratorCol.MARGINAL_COST,
                            old[PyPSAGeneratorCol.MARGINAL_COST],
                        )
                    ],
                    note=(
                        "RenewableNonDispatch has no operation_cost field; "
                        "non-zero marginal_cost dropped (information lost)"
                    ),
                )
            ]
            if old[PyPSAGeneratorCol.MARGINAL_COST] != 0
            else []
        ),
    )


RENEWABLE_DISPATCH_TRANSLATIONS: list[Translation] = _renewable_translations(
    _dest,
    sienna_component=SiennaComponent.RENEWABLE_DISPATCH,
    id_note="assigned by 1-based row position in renewable generators DataFrame",
    sienna_type_derivation="renewable carrier -> RenewableDispatch",
    active_power_expr=pl.col(_EFFECTIVE_P_NOM) * pl.col(PyPSAGeneratorCol.P_MIN_PU),
    active_power_derivation="effective_p_nom * p_min_pu (initial dispatch = min operating point)",
    tail=[_renewable_reactive_power_limits(_dest), _renewable_cost(_dest)],
)

RENEWABLE_NON_DISPATCH_TRANSLATIONS: list[Translation] = _renewable_translations(
    _dest_nd,
    sienna_component=SiennaComponent.RENEWABLE_NON_DISPATCH,
    id_note="assigned by 1-based row position in renewable non-dispatch generators DataFrame",
    sienna_type_derivation="renewable carrier -> RenewableNonDispatch",
    active_power_expr=pl.col(_EFFECTIVE_P_NOM) * pl.col(PyPSAGeneratorCol.P_MAX_PU),
    active_power_derivation=(
        "effective_p_nom * p_max_pu (must-take initial dispatch = peak available)"
    ),
    tail=[_renewable_cost_loss(_dest_nd)],
)


def _enrich_renewable(
    table: pl.DataFrame,
    ts: pl.LazyFrame | None,
    _ts_info: TimeSeriesInfo,
    mappings: CarrierMappings,
) -> pl.DataFrame:
    return enrich_renewable_ts_stats(
        enrich_renewable_carrier(table, mappings.get_prime_mover_map()), ts
    )


RENEWABLE_DISPATCH_MAPPING = ComponentMapping(
    source_table=PyPSATable.GENERATORS,
    carrier_col=PyPSAGeneratorCol.CARRIER,
    fill_defaults=fill_renewable_defaults,
    enrich=_enrich_renewable,
    translations=RENEWABLE_DISPATCH_TRANSLATIONS,
    schema=RENEWABLE_DISPATCH_DESTINATION_SCHEMA,
    sienna_component=SiennaComponent.RENEWABLE_DISPATCH,
    time_series_attr=PyPSAGeneratorCol.P_MAX_PU,
    build_ts_association=partial(
        build_renewable_ts_association, owner_type=SiennaComponent.RENEWABLE_DISPATCH
    ),
    extensions=ExtensionSpec(ExtensionKind.GENERATOR, build_renewable_extensions),
)

RENEWABLE_NON_DISPATCH_MAPPING = ComponentMapping(
    source_table=PyPSATable.GENERATORS,
    carrier_col=PyPSAGeneratorCol.CARRIER,
    fill_defaults=fill_renewable_defaults,
    enrich=_enrich_renewable,
    translations=RENEWABLE_NON_DISPATCH_TRANSLATIONS,
    schema=RENEWABLE_NON_DISPATCH_DESTINATION_SCHEMA,
    sienna_component=SiennaComponent.RENEWABLE_NON_DISPATCH,
    time_series_attr=PyPSAGeneratorCol.P_MAX_PU,
    build_ts_association=partial(
        build_renewable_ts_association, owner_type=SiennaComponent.RENEWABLE_NON_DISPATCH
    ),
    extensions=ExtensionSpec(ExtensionKind.GENERATOR, build_renewable_extensions),
)
