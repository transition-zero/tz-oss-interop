"""Translation objects and helpers for PyPSA Link -> Sienna TwoTerminalGenericHVDCLine.

Power limits come from p_nom * p_min_pu/p_max_pu (extendable links use p_nom_opt when solved);
p_min_pu < 0 makes the link bidirectional, so the from-end min becomes negative. The to-end
limits are the from-end limits scaled by efficiency. efficiency maps to a linear
InputOutputCurve loss with proportional_term = 1 - efficiency. Multi-port links (bus2/bus3
set) and links touching non-electricity buses are out of scope and skipped. Time-varying
efficiency/p_min_pu/p_max_pu use the static value and record a flag in the extensions sidecar.
"""

from __future__ import annotations

from typing import Any

import polars as pl

from interop.core.extensions import ControllableLineExtension
from interop.plugins.shared.constants import UNIT_MW, Framework
from interop.plugins.shared.pypsa_constants import (
    PYPSA_COMPONENT_NAMING,
    PyPSAComponent,
    PyPSALinkCol,
    PyPSATable,
    PyPSATimeSeriesCol,
)
from interop.plugins.shared.pypsa_sienna_translations._shared import pypsa_skip_report
from interop.plugins.shared.sienna_constants import (
    IO_CURVE_DTYPE,
    MIN_MAX_DTYPE,
    SIENNA_TYPE_ATTRIBUTE,
    MinMaxField,
    SiennaComponent,
    SiennaCurveType,
    SiennaFunctionType,
    SiennaLinkCol,
)
from interop.plugins.shared.translation_runner import Translation
from interop.ports.outbound.reporting import (
    DestinationField,
    EventKind,
    SourceField,
    TranslationEvent,
)


def _source(
    name: str, attribute: str | None = None, value: object = None, unit: str | None = None
) -> SourceField:
    return SourceField(
        framework=Framework.PYPSA,
        component=PyPSAComponent.LINK,
        name=name,
        attribute=attribute,
        value=value,
        unit=unit,
    )


def _dest(
    name: str, attribute: str | None = None, value: object = None, unit: str | None = None
) -> DestinationField:
    return DestinationField(
        framework=Framework.SIENNA,
        component=SiennaComponent.TWO_TERMINAL_GENERIC_HVDC_LINE,
        name=name,
        attribute=attribute,
        value=value,
        unit=unit,
    )


# Prefix for the extensions flags that record a dropped time-varying link series.
_HAS_TIME_VARYING_PREFIX = "has_time_varying_"

# PyPSA link attributes whose time-varying form is collapsed to the static value in v1.
TIME_VARYING_LINK_ATTRS: tuple[str, ...] = (
    PyPSALinkCol.EFFICIENCY,
    PyPSALinkCol.P_MIN_PU,
    PyPSALinkCol.P_MAX_PU,
)


def fill_link_defaults(table: pl.DataFrame) -> pl.DataFrame:
    """Add optional PyPSA link columns absent when all links share the PyPSA default."""
    float_defaults: list[tuple[str, float]] = [
        (PyPSALinkCol.P_NOM, 0.0),
        (PyPSALinkCol.P_NOM_OPT, 0.0),
        (PyPSALinkCol.P_MIN_PU, 0.0),
        (PyPSALinkCol.P_MAX_PU, 1.0),
        (PyPSALinkCol.EFFICIENCY, 1.0),
    ]
    for col, default in float_defaults:
        if col not in table.columns:
            table = table.with_columns(pl.lit(default, dtype=pl.Float64).alias(col))
    if PyPSALinkCol.P_NOM_EXTENDABLE not in table.columns:
        table = table.with_columns(
            pl.lit(False, dtype=pl.Boolean).alias(PyPSALinkCol.P_NOM_EXTENDABLE)
        )
    if PyPSALinkCol.ACTIVE not in table.columns:
        table = table.with_columns(pl.lit(True, dtype=pl.Boolean).alias(PyPSALinkCol.ACTIVE))
    for str_col in (PyPSALinkCol.CARRIER, PyPSALinkCol.BUS2, PyPSALinkCol.BUS3):
        if str_col not in table.columns:
            table = table.with_columns(pl.lit("", dtype=pl.Utf8).alias(str_col))
    return table.with_columns(
        [
            pl.col(PyPSALinkCol.P_NOM).fill_nan(0.0).fill_null(0.0),
            pl.col(PyPSALinkCol.P_NOM_OPT).fill_nan(0.0).fill_null(0.0),
            pl.col(PyPSALinkCol.P_MIN_PU).fill_nan(0.0).fill_null(0.0),
            pl.col(PyPSALinkCol.P_MAX_PU).fill_nan(1.0).fill_null(1.0),
            pl.col(PyPSALinkCol.EFFICIENCY).fill_nan(1.0).fill_null(1.0),
            pl.col(PyPSALinkCol.ACTIVE).fill_null(True),
            pl.col(PyPSALinkCol.CARRIER).fill_null(""),
            pl.col(PyPSALinkCol.BUS2).fill_null(""),
            pl.col(PyPSALinkCol.BUS3).fill_null(""),
        ]
    )


def link_in_scope(ac_bus_names: list[str]) -> pl.Expr:
    """A link is in scope when it is two-port and both endpoints are electricity buses."""
    return (
        (pl.col(PyPSALinkCol.BUS2) == "")
        & (pl.col(PyPSALinkCol.BUS3) == "")
        & pl.col(PyPSALinkCol.BUS0).is_in(ac_bus_names)
        & pl.col(PyPSALinkCol.BUS1).is_in(ac_bus_names)
    )


def _link_skip_note(row: dict[str, Any]) -> str:
    """Why one out-of-scope link is left out."""
    if row[PyPSALinkCol.BUS2] or row[PyPSALinkCol.BUS3]:
        return "multi-port link (bus2/bus3 set): not translatable in v1"
    return "endpoint is not an electricity (AC) bus: not translatable in v1"


LINK_SKIP = pypsa_skip_report(
    component=PyPSAComponent.LINK,
    name_col=PyPSALinkCol.NAME,
    counted_noun=PYPSA_COMPONENT_NAMING[PyPSATable.LINKS].plural,
    reason="have more than two ports or an endpoint that is not an electricity bus",
    note=_link_skip_note,
)


def link_time_varying_owners(
    series_frames: dict[tuple[str, str], pl.LazyFrame],
) -> dict[str, set[str]]:
    """Map each time-varying flag key to the set of link names that actually carry the series.

    The series frames are keyed by ``(table, attribute)`` and list one ``component`` per
    link that has a time-varying column, so membership is per-link rather than table-wide.
    Reading only the distinct ``component`` values is a column-subset aggregation, safe to
    collect on a (potentially huge) source time-series frame.
    """
    owners: dict[str, set[str]] = {}
    for attr in TIME_VARYING_LINK_ATTRS:
        frame = series_frames.get((PyPSATable.LINKS, attr))
        if frame is None:
            continue
        names = frame.select(PyPSATimeSeriesCol.COMPONENT).unique().collect()
        owners[f"{_HAS_TIME_VARYING_PREFIX}{attr}"] = set(
            names[PyPSATimeSeriesCol.COMPONENT].to_list()
        )
    return owners


def build_link_extensions(
    enriched_src: pl.DataFrame,
    dst: pl.DataFrame,
    time_varying_owners: dict[str, set[str]],
) -> list[ControllableLineExtension]:
    """Build extension records preserving PyPSA link fields with no Sienna home.

    ``time_varying_owners`` maps a flag field to the link names that carry that time-varying
    series; each link receives only the flags for the series it actually has.
    """
    name_to_src = {row[PyPSALinkCol.NAME]: row for row in enriched_src.iter_rows(named=True)}
    records = [
        _link_extension(name, name_to_src[name], time_varying_owners)
        for name in dst[SiennaLinkCol.NAME].to_list()
    ]
    return records


def _link_extension(
    name: str, src: dict[str, Any], time_varying_owners: dict[str, set[str]]
) -> ControllableLineExtension:
    """One link's record. A field the link does not need is left unstated, not defaulted."""
    # active_power_limits_from folds p_nom * p_max_pu into a single max, and drops any
    # positive p_min_pu (its from-end min is 0). Carry both so the reverse recovers the
    # original p_nom / p_max_pu split and a positive lower bound losslessly.
    p_max_pu = src[PyPSALinkCol.P_MAX_PU]
    p_min_pu = src[PyPSALinkCol.P_MIN_PU]
    return ControllableLineExtension(
        name=name,
        carrier=src[PyPSALinkCol.CARRIER],
        p_nom_extendable=src[PyPSALinkCol.P_NOM_EXTENDABLE],
        p_max_pu=p_max_pu if p_max_pu != 1.0 else None,
        p_min_pu=p_min_pu if p_min_pu > 0.0 else None,
        **_time_varying_flags(name, time_varying_owners),
    )


def _time_varying_flags(name: str, time_varying_owners: dict[str, set[str]]) -> dict[str, bool]:
    """The flag fields this link carries a dropped series for."""
    return {field: True for field, owners in time_varying_owners.items() if name in owners}


# --- Limit / loss expressions ---

_effective_p_nom = (
    pl.when(pl.col(PyPSALinkCol.P_NOM_EXTENDABLE) & (pl.col(PyPSALinkCol.P_NOM_OPT) > 0))
    .then(pl.col(PyPSALinkCol.P_NOM_OPT))
    .otherwise(pl.col(PyPSALinkCol.P_NOM))
)
_is_bidirectional = pl.col(PyPSALinkCol.P_MIN_PU) < 0
_from_min = (
    pl.when(_is_bidirectional).then(_effective_p_nom * pl.col(PyPSALinkCol.P_MIN_PU)).otherwise(0.0)
)
_from_max = _effective_p_nom * pl.col(PyPSALinkCol.P_MAX_PU)
_to_min = (
    pl.when(_is_bidirectional)
    .then(_effective_p_nom * pl.col(PyPSALinkCol.P_MIN_PU) * pl.col(PyPSALinkCol.EFFICIENCY))
    .otherwise(0.0)
)
_to_max = _effective_p_nom * pl.col(PyPSALinkCol.P_MAX_PU) * pl.col(PyPSALinkCol.EFFICIENCY)


def _capacity_source(old: dict[str, Any]) -> tuple[str, float]:
    """The PyPSA capacity attribute actually used for the power limits, and its value."""
    if bool(old[PyPSALinkCol.P_NOM_EXTENDABLE]) and old[PyPSALinkCol.P_NOM_OPT] > 0:
        return PyPSALinkCol.P_NOM_OPT, old[PyPSALinkCol.P_NOM_OPT]
    return PyPSALinkCol.P_NOM, old[PyPSALinkCol.P_NOM]


# --- Translation constants ---

LINK_ID = Translation(
    exprs=[pl.int_range(1, pl.len() + 1, dtype=pl.Int64).alias(SiennaLinkCol.ID)],
    make_events=lambda old, new: [
        TranslationEvent(
            kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
            destinations=[_dest(new[SiennaLinkCol.NAME], SiennaLinkCol.ID, new[SiennaLinkCol.ID])],
            note="assigned by 1-based row position in links DataFrame",
        )
    ],
)

LINK_NAME = Translation(
    exprs=[pl.col(PyPSALinkCol.NAME).alias(SiennaLinkCol.NAME)],
    make_events=lambda old, new: [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[_source(old[PyPSALinkCol.NAME], PyPSALinkCol.NAME, old[PyPSALinkCol.NAME])],
            destinations=[
                _dest(new[SiennaLinkCol.NAME], SiennaLinkCol.NAME, new[SiennaLinkCol.NAME])
            ],
            derivation="direct",
        )
    ],
)

LINK_AVAILABLE = Translation(
    exprs=[pl.col(PyPSALinkCol.ACTIVE).alias(SiennaLinkCol.AVAILABLE)],
    make_events=lambda old, new: [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                _source(old[PyPSALinkCol.NAME], PyPSALinkCol.ACTIVE, old[PyPSALinkCol.ACTIVE])
            ],
            destinations=[
                _dest(old[PyPSALinkCol.NAME], SiennaLinkCol.AVAILABLE, new[SiennaLinkCol.AVAILABLE])
            ],
            derivation="active -> available",
        )
    ],
)

LINK_ACTIVE_POWER_FLOW = Translation(
    exprs=[pl.lit(0.0).alias(SiennaLinkCol.ACTIVE_POWER_FLOW)],
    make_events=lambda old, _: [
        TranslationEvent(
            kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
            destinations=[_dest(old[PyPSALinkCol.NAME], SiennaLinkCol.ACTIVE_POWER_FLOW, 0.0)],
            note="PyPSA branch flows are outputs, not inputs; initialised to 0.0",
        )
    ],
)

LINK_SIENNA_TYPE = Translation(
    exprs=[],
    make_events=lambda old, _: [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                _source(old[PyPSALinkCol.NAME], PyPSALinkCol.CARRIER, old[PyPSALinkCol.CARRIER])
            ],
            destinations=[
                _dest(
                    old[PyPSALinkCol.NAME],
                    SIENNA_TYPE_ATTRIBUTE,
                    SiennaComponent.TWO_TERMINAL_GENERIC_HVDC_LINE,
                )
            ],
            derivation="controllable branch -> TwoTerminalGenericHVDCLine",
        )
    ],
)


def _apl_from_events(old: dict[str, Any], new: dict[str, Any]) -> list[TranslationEvent]:
    capacity_attr, capacity_value = _capacity_source(old)
    return [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                _source(old[PyPSALinkCol.NAME], capacity_attr, capacity_value, unit=UNIT_MW),
                _source(old[PyPSALinkCol.NAME], PyPSALinkCol.P_MIN_PU, old[PyPSALinkCol.P_MIN_PU]),
                _source(old[PyPSALinkCol.NAME], PyPSALinkCol.P_MAX_PU, old[PyPSALinkCol.P_MAX_PU]),
            ],
            destinations=[
                _dest(
                    old[PyPSALinkCol.NAME],
                    SiennaLinkCol.ACTIVE_POWER_LIMITS_FROM,
                    new[SiennaLinkCol.ACTIVE_POWER_LIMITS_FROM],
                    unit=UNIT_MW,
                )
            ],
            derivation=(
                "min = capacity * p_min_pu (if p_min_pu < 0, else 0); max = capacity * p_max_pu"
            ),
        )
    ]


LINK_ACTIVE_POWER_LIMITS_FROM = Translation(
    exprs=[
        pl.struct(
            _from_min.alias(MinMaxField.MIN),
            _from_max.alias(MinMaxField.MAX),
        )
        .cast(MIN_MAX_DTYPE)
        .alias(SiennaLinkCol.ACTIVE_POWER_LIMITS_FROM)
    ],
    make_events=_apl_from_events,
)


def _apl_to_events(old: dict[str, Any], new: dict[str, Any]) -> list[TranslationEvent]:
    return [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                _source(
                    old[PyPSALinkCol.NAME], PyPSALinkCol.EFFICIENCY, old[PyPSALinkCol.EFFICIENCY]
                )
            ],
            destinations=[
                _dest(
                    old[PyPSALinkCol.NAME],
                    SiennaLinkCol.ACTIVE_POWER_LIMITS_TO,
                    new[SiennaLinkCol.ACTIVE_POWER_LIMITS_TO],
                    unit=UNIT_MW,
                )
            ],
            derivation="active_power_limits_to = active_power_limits_from * efficiency",
        )
    ]


LINK_ACTIVE_POWER_LIMITS_TO = Translation(
    exprs=[
        pl.struct(
            _to_min.alias(MinMaxField.MIN),
            _to_max.alias(MinMaxField.MAX),
        )
        .cast(MIN_MAX_DTYPE)
        .alias(SiennaLinkCol.ACTIVE_POWER_LIMITS_TO)
    ],
    make_events=_apl_to_events,
)


def _zero_reactive_limits(attribute: str) -> Translation:
    return Translation(
        exprs=[
            pl.struct(
                pl.lit(0.0).alias(MinMaxField.MIN),
                pl.lit(0.0).alias(MinMaxField.MAX),
            )
            .cast(MIN_MAX_DTYPE)
            .alias(attribute)
        ],
        make_events=lambda old, _: [
            TranslationEvent(
                kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
                destinations=[
                    _dest(
                        old[PyPSALinkCol.NAME],
                        attribute,
                        {MinMaxField.MIN: 0.0, MinMaxField.MAX: 0.0},
                    )
                ],
                note="PyPSA Links carry no reactive power; DC assumption",
            )
        ],
    )


LINK_REACTIVE_POWER_LIMITS_FROM = _zero_reactive_limits(SiennaLinkCol.REACTIVE_POWER_LIMITS_FROM)
LINK_REACTIVE_POWER_LIMITS_TO = _zero_reactive_limits(SiennaLinkCol.REACTIVE_POWER_LIMITS_TO)

LINK_LOSS = Translation(
    exprs=[
        pl.struct(
            curve_type=pl.lit(SiennaCurveType.INPUT_OUTPUT),
            function_data=pl.struct(
                function_type=pl.lit(SiennaFunctionType.LINEAR),
                proportional_term=(1.0 - pl.col(PyPSALinkCol.EFFICIENCY)),
                constant_term=pl.lit(0.0),
            ),
            input_at_zero=pl.lit(None, dtype=pl.Float64),
        )
        .cast(IO_CURVE_DTYPE)
        .alias(SiennaLinkCol.LOSS)
    ],
    make_events=lambda old, new: [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                _source(
                    old[PyPSALinkCol.NAME], PyPSALinkCol.EFFICIENCY, old[PyPSALinkCol.EFFICIENCY]
                )
            ],
            destinations=[
                _dest(old[PyPSALinkCol.NAME], SiennaLinkCol.LOSS, new[SiennaLinkCol.LOSS])
            ],
            derivation="loss = InputOutputCurve(proportional_term = 1 - efficiency)",
        )
    ],
)

LINK_TRANSLATIONS: list[Translation] = [
    LINK_ID,
    LINK_NAME,
    LINK_AVAILABLE,
    LINK_ACTIVE_POWER_FLOW,
    LINK_SIENNA_TYPE,
    LINK_ACTIVE_POWER_LIMITS_FROM,
    LINK_ACTIVE_POWER_LIMITS_TO,
    LINK_REACTIVE_POWER_LIMITS_FROM,
    LINK_REACTIVE_POWER_LIMITS_TO,
    LINK_LOSS,
]
