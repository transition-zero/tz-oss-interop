"""Translation objects and helpers for PyPSA Generator -> Sienna ThermalStandard.

Only generators whose carrier appears in the user-supplied carrier mapping YAML file are
translated. A generator whose carrier the file does not name is left out and recorded.
"""

from __future__ import annotations

from functools import partial
from typing import Any

import polars as pl

from interop.core.extensions import ExtensionKind, GeneratorExtension
from interop.plugins.shared.constants import UNIT_MW, Framework
from interop.plugins.shared.pypsa_constants import (
    PYPSA_COMPONENT_NAMING,
    PyPSACarrier,
    PyPSAComponent,
    PyPSAComponentCol,
    PyPSAGeneratorCol,
    PyPSATable,
    PyPSATimeSeriesCol,
)
from interop.plugins.shared.pypsa_sienna_translations._component_mapping import (
    ComponentMapping,
    ExtensionSpec,
)
from interop.plugins.shared.pypsa_sienna_translations._shared import (
    pypsa_skip_report,
    pypsa_source_field,
    sienna_dest_field,
    ts_association_row,
    variable_cost_curve,
)
from interop.plugins.shared.pypsa_sienna_translations._ts_info import TimeSeriesInfo
from interop.plugins.shared.pypsa_sienna_user_mappings import CarrierMappings
from interop.plugins.shared.sienna_constants import (
    ACTIVE_POWER_LIMITS_DTYPE,
    PRIME_MOVERS_DTYPE,
    RAMP_LIMITS_DTYPE,
    REACTIVE_POWER_LIMITS_DTYPE,
    SIENNA_TYPE_ATTRIBUTE,
    THERMAL_FUELS_DTYPE,
    THERMAL_GENERATION_COST_DTYPE,
    THERMAL_GENERATORS_DESTINATION_SCHEMA,
    TIME_LIMITS_DTYPE,
    TIME_SERIES_ASSOCIATION_SCHEMA,
    SiennaComponent,
    SiennaCostType,
    SiennaSeriesName,
    SiennaThermalGeneratorCol,
)
from interop.plugins.shared.translation_runner import (
    Translation,
    default_translation,
    direct_translation,
    fill_defaults,
    row_position_id_translation,
)
from interop.ports.outbound.reporting import (
    DestinationField,
    EventKind,
    SourceField,
    TranslationEvent,
)

# Enrichment column names added before translations; never written to destination table.
_FUEL_TYPE_COL = "_fuel_type_raw"
_PRIME_MOVER_COL = "_prime_mover_raw"
_TS_PEAK_PMAX = "_ts_peak_pmax"
_DT_MINUTES_COL = "_dt_minutes"
_EFFECTIVE_P_NOM = "_effective_p_nom"


def fill_generator_defaults(table: pl.DataFrame) -> pl.DataFrame:
    """Add PyPSA generator columns absent when all generators share the PyPSA default."""
    table = fill_defaults(
        table,
        [
            (PyPSAGeneratorCol.P_NOM, 0.0),
            (PyPSAGeneratorCol.P_NOM_OPT, 0.0),
            (PyPSAGeneratorCol.P_MIN_PU, 0.0),
            (PyPSAGeneratorCol.P_MAX_PU, 1.0),
            (PyPSAGeneratorCol.MARGINAL_COST, 0.0),
            (PyPSAGeneratorCol.RAMP_LIMIT_UP, None),
            (PyPSAGeneratorCol.RAMP_LIMIT_DOWN, None),
            (PyPSAGeneratorCol.MIN_UP_TIME, 0.0),
            (PyPSAGeneratorCol.MIN_DOWN_TIME, 0.0),
            (PyPSAGeneratorCol.UP_TIME_BEFORE, 0.0),
            (PyPSAGeneratorCol.START_UP_COST, 0.0),
            (PyPSAGeneratorCol.SHUT_DOWN_COST, 0.0),
        ],
        [
            (PyPSAGeneratorCol.COMMITTABLE, False),
            (PyPSAGeneratorCol.P_NOM_EXTENDABLE, False),
        ],
    )
    return table.with_columns(
        pl.when(pl.col(PyPSAGeneratorCol.P_NOM_EXTENDABLE))
        .then(pl.col(PyPSAGeneratorCol.P_NOM_OPT))
        .otherwise(pl.col(PyPSAGeneratorCol.P_NOM))
        .alias(_EFFECTIVE_P_NOM)
    )


def enrich_carrier_lookup(
    table: pl.DataFrame,
    mappings: CarrierMappings,
) -> pl.DataFrame:
    """Pre-compute fuel_type and prime_mover enrichment columns from the carrier map.

    These are dropped by finalise(); they exist only to allow single-column Translation
    exprs for GENERATOR_FUEL_TYPE and GENERATOR_PRIME_MOVER.
    """
    carrier_map = mappings.get_thermal_carrier_map()
    fuel_map = {c: v[0] for c, v in carrier_map.items()}
    mover_map = {c: v[1] for c, v in carrier_map.items()}
    return table.with_columns(
        [
            pl.col(PyPSAGeneratorCol.CARRIER).replace(fuel_map).alias(_FUEL_TYPE_COL),
            pl.col(PyPSAGeneratorCol.CARRIER).replace(mover_map).alias(_PRIME_MOVER_COL),
        ]
    )


def enrich_generator_ts_stats(
    table: pl.DataFrame,
    ts_p_max_pu: pl.LazyFrame | None,
) -> pl.DataFrame:
    """Left-join peak p_max_pu per generator for time-series detection and capacity calc.

    Adds ``_ts_peak_pmax`` (max p_max_pu value) as a Float64 column — null for any
    generator without a time series. Component-scale aggregation; safe to collect.
    """
    if ts_p_max_pu is not None:
        stats = (
            ts_p_max_pu.group_by(PyPSATimeSeriesCol.COMPONENT)
            .agg(pl.col(PyPSATimeSeriesCol.VALUE).max().alias(_TS_PEAK_PMAX))
            .collect()
        )
        return table.join(
            stats,
            left_on=PyPSAGeneratorCol.NAME,
            right_on=PyPSATimeSeriesCol.COMPONENT,
            how="left",
        )
    return table.with_columns(pl.lit(None, dtype=pl.Float64).alias(_TS_PEAK_PMAX))


def enrich_snapshot_duration(table: pl.DataFrame, dt_minutes: float) -> pl.DataFrame:
    """Add snapshot duration column used by ramp rate calculations."""
    return table.with_columns(pl.lit(dt_minutes).alias(_DT_MINUTES_COL))


# A generator this translator wrote itself on an earlier hop, which this hop must not read
# back as a power plant. It is not a carrier a mappings file would name, so it needs a report
# of its own rather than falling through to the unnamed-carrier drop.
GENERATOR_LOAD_SHEDDING_SKIP = pypsa_skip_report(
    component=PYPSA_COMPONENT_NAMING[PyPSATable.GENERATORS].display,
    name_col=PyPSAComponentCol.NAME,
    counted_noun=PYPSA_COMPONENT_NAMING[PyPSATable.GENERATORS].plural,
    reason="are load shedding generators, which Sienna prices on the load instead",
    note=(
        f"carrier={PyPSACarrier.LOAD_SHEDDING.value!r}: Sienna sheds load through an "
        "InterruptiblePowerLoad, so translating this as a generator would shed twice"
    ),
)


def build_generator_ts_association(
    enriched_src: pl.DataFrame,
    dst: pl.DataFrame,
    ts_info: TimeSeriesInfo,
) -> pl.DataFrame:
    """Build time_series_association rows for generators that have a p_max_pu time series.

    The series name is ``max_active_power``, which is the name PowerSimulations reads an
    availability forecast under. The p_max_pu series is stored as a peak-1.0 shape:
    ``scaling_factor`` carries the series peak as the divisor the h5 sink applies.
    ``get_max_active_power`` (declared as the multiplier) returns
    ``active_power_limits.max`` = p_nom * peak, so reading the shape back reconstructs the
    absolute MW availability p_max_pu * p_nom.
    """
    with_ts = enriched_src.filter(pl.col(_TS_PEAK_PMAX).is_not_null())
    names_with_ts = with_ts[PyPSAGeneratorCol.NAME].to_list()
    if not names_with_ts:
        return pl.DataFrame(schema=TIME_SERIES_ASSOCIATION_SCHEMA)
    peak_by_name = dict(zip(names_with_ts, with_ts[_TS_PEAK_PMAX].to_list(), strict=True))
    name_to_id = dict(
        zip(
            dst[SiennaThermalGeneratorCol.NAME].to_list(),
            dst[SiennaThermalGeneratorCol.ID].to_list(),
            strict=True,
        )
    )
    rows = [
        ts_association_row(
            owner_type=SiennaComponent.THERMAL_STANDARD,
            owner_id=name_to_id[name],
            component_name=name,
            series_name=SiennaSeriesName.MAX_ACTIVE_POWER,
            ts_info=ts_info,
            source_table=PyPSATable.GENERATORS,
            source_attribute=PyPSAGeneratorCol.P_MAX_PU,
            # An all-zero series has peak 0.0; divide by 1.0 to keep the stored zeros.
            scaling_factor=peak_by_name[name] or 1.0,
        )
        for name in names_with_ts
    ]
    return pl.DataFrame(rows, schema=TIME_SERIES_ASSOCIATION_SCHEMA)


def build_generator_extensions(
    enriched_src: pl.DataFrame,
    dst: pl.DataFrame,
) -> list[GeneratorExtension]:
    """Build extension records for every translated thermal generator.

    Records each generator's PyPSA ``carrier``, ``committable``, and ``p_nom_extendable``.
    ``carrier`` is kept so carriers that share a (prime_mover, fuel) pair (e.g. coal and
    lignite) round-trip exactly rather than collapsing to the reverse map's canonical carrier;
    ``committable``/``p_nom_extendable`` have no SiennaSchemas home and the translation makes
    no decision on them.
    """
    name_to_src = {row[PyPSAGeneratorCol.NAME]: row for row in enriched_src.iter_rows(named=True)}
    records = [
        GeneratorExtension(
            name=name,
            carrier=name_to_src[name][PyPSAGeneratorCol.CARRIER],
            committable=name_to_src[name][PyPSAGeneratorCol.COMMITTABLE],
            p_nom_extendable=name_to_src[name][PyPSAGeneratorCol.P_NOM_EXTENDABLE],
        )
        for name in dst[SiennaThermalGeneratorCol.NAME].to_list()
    ]
    return records


# --- Translation constants ---

T = SiennaThermalGeneratorCol

_source = partial(pypsa_source_field, PyPSAComponent.GENERATOR)
_dest = partial(sienna_dest_field, SiennaComponent.THERMAL_STANDARD)

_direct = partial(direct_translation, _source, _dest, name_col=PyPSAGeneratorCol.NAME)
_default = partial(default_translation, _dest, name_col=PyPSAGeneratorCol.NAME)

GENERATOR_ID = row_position_id_translation(
    _dest,
    dest_name_col=T.NAME,
    id_col=T.ID,
    note="assigned by 1-based row position in thermal generators DataFrame",
)

GENERATOR_NAME = _direct(source_col=PyPSAGeneratorCol.NAME, dest_col=T.NAME)

GENERATOR_AVAILABLE = _default(
    dest_col=T.AVAILABLE,
    value=True,
    note="PyPSA Generator has no active field; defaulted to True",
)

GENERATOR_STATUS = _default(
    dest_col=T.STATUS,
    value=True,
    note="PyPSA has no separate initial on/off state; defaulted to True",
)

GENERATOR_BUS_NAME = _direct(source_col=PyPSAGeneratorCol.BUS, dest_col=T.BUS_NAME)

GENERATOR_SIENNA_TYPE = Translation(
    exprs=[],
    make_events=lambda old, _: [
        TranslationEvent(
            kind=EventKind.USER_CONFIG_DEFAULT_APPLIED,
            sources=[
                _source(
                    old[PyPSAGeneratorCol.NAME],
                    PyPSAGeneratorCol.CARRIER,
                    old[PyPSAGeneratorCol.CARRIER],
                )
            ],
            destinations=[
                _dest(
                    old[PyPSAGeneratorCol.NAME],
                    SIENNA_TYPE_ATTRIBUTE,
                    SiennaComponent.THERMAL_STANDARD,
                )
            ],
            note="according to user defined mapping",
        )
    ],
)

GENERATOR_FUEL_TYPE = Translation(
    exprs=[
        pl.col(_FUEL_TYPE_COL).cast(THERMAL_FUELS_DTYPE).alias(SiennaThermalGeneratorCol.FUEL_TYPE)
    ],
    make_events=lambda old, new: [
        TranslationEvent(
            kind=EventKind.USER_CONFIG_DEFAULT_APPLIED,
            sources=[
                SourceField(
                    framework=Framework.PYPSA,
                    component=PyPSAComponent.GENERATOR,
                    name=old[PyPSAGeneratorCol.NAME],
                    attribute=PyPSAGeneratorCol.CARRIER,
                    value=old[PyPSAGeneratorCol.CARRIER],
                )
            ],
            destinations=[
                DestinationField(
                    framework=Framework.SIENNA,
                    component=SiennaComponent.THERMAL_STANDARD,
                    name=old[PyPSAGeneratorCol.NAME],
                    attribute=SiennaThermalGeneratorCol.FUEL_TYPE,
                    value=new[SiennaThermalGeneratorCol.FUEL_TYPE],
                )
            ],
            note="according to user defined mapping",
        )
    ],
)

GENERATOR_PRIME_MOVER = Translation(
    exprs=[
        pl.col(_PRIME_MOVER_COL)
        .cast(PRIME_MOVERS_DTYPE)
        .alias(SiennaThermalGeneratorCol.PRIME_MOVER_TYPE)
    ],
    make_events=lambda old, new: [
        TranslationEvent(
            kind=EventKind.USER_CONFIG_DEFAULT_APPLIED,
            sources=[
                SourceField(
                    framework=Framework.PYPSA,
                    component=PyPSAComponent.GENERATOR,
                    name=old[PyPSAGeneratorCol.NAME],
                    attribute=PyPSAGeneratorCol.CARRIER,
                    value=old[PyPSAGeneratorCol.CARRIER],
                )
            ],
            destinations=[
                DestinationField(
                    framework=Framework.SIENNA,
                    component=SiennaComponent.THERMAL_STANDARD,
                    name=old[PyPSAGeneratorCol.NAME],
                    attribute=SiennaThermalGeneratorCol.PRIME_MOVER_TYPE,
                    value=new[SiennaThermalGeneratorCol.PRIME_MOVER_TYPE],
                )
            ],
            note="according to user defined mapping",
        )
    ],
)

GENERATOR_BASE_POWER = _direct(
    source_col=PyPSAGeneratorCol.P_NOM,
    dest_col=T.BASE_POWER,
    expr=pl.col(_EFFECTIVE_P_NOM),
    unit=UNIT_MW,
    derivation="p_nom_opt when p_nom_extendable else p_nom",
)

GENERATOR_ACTIVE_POWER = _direct(
    source_col=PyPSAGeneratorCol.P_NOM,
    dest_col=T.ACTIVE_POWER,
    expr=pl.col(_EFFECTIVE_P_NOM) * pl.col(PyPSAGeneratorCol.P_MIN_PU),
    unit=UNIT_MW,
    derivation="effective_p_nom * p_min_pu (initial dispatch = min operating point)",
)

GENERATOR_REACTIVE_POWER = _default(
    dest_col=T.REACTIVE_POWER,
    value=0.0,
    note="PyPSA networks rarely model reactive power for generators",
)

GENERATOR_RATING = _direct(
    source_col=PyPSAGeneratorCol.P_MAX_PU,
    dest_col=T.RATING,
    derivation="p_max_pu (per-unit nameplate rating; typically 1.0)",
)

GENERATOR_APL = Translation(
    exprs=[
        pl.struct(
            min=(pl.col(_EFFECTIVE_P_NOM) * pl.col(PyPSAGeneratorCol.P_MIN_PU)).cast(pl.Float64),
            max=pl.when(pl.col(_TS_PEAK_PMAX).is_not_null())
            .then(pl.col(_EFFECTIVE_P_NOM) * pl.col(_TS_PEAK_PMAX))
            .otherwise(pl.col(_EFFECTIVE_P_NOM) * pl.col(PyPSAGeneratorCol.P_MAX_PU))
            .cast(pl.Float64),
        )
        .cast(ACTIVE_POWER_LIMITS_DTYPE)
        .alias(SiennaThermalGeneratorCol.ACTIVE_POWER_LIMITS)
    ],
    make_events=lambda old, new: [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                SourceField(
                    framework=Framework.PYPSA,
                    component=PyPSAComponent.GENERATOR,
                    name=old[PyPSAGeneratorCol.NAME],
                    attribute=(
                        PyPSAGeneratorCol.P_NOM_OPT
                        if old[PyPSAGeneratorCol.P_NOM_EXTENDABLE]
                        else PyPSAGeneratorCol.P_NOM
                    ),
                    value=old[_EFFECTIVE_P_NOM],
                    unit=UNIT_MW,
                )
            ],
            destinations=[
                DestinationField(
                    framework=Framework.SIENNA,
                    component=SiennaComponent.THERMAL_STANDARD,
                    name=old[PyPSAGeneratorCol.NAME],
                    attribute=SiennaThermalGeneratorCol.ACTIVE_POWER_LIMITS,
                    value=new[SiennaThermalGeneratorCol.ACTIVE_POWER_LIMITS],
                    unit=UNIT_MW,
                )
            ],
            derivation=(
                "min=effective_p_nom*p_min_pu, max=effective_p_nom*ts_peak_p_max_pu (time series)"
                if old[_TS_PEAK_PMAX] is not None
                else "min=effective_p_nom*p_min_pu, max=effective_p_nom*p_max_pu (static)"
            ),
        )
    ],
)

GENERATOR_RAMP_LIMITS = Translation(
    exprs=[
        pl.when(
            pl.col(PyPSAGeneratorCol.RAMP_LIMIT_UP).is_not_null()
            | pl.col(PyPSAGeneratorCol.RAMP_LIMIT_DOWN).is_not_null()
        )
        .then(
            pl.struct(
                up=(
                    pl.col(_EFFECTIVE_P_NOM)
                    * pl.col(PyPSAGeneratorCol.RAMP_LIMIT_UP)
                    / pl.col(_DT_MINUTES_COL)
                ).cast(pl.Float64),
                down=(
                    pl.col(_EFFECTIVE_P_NOM)
                    * pl.col(PyPSAGeneratorCol.RAMP_LIMIT_DOWN)
                    / pl.col(_DT_MINUTES_COL)
                ).cast(pl.Float64),
            ).cast(RAMP_LIMITS_DTYPE)
        )
        .otherwise(pl.lit(None, dtype=RAMP_LIMITS_DTYPE))
        .alias(SiennaThermalGeneratorCol.RAMP_LIMITS)
    ],
    make_events=lambda old, new: (
        [
            TranslationEvent(
                kind=EventKind.VALUE_DERIVED,
                sources=[
                    SourceField(
                        framework=Framework.PYPSA,
                        component=PyPSAComponent.GENERATOR,
                        name=old[PyPSAGeneratorCol.NAME],
                        attribute=PyPSAGeneratorCol.RAMP_LIMIT_UP,
                        value=old[PyPSAGeneratorCol.RAMP_LIMIT_UP],
                    )
                ],
                destinations=[
                    DestinationField(
                        framework=Framework.SIENNA,
                        component=SiennaComponent.THERMAL_STANDARD,
                        name=old[PyPSAGeneratorCol.NAME],
                        attribute=SiennaThermalGeneratorCol.RAMP_LIMITS,
                        value=new[SiennaThermalGeneratorCol.RAMP_LIMITS],
                    )
                ],
                derivation=(
                    f"effective_p_nom * ramp_limit"
                    f" / {old[_DT_MINUTES_COL]:g} min (pu/snapshot -> MW/min)"
                ),
            )
        ]
        if (
            old[PyPSAGeneratorCol.RAMP_LIMIT_UP] is not None
            or old[PyPSAGeneratorCol.RAMP_LIMIT_DOWN] is not None
        )
        else [
            TranslationEvent(
                kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
                destinations=[
                    DestinationField(
                        framework=Framework.SIENNA,
                        component=SiennaComponent.THERMAL_STANDARD,
                        name=old[PyPSAGeneratorCol.NAME],
                        attribute=SiennaThermalGeneratorCol.RAMP_LIMITS,
                        value=None,
                    )
                ],
                note="ramp_limit_up/down absent in PyPSA network; ramp_limits set to null",
            )
        ]
    ),
)


def _generator_cost_events(old: dict[str, Any], _: dict[str, Any]) -> list[TranslationEvent]:
    name = old[PyPSAGeneratorCol.NAME]

    def cost_event(
        source_attr: str, dest_attr: str, value: float, derivation: str
    ) -> TranslationEvent:
        return TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                SourceField(
                    framework=Framework.PYPSA,
                    component=PyPSAComponent.GENERATOR,
                    name=name,
                    attribute=source_attr,
                    value=value,
                )
            ],
            destinations=[
                DestinationField(
                    framework=Framework.SIENNA,
                    component=SiennaComponent.THERMAL_STANDARD,
                    name=name,
                    attribute=f"{SiennaThermalGeneratorCol.OPERATION_COST}.{dest_attr}",
                    value=value,
                )
            ],
            derivation=derivation,
        )

    return [
        cost_event(
            PyPSAGeneratorCol.MARGINAL_COST,
            "variable.value_curve.function_data.proportional_term",
            old[PyPSAGeneratorCol.MARGINAL_COST],
            "flat marginal_cost ($/MWh) -> single-segment linear CostCurve",
        ),
        cost_event(
            PyPSAGeneratorCol.START_UP_COST,
            "start_up",
            old[PyPSAGeneratorCol.START_UP_COST],
            "start_up_cost ($) -> operation_cost.start_up",
        ),
        cost_event(
            PyPSAGeneratorCol.SHUT_DOWN_COST,
            "shut_down",
            old[PyPSAGeneratorCol.SHUT_DOWN_COST],
            "shut_down_cost ($) -> operation_cost.shut_down",
        ),
    ]


GENERATOR_COST = Translation(
    exprs=[
        pl.struct(
            cost_type=pl.lit(SiennaCostType.THERMAL),
            fixed=pl.lit(0.0),
            shut_down=pl.col(PyPSAGeneratorCol.SHUT_DOWN_COST),
            start_up=pl.col(PyPSAGeneratorCol.START_UP_COST),
            variable=variable_cost_curve(pl.col(PyPSAGeneratorCol.MARGINAL_COST)),
        )
        .cast(THERMAL_GENERATION_COST_DTYPE)
        .alias(SiennaThermalGeneratorCol.OPERATION_COST)
    ],
    make_events=_generator_cost_events,
)

GENERATOR_REACTIVE_POWER_LIMITS = _default(
    dest_col=T.REACTIVE_POWER_LIMITS,
    value=None,
    note="PyPSA does not model reactive power limits for generators in v1",
    dtype=REACTIVE_POWER_LIMITS_DTYPE,
)

GENERATOR_TIME_LIMITS = Translation(
    exprs=[
        pl.when(
            (pl.col(PyPSAGeneratorCol.MIN_UP_TIME) > 0)
            | (pl.col(PyPSAGeneratorCol.MIN_DOWN_TIME) > 0)
        )
        .then(
            pl.struct(
                up=(pl.col(PyPSAGeneratorCol.MIN_UP_TIME) * pl.col(_DT_MINUTES_COL) / 60.0).cast(
                    pl.Float64
                ),
                down=(
                    pl.col(PyPSAGeneratorCol.MIN_DOWN_TIME) * pl.col(_DT_MINUTES_COL) / 60.0
                ).cast(pl.Float64),
            ).cast(TIME_LIMITS_DTYPE)
        )
        .otherwise(pl.lit(None, dtype=TIME_LIMITS_DTYPE))
        .alias(SiennaThermalGeneratorCol.TIME_LIMITS)
    ],
    make_events=lambda old, new: (
        [
            TranslationEvent(
                kind=EventKind.VALUE_DERIVED,
                sources=[
                    SourceField(
                        framework=Framework.PYPSA,
                        component=PyPSAComponent.GENERATOR,
                        name=old[PyPSAGeneratorCol.NAME],
                        attribute=PyPSAGeneratorCol.MIN_UP_TIME,
                        value=old[PyPSAGeneratorCol.MIN_UP_TIME],
                    )
                ],
                destinations=[
                    DestinationField(
                        framework=Framework.SIENNA,
                        component=SiennaComponent.THERMAL_STANDARD,
                        name=old[PyPSAGeneratorCol.NAME],
                        attribute=SiennaThermalGeneratorCol.TIME_LIMITS,
                        value=new[SiennaThermalGeneratorCol.TIME_LIMITS],
                    )
                ],
                derivation=(
                    f"min_up_time/min_down_time × {old[_DT_MINUTES_COL]:g} min / 60 → hours"
                ),
            )
        ]
        if (old[PyPSAGeneratorCol.MIN_UP_TIME] > 0 or old[PyPSAGeneratorCol.MIN_DOWN_TIME] > 0)
        else [
            TranslationEvent(
                kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
                destinations=[
                    DestinationField(
                        framework=Framework.SIENNA,
                        component=SiennaComponent.THERMAL_STANDARD,
                        name=old[PyPSAGeneratorCol.NAME],
                        attribute=SiennaThermalGeneratorCol.TIME_LIMITS,
                        value=None,
                    )
                ],
                note="min_up_time and min_down_time both zero; time_limits set to null",
            )
        ]
    ),
)

GENERATOR_TIME_AT_STATUS = Translation(
    exprs=[
        pl.when(pl.col(PyPSAGeneratorCol.UP_TIME_BEFORE) > 0)
        .then(
            (pl.col(PyPSAGeneratorCol.UP_TIME_BEFORE) * pl.col(_DT_MINUTES_COL) / 60.0).cast(
                pl.Float64
            )
        )
        .otherwise(pl.lit(10000.0, dtype=pl.Float64))
        .alias(SiennaThermalGeneratorCol.TIME_AT_STATUS)
    ],
    make_events=lambda old, new: [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                SourceField(
                    framework=Framework.PYPSA,
                    component=PyPSAComponent.GENERATOR,
                    name=old[PyPSAGeneratorCol.NAME],
                    attribute=PyPSAGeneratorCol.UP_TIME_BEFORE,
                    value=old[PyPSAGeneratorCol.UP_TIME_BEFORE],
                )
            ],
            destinations=[
                DestinationField(
                    framework=Framework.SIENNA,
                    component=SiennaComponent.THERMAL_STANDARD,
                    name=old[PyPSAGeneratorCol.NAME],
                    attribute=SiennaThermalGeneratorCol.TIME_AT_STATUS,
                    value=new[SiennaThermalGeneratorCol.TIME_AT_STATUS],
                )
            ],
            derivation=(
                f"up_time_before × {old[_DT_MINUTES_COL]:g} min / 60 → hours"
                if old[PyPSAGeneratorCol.UP_TIME_BEFORE] > 0
                else "up_time_before=0; defaulted to 10000.0 (Sienna schema default)"
            ),
        )
    ],
)

GENERATOR_MUST_RUN = _default(
    dest_col=T.MUST_RUN,
    value=False,
    note="PyPSA Generator has no must_run concept; defaulted to False",
    dtype=pl.Boolean,
)

GENERATOR_TRANSLATIONS: list[Translation] = [
    GENERATOR_ID,
    GENERATOR_NAME,
    GENERATOR_AVAILABLE,
    GENERATOR_STATUS,
    GENERATOR_BUS_NAME,
    GENERATOR_SIENNA_TYPE,
    GENERATOR_FUEL_TYPE,
    GENERATOR_PRIME_MOVER,
    GENERATOR_BASE_POWER,
    GENERATOR_ACTIVE_POWER,
    GENERATOR_REACTIVE_POWER,
    GENERATOR_REACTIVE_POWER_LIMITS,
    GENERATOR_RATING,
    GENERATOR_APL,
    GENERATOR_RAMP_LIMITS,
    GENERATOR_TIME_LIMITS,
    GENERATOR_MUST_RUN,
    GENERATOR_TIME_AT_STATUS,
    GENERATOR_COST,
]


def _enrich_thermal(
    table: pl.DataFrame,
    ts: pl.LazyFrame | None,
    ts_info: TimeSeriesInfo,
    mappings: CarrierMappings,
) -> pl.DataFrame:
    table = enrich_carrier_lookup(table, mappings)
    table = enrich_generator_ts_stats(table, ts)
    return enrich_snapshot_duration(table, ts_info.resolution_minutes)


THERMAL_MAPPING = ComponentMapping(
    source_table=PyPSATable.GENERATORS,
    carrier_col=PyPSAGeneratorCol.CARRIER,
    fill_defaults=fill_generator_defaults,
    enrich=_enrich_thermal,
    translations=GENERATOR_TRANSLATIONS,
    schema=THERMAL_GENERATORS_DESTINATION_SCHEMA,
    sienna_component=SiennaComponent.THERMAL_STANDARD,
    time_series_attr=PyPSAGeneratorCol.P_MAX_PU,
    build_ts_association=build_generator_ts_association,
    extensions=ExtensionSpec(ExtensionKind.GENERATOR, build_generator_extensions),
)
