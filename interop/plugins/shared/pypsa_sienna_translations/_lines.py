"""Translation objects and helpers for PyPSA Line -> Sienna Line.

Series impedance (r, x) and shunt admittance (b, g) are converted from PyPSA's absolute
ohms/siemens to per-unit on a 100 MVA system base using the endpoint bus voltage; b and g
are split equally across the pi-model ends. ``rating`` is the effective MVA limit
(s_nom * s_max_pu), falling back to the nominal s_nom for extendable lines with no
optimised capacity. Endpoints travel as bus *names* (bus0/bus1) and are resolved to the
shared Arc by the sink. A Sienna Line carries one static rating, so a line stating s_max_pu
as a time series (dynamic line rating) is left out.
"""

from __future__ import annotations

import math
from typing import Any

import polars as pl

from interop.core.extensions import LineExtension
from interop.plugins.shared.constants import (
    UNIT_MVA,
    UNIT_OHM,
    UNIT_SIEMENS,
    Framework,
)
from interop.plugins.shared.pypsa_constants import (
    PYPSA_COMPONENT_NAMING,
    PyPSACarrier,
    PyPSAComponent,
    PyPSALineCol,
    PyPSATable,
    PyPSATimeSeriesCol,
)
from interop.plugins.shared.pypsa_sienna_translations._shared import pypsa_skip_report
from interop.plugins.shared.sienna_constants import (
    FROM_TO_DTYPE,
    MIN_MAX_DTYPE,
    SIENNA_TYPE_ATTRIBUTE,
    SYSTEM_BASE_MVA,
    FromToField,
    MinMaxField,
    SiennaACBusCol,
    SiennaComponent,
    SiennaLineCol,
)
from interop.plugins.shared.translation_runner import Translation
from interop.ports.outbound.reporting import (
    DestinationField,
    EventKind,
    SourceField,
    TranslationEvent,
)

# Default Sienna angle limits when PyPSA v_ang_min/v_ang_max are unset (+/- infinity).
_DEFAULT_ANGLE_RAD: float = math.pi / 2

# Enrichment column: endpoint (bus0) base voltage in kV, used for the per-unit conversion.
# Dropped by finalise().
_V_NOM = "_v_nom_kv"

_DYNAMIC_RATING_NOTE = (
    "the line states s_max_pu as a time series (dynamic line rating), and a Sienna Line "
    "carries one static rating, so its capacity over the horizon is not something this "
    "mapping can write"
)

LINE_DYNAMIC_RATING_SKIP = pypsa_skip_report(
    component=PyPSAComponent.LINE,
    name_col=PyPSALineCol.NAME,
    counted_noun=PYPSA_COMPONENT_NAMING[PyPSATable.LINES].plural,
    reason="state s_max_pu as a time series (dynamic line rating)",
    note=_DYNAMIC_RATING_NOTE,
)


def lines_rated_by_a_series(series_frames: dict[tuple[str, str], pl.LazyFrame]) -> set[str]:
    """The lines whose s_max_pu is a time series rather than one number.

    Reading only the distinct ``component`` values is a column-subset aggregation, safe to
    collect on a (potentially huge) source time-series frame.
    """
    frame = series_frames.get((PyPSATable.LINES, PyPSALineCol.S_MAX_PU))
    if frame is None:
        return set()
    names = frame.select(PyPSATimeSeriesCol.COMPONENT).unique().collect()
    return set(names[PyPSATimeSeriesCol.COMPONENT].to_list())


def line_rating_is_static(rated_by_a_series: set[str]) -> pl.Expr:
    """A line is in scope when one number states its rating for the whole horizon."""
    return ~pl.col(PyPSALineCol.NAME).is_in(sorted(rated_by_a_series))


def _source(
    name: str, attribute: str | None = None, value: object = None, unit: str | None = None
) -> SourceField:
    return SourceField(
        framework=Framework.PYPSA,
        component=PyPSAComponent.LINE,
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
        component=SiennaComponent.LINE,
        name=name,
        attribute=attribute,
        value=value,
        unit=unit,
    )


def fill_line_defaults(table: pl.DataFrame) -> pl.DataFrame:
    """Add optional PyPSA line columns absent when all lines share the PyPSA default."""
    float_defaults: list[tuple[str, float]] = [
        (PyPSALineCol.R, 0.0),
        (PyPSALineCol.X, 0.0),
        (PyPSALineCol.B, 0.0),
        (PyPSALineCol.G, 0.0),
        (PyPSALineCol.S_NOM, 0.0),
        (PyPSALineCol.S_MAX_PU, 1.0),
        (PyPSALineCol.S_NOM_OPT, 0.0),
        (PyPSALineCol.LENGTH, 0.0),
        (PyPSALineCol.NUM_PARALLEL, 1.0),
        (PyPSALineCol.V_ANG_MIN, float("-inf")),
        (PyPSALineCol.V_ANG_MAX, float("inf")),
    ]
    for col, default in float_defaults:
        if col not in table.columns:
            table = table.with_columns(pl.lit(default, dtype=pl.Float64).alias(col))
    if PyPSALineCol.S_NOM_EXTENDABLE not in table.columns:
        table = table.with_columns(
            pl.lit(False, dtype=pl.Boolean).alias(PyPSALineCol.S_NOM_EXTENDABLE)
        )
    if PyPSALineCol.ACTIVE not in table.columns:
        table = table.with_columns(pl.lit(True, dtype=pl.Boolean).alias(PyPSALineCol.ACTIVE))
    if PyPSALineCol.CARRIER not in table.columns:
        table = table.with_columns(pl.lit(PyPSACarrier.AC).alias(PyPSALineCol.CARRIER))
    return table.with_columns(
        [
            pl.col(PyPSALineCol.B).fill_nan(0.0).fill_null(0.0),
            pl.col(PyPSALineCol.G).fill_nan(0.0).fill_null(0.0),
            pl.col(PyPSALineCol.S_MAX_PU).fill_nan(1.0).fill_null(1.0),
            pl.col(PyPSALineCol.S_NOM_OPT).fill_nan(0.0).fill_null(0.0),
            pl.col(PyPSALineCol.LENGTH).fill_nan(0.0).fill_null(0.0),
            pl.col(PyPSALineCol.NUM_PARALLEL).fill_nan(1.0).fill_null(1.0),
            pl.col(PyPSALineCol.ACTIVE).fill_null(True),
            pl.col(PyPSALineCol.CARRIER).fill_null(PyPSACarrier.AC),
        ]
    )


def enrich_line_voltage(table: pl.DataFrame, sienna_buses: pl.DataFrame) -> pl.DataFrame:
    """Left-join the bus0 base voltage (kV) for the per-unit impedance conversion."""
    lookup = sienna_buses.select(
        [
            pl.col(SiennaACBusCol.NAME).alias(PyPSALineCol.BUS0),
            pl.col(SiennaACBusCol.BASE_VOLTAGE).alias(_V_NOM),
        ]
    )
    return table.join(lookup, on=PyPSALineCol.BUS0, how="left")


def build_line_extensions(enriched_src: pl.DataFrame, dst: pl.DataFrame) -> list[LineExtension]:
    """Build extension records preserving PyPSA line fields with no Sienna home."""
    name_to_src = {row[PyPSALineCol.NAME]: row for row in enriched_src.iter_rows(named=True)}
    records = [
        LineExtension(
            name=name,
            carrier=name_to_src[name][PyPSALineCol.CARRIER],
            length=name_to_src[name][PyPSALineCol.LENGTH],
            num_parallel=name_to_src[name][PyPSALineCol.NUM_PARALLEL],
            s_nom_extendable=name_to_src[name][PyPSALineCol.S_NOM_EXTENDABLE],
        )
        for name in dst[SiennaLineCol.NAME].to_list()
    ]
    return records


# --- Per-unit conversion expressions (per-unit on SYSTEM_BASE_MVA) ---

_r_pu = pl.col(PyPSALineCol.R) * SYSTEM_BASE_MVA / pl.col(_V_NOM) ** 2
_x_pu = pl.col(PyPSALineCol.X) * SYSTEM_BASE_MVA / pl.col(_V_NOM) ** 2
_b_total_pu = pl.col(PyPSALineCol.B) * pl.col(_V_NOM) ** 2 / SYSTEM_BASE_MVA
_g_total_pu = pl.col(PyPSALineCol.G) * pl.col(_V_NOM) ** 2 / SYSTEM_BASE_MVA
_effective_s_nom = (
    pl.when(pl.col(PyPSALineCol.S_NOM_EXTENDABLE) & (pl.col(PyPSALineCol.S_NOM_OPT) > 0))
    .then(pl.col(PyPSALineCol.S_NOM_OPT))
    .otherwise(pl.col(PyPSALineCol.S_NOM))
)

_R_DERIVATION = "r_ohm * S_base / v_nom^2 (per-unit on 100 MVA)"
_X_DERIVATION = "x_ohm * S_base / v_nom^2 (per-unit on 100 MVA)"
_B_DERIVATION = "b_siemens * v_nom^2 / S_base, split equally (per-unit on 100 MVA)"
_G_DERIVATION = "g_siemens * v_nom^2 / S_base, split equally (per-unit on 100 MVA)"

# --- Translation constants ---

LINE_ID = Translation(
    exprs=[pl.int_range(1, pl.len() + 1, dtype=pl.Int64).alias(SiennaLineCol.ID)],
    make_events=lambda old, new: [
        TranslationEvent(
            kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
            destinations=[_dest(new[SiennaLineCol.NAME], SiennaLineCol.ID, new[SiennaLineCol.ID])],
            note="assigned by 1-based row position in lines DataFrame",
        )
    ],
)

LINE_NAME = Translation(
    exprs=[pl.col(PyPSALineCol.NAME).alias(SiennaLineCol.NAME)],
    make_events=lambda old, new: [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[_source(old[PyPSALineCol.NAME], PyPSALineCol.NAME, old[PyPSALineCol.NAME])],
            destinations=[
                _dest(new[SiennaLineCol.NAME], SiennaLineCol.NAME, new[SiennaLineCol.NAME])
            ],
            derivation="direct",
        )
    ],
)

LINE_AVAILABLE = Translation(
    exprs=[pl.col(PyPSALineCol.ACTIVE).alias(SiennaLineCol.AVAILABLE)],
    make_events=lambda old, new: [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                _source(old[PyPSALineCol.NAME], PyPSALineCol.ACTIVE, old[PyPSALineCol.ACTIVE])
            ],
            destinations=[
                _dest(old[PyPSALineCol.NAME], SiennaLineCol.AVAILABLE, new[SiennaLineCol.AVAILABLE])
            ],
            derivation="active -> available",
        )
    ],
)

LINE_ACTIVE_POWER_FLOW = Translation(
    exprs=[pl.lit(0.0).alias(SiennaLineCol.ACTIVE_POWER_FLOW)],
    make_events=lambda old, _: [
        TranslationEvent(
            kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
            destinations=[_dest(old[PyPSALineCol.NAME], SiennaLineCol.ACTIVE_POWER_FLOW, 0.0)],
            note="PyPSA branch flows are outputs, not inputs; initialised to 0.0",
        )
    ],
)

LINE_REACTIVE_POWER_FLOW = Translation(
    exprs=[pl.lit(0.0).alias(SiennaLineCol.REACTIVE_POWER_FLOW)],
    make_events=lambda old, _: [
        TranslationEvent(
            kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
            destinations=[_dest(old[PyPSALineCol.NAME], SiennaLineCol.REACTIVE_POWER_FLOW, 0.0)],
            note="PyPSA branch flows are outputs, not inputs; initialised to 0.0",
        )
    ],
)

LINE_SIENNA_TYPE = Translation(
    exprs=[],
    make_events=lambda old, _: [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                _source(old[PyPSALineCol.NAME], PyPSALineCol.CARRIER, old[PyPSALineCol.CARRIER])
            ],
            destinations=[
                _dest(old[PyPSALineCol.NAME], SIENNA_TYPE_ATTRIBUTE, SiennaComponent.LINE)
            ],
            derivation="AC branch -> Line",
        )
    ],
)

LINE_R = Translation(
    exprs=[_r_pu.alias(SiennaLineCol.R)],
    make_events=lambda old, new: [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                _source(old[PyPSALineCol.NAME], PyPSALineCol.R, old[PyPSALineCol.R], unit=UNIT_OHM)
            ],
            destinations=[_dest(old[PyPSALineCol.NAME], SiennaLineCol.R, new[SiennaLineCol.R])],
            derivation=_R_DERIVATION,
        )
    ],
)

LINE_X = Translation(
    exprs=[_x_pu.alias(SiennaLineCol.X)],
    make_events=lambda old, new: [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                _source(old[PyPSALineCol.NAME], PyPSALineCol.X, old[PyPSALineCol.X], unit=UNIT_OHM)
            ],
            destinations=[_dest(old[PyPSALineCol.NAME], SiennaLineCol.X, new[SiennaLineCol.X])],
            derivation=_X_DERIVATION,
        )
    ],
)

LINE_B = Translation(
    exprs=[
        pl.struct(
            (_b_total_pu / 2).alias(FromToField.FROM),
            (_b_total_pu / 2).alias(FromToField.TO),
        )
        .cast(FROM_TO_DTYPE)
        .alias(SiennaLineCol.B)
    ],
    make_events=lambda old, new: [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                _source(
                    old[PyPSALineCol.NAME], PyPSALineCol.B, old[PyPSALineCol.B], unit=UNIT_SIEMENS
                )
            ],
            destinations=[_dest(old[PyPSALineCol.NAME], SiennaLineCol.B, new[SiennaLineCol.B])],
            derivation=_B_DERIVATION,
        )
    ],
)

LINE_G = Translation(
    exprs=[
        pl.struct(
            (_g_total_pu / 2).alias(FromToField.FROM),
            (_g_total_pu / 2).alias(FromToField.TO),
        )
        .cast(FROM_TO_DTYPE)
        .alias(SiennaLineCol.G)
    ],
    make_events=lambda old, new: [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                _source(
                    old[PyPSALineCol.NAME], PyPSALineCol.G, old[PyPSALineCol.G], unit=UNIT_SIEMENS
                )
            ],
            destinations=[_dest(old[PyPSALineCol.NAME], SiennaLineCol.G, new[SiennaLineCol.G])],
            derivation=_G_DERIVATION,
        )
    ],
)


def _rating_uses_opt(old: dict[str, Any]) -> bool:
    """An extendable line with an optimised capacity uses s_nom_opt, not nominal s_nom."""
    return bool(old[PyPSALineCol.S_NOM_EXTENDABLE]) and old[PyPSALineCol.S_NOM_OPT] > 0


def _rating_capacity_source(old: dict[str, Any]) -> tuple[str, float]:
    """The PyPSA capacity attribute actually used for the rating, and its value."""
    if _rating_uses_opt(old):
        return PyPSALineCol.S_NOM_OPT, old[PyPSALineCol.S_NOM_OPT]
    return PyPSALineCol.S_NOM, old[PyPSALineCol.S_NOM]


def _rating_note(old: dict[str, Any], new: dict[str, Any]) -> str | None:
    if new[SiennaLineCol.RATING] == 0.0:
        return (
            "s_nom=0: line has zero rating; Sienna will constrain its flow to zero "
            "(flagged for user review)"
        )
    if old[PyPSALineCol.S_NOM_EXTENDABLE] and old[PyPSALineCol.S_NOM_OPT] <= 0:
        return "extendable line with no optimised capacity; using nominal s_nom as rating"
    return None


def _rating_events(old: dict[str, Any], new: dict[str, Any]) -> list[TranslationEvent]:
    capacity_attr, capacity_value = _rating_capacity_source(old)
    return [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                _source(old[PyPSALineCol.NAME], capacity_attr, capacity_value, unit=UNIT_MVA),
                _source(old[PyPSALineCol.NAME], PyPSALineCol.S_MAX_PU, old[PyPSALineCol.S_MAX_PU]),
            ],
            destinations=[
                _dest(old[PyPSALineCol.NAME], SiennaLineCol.RATING, new[SiennaLineCol.RATING])
            ],
            derivation=f"{capacity_attr} * s_max_pu / S_base (per-unit on 100 MVA)",
            note=_rating_note(old, new),
        )
    ]


LINE_RATING = Translation(
    exprs=[
        (_effective_s_nom * pl.col(PyPSALineCol.S_MAX_PU) / SYSTEM_BASE_MVA).alias(
            SiennaLineCol.RATING
        )
    ],
    make_events=_rating_events,
)


def _angle_limits_events(old: dict[str, Any], new: dict[str, Any]) -> list[TranslationEvent]:
    angle = new[SiennaLineCol.ANGLE_LIMITS]
    if math.isfinite(old[PyPSALineCol.V_ANG_MIN]) and math.isfinite(old[PyPSALineCol.V_ANG_MAX]):
        return [
            TranslationEvent(
                kind=EventKind.VALUE_DERIVED,
                sources=[
                    _source(
                        old[PyPSALineCol.NAME], PyPSALineCol.V_ANG_MIN, old[PyPSALineCol.V_ANG_MIN]
                    )
                ],
                destinations=[_dest(old[PyPSALineCol.NAME], SiennaLineCol.ANGLE_LIMITS, angle)],
                derivation="v_ang_min/v_ang_max degrees -> radians",
            )
        ]
    return [
        TranslationEvent(
            kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
            destinations=[_dest(old[PyPSALineCol.NAME], SiennaLineCol.ANGLE_LIMITS, angle)],
            note="v_ang_min/v_ang_max unset (+/- inf); defaulted to +/- pi/2",
        )
    ]


LINE_ANGLE_LIMITS = Translation(
    exprs=[
        pl.when(
            pl.col(PyPSALineCol.V_ANG_MIN).is_finite() & pl.col(PyPSALineCol.V_ANG_MAX).is_finite()
        )
        .then(
            pl.struct(
                (pl.col(PyPSALineCol.V_ANG_MIN) * math.pi / 180).alias(MinMaxField.MIN),
                (pl.col(PyPSALineCol.V_ANG_MAX) * math.pi / 180).alias(MinMaxField.MAX),
            )
        )
        .otherwise(
            pl.struct(
                pl.lit(-_DEFAULT_ANGLE_RAD).alias(MinMaxField.MIN),
                pl.lit(_DEFAULT_ANGLE_RAD).alias(MinMaxField.MAX),
            )
        )
        .cast(MIN_MAX_DTYPE)
        .alias(SiennaLineCol.ANGLE_LIMITS)
    ],
    make_events=_angle_limits_events,
)

LINE_TRANSLATIONS: list[Translation] = [
    LINE_ID,
    LINE_NAME,
    LINE_AVAILABLE,
    LINE_ACTIVE_POWER_FLOW,
    LINE_REACTIVE_POWER_FLOW,
    LINE_SIENNA_TYPE,
    LINE_R,
    LINE_X,
    LINE_B,
    LINE_G,
    LINE_RATING,
    LINE_ANGLE_LIMITS,
]
