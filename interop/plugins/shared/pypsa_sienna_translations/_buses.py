"""Translation objects for PyPSA Bus → Sienna ACBus.

All bus field translations live here; relate_components only creates the Areas table.
finalise() in map_components emits NOT_MAPPED for LOAD_ZONE.
"""

from __future__ import annotations

import math

import polars as pl

from interop.core.extensions import BusExtension
from interop.plugins.shared.constants import UNIT_KV, Framework
from interop.plugins.shared.pypsa_constants import (
    DEFAULT_BUS_V_NOM,
    PYPSA_COMPONENT_NAMING,
    PyPSABusCol,
    PyPSABusControl,
    PyPSACarrier,
    PyPSAComponent,
    PyPSATable,
)
from interop.plugins.shared.pypsa_sienna_translations._shared import pypsa_skip_report
from interop.plugins.shared.sienna_constants import (
    BUSTYPE_DTYPE,
    SIENNA_TYPE_ATTRIBUTE,
    VOLTAGE_LIMIT_DTYPE,
    ACBusType,
    SiennaACBusCol,
    SiennaComponent,
)
from interop.plugins.shared.translation_runner import Translation, fill_defaults
from interop.ports.outbound.reporting import (
    DestinationField,
    EventKind,
    SourceField,
    TranslationEvent,
)

_PYPSA_DEFAULT_V_MAG_PU_SET: float = 1.0
_PYPSA_DEFAULT_V_MAG_PU_MIN: float = 0.0
_VOLTAGE_LIMIT_FALLBACK_MIN: float = 0.9
_VOLTAGE_LIMIT_FALLBACK_MAX: float = 1.1

_CONTROL_TO_BUSTYPE: dict[str, str] = {
    PyPSABusControl.PQ: ACBusType.PQ,
    PyPSABusControl.PV: ACBusType.PV,
    PyPSABusControl.SLACK: ACBusType.REF,
}
_DEFAULT_BUSTYPE = ACBusType.PQ


def fill_bus_defaults(table: pl.DataFrame) -> pl.DataFrame:
    """``v_nom``, ``carrier``, ``location``, ``control`` and the voltage magnitude columns are
    optional in PyPSA, absent when no bus has a non-default value.
    """
    return fill_defaults(
        table,
        float_defaults=[
            (PyPSABusCol.V_NOM, DEFAULT_BUS_V_NOM),
            (PyPSABusCol.V_MAG_PU_SET, _PYPSA_DEFAULT_V_MAG_PU_SET),
            (PyPSABusCol.V_MAG_PU_MIN, _PYPSA_DEFAULT_V_MAG_PU_MIN),
            (PyPSABusCol.V_MAG_PU_MAX, float("inf")),
        ],
        str_defaults=[
            (PyPSABusCol.CARRIER, PyPSACarrier.AC),
            (PyPSABusCol.LOCATION, ""),
            (PyPSABusCol.CONTROL, ""),
        ],
    )


BUS_SKIP = pypsa_skip_report(
    component=PyPSAComponent.BUS,
    name_col=PyPSABusCol.NAME,
    counted_noun=PYPSA_COMPONENT_NAMING[PyPSATable.BUSES].plural,
    reason="carry something other than electricity",
    note=lambda row: f"carrier={row[PyPSABusCol.CARRIER]!r}: only AC buses are supported in v1",
)


# --- Translation constants ---

BUS_ID = Translation(
    exprs=[pl.int_range(1, pl.len() + 1, dtype=pl.Int64).alias(SiennaACBusCol.ID)],
    make_events=lambda old, new: [
        TranslationEvent(
            kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
            destinations=[
                DestinationField(
                    framework=Framework.SIENNA,
                    component=SiennaComponent.AC_BUS,
                    name=new[SiennaACBusCol.NAME],
                    attribute=SiennaACBusCol.ID,
                    value=new[SiennaACBusCol.ID],
                )
            ],
            note="assigned by 1-based row position in AC buses DataFrame",
        )
    ],
)

BUS_NAME = Translation(
    exprs=[pl.col(PyPSABusCol.NAME).alias(SiennaACBusCol.NAME)],
    make_events=lambda old, new: [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                SourceField(
                    framework=Framework.PYPSA,
                    component=PyPSAComponent.BUS,
                    name=old[PyPSABusCol.NAME],
                    attribute=PyPSABusCol.NAME,
                    value=old[PyPSABusCol.NAME],
                )
            ],
            destinations=[
                DestinationField(
                    framework=Framework.SIENNA,
                    component=SiennaComponent.AC_BUS,
                    name=old[PyPSABusCol.NAME],
                    attribute=SiennaACBusCol.NAME,
                    value=new[SiennaACBusCol.NAME],
                )
            ],
            derivation="direct",
        )
    ],
)

BUS_NUMBER = Translation(
    exprs=[pl.int_range(1, pl.len() + 1, dtype=pl.Int64).alias(SiennaACBusCol.NUMBER)],
    make_events=lambda old, new: [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            destinations=[
                DestinationField(
                    framework=Framework.SIENNA,
                    component=SiennaComponent.AC_BUS,
                    name=old[PyPSABusCol.NAME],
                    attribute=SiennaACBusCol.NUMBER,
                    value=new[SiennaACBusCol.NUMBER],
                )
            ],
            derivation="1-based row position in AC buses DataFrame",
        )
    ],
)

BUS_AVAILABLE = Translation(
    exprs=[pl.lit(True).alias(SiennaACBusCol.AVAILABLE)],
    make_events=lambda old, new: [
        TranslationEvent(
            kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
            destinations=[
                DestinationField(
                    framework=Framework.SIENNA,
                    component=SiennaComponent.AC_BUS,
                    name=old[PyPSABusCol.NAME],
                    attribute=SiennaACBusCol.AVAILABLE,
                    value=True,
                )
            ],
            note="PyPSA Bus has no active input field; always True",
        )
    ],
)

BUS_BASE_VOLTAGE = Translation(
    exprs=[pl.col(PyPSABusCol.V_NOM).alias(SiennaACBusCol.BASE_VOLTAGE)],
    make_events=lambda old, new: [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                SourceField(
                    framework=Framework.PYPSA,
                    component=PyPSAComponent.BUS,
                    name=old[PyPSABusCol.NAME],
                    attribute=PyPSABusCol.V_NOM,
                    value=old[PyPSABusCol.V_NOM],
                    unit=UNIT_KV,
                )
            ],
            destinations=[
                DestinationField(
                    framework=Framework.SIENNA,
                    component=SiennaComponent.AC_BUS,
                    name=old[PyPSABusCol.NAME],
                    attribute=SiennaACBusCol.BASE_VOLTAGE,
                    value=new[SiennaACBusCol.BASE_VOLTAGE],
                    unit=UNIT_KV,
                )
            ],
            derivation="direct",
            note=(
                f"PyPSA default is {DEFAULT_BUS_V_NOM}kV when bus voltage level was "
                f"not specified. Flag for user review since {DEFAULT_BUS_V_NOM}kV is "
                "atypical for transmission networks."
                if old[PyPSABusCol.V_NOM] == DEFAULT_BUS_V_NOM
                else None
            ),
        )
    ],
)

BUS_AREA = Translation(
    exprs=[
        pl.when(pl.col(PyPSABusCol.LOCATION).str.len_chars() > 0)
        .then(pl.col(PyPSABusCol.LOCATION))
        .otherwise(pl.lit(None, dtype=pl.Utf8))
        .alias(SiennaACBusCol.AREA)
    ],
    make_events=lambda old, new: [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                SourceField(
                    framework=Framework.PYPSA,
                    component=PyPSAComponent.BUS,
                    name=old[PyPSABusCol.NAME],
                    attribute=PyPSABusCol.LOCATION,
                    value=old[PyPSABusCol.LOCATION] or None,
                )
            ],
            destinations=[
                DestinationField(
                    framework=Framework.SIENNA,
                    component=SiennaComponent.AC_BUS,
                    name=old[PyPSABusCol.NAME],
                    attribute=SiennaACBusCol.AREA,
                    value=new[SiennaACBusCol.AREA],
                )
            ],
            derivation="location -> area name; null if absent",
        )
    ],
)

BUS_SIENNA_TYPE = Translation(
    exprs=[],
    make_events=lambda old, _: [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                SourceField(
                    framework=Framework.PYPSA,
                    component=PyPSAComponent.BUS,
                    name=old[PyPSABusCol.NAME],
                    attribute=PyPSABusCol.CARRIER,
                    value=old[PyPSABusCol.CARRIER],
                )
            ],
            destinations=[
                DestinationField(
                    framework=Framework.SIENNA,
                    component=SiennaComponent.AC_BUS,
                    name=old[PyPSABusCol.NAME],
                    attribute=SIENNA_TYPE_ATTRIBUTE,
                    value=SiennaComponent.AC_BUS,
                )
            ],
            derivation="AC carrier -> ACBus",
        )
    ],
)

BUS_BUSTYPE = Translation(
    exprs=[
        pl.col(PyPSABusCol.CONTROL)
        .replace_strict(_CONTROL_TO_BUSTYPE, default=_DEFAULT_BUSTYPE)
        .cast(BUSTYPE_DTYPE)
        .alias(SiennaACBusCol.BUSTYPE)
    ],
    make_events=lambda old, new: [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                SourceField(
                    framework=Framework.PYPSA,
                    component=PyPSAComponent.BUS,
                    name=old[PyPSABusCol.NAME],
                    attribute=PyPSABusCol.CONTROL,
                    value=old[PyPSABusCol.CONTROL],
                )
            ],
            destinations=[
                DestinationField(
                    framework=Framework.SIENNA,
                    component=SiennaComponent.AC_BUS,
                    name=old[PyPSABusCol.NAME],
                    attribute=SiennaACBusCol.BUSTYPE,
                    value=new[SiennaACBusCol.BUSTYPE],
                )
            ],
            derivation="n.buses.control -> ACBusType",
        )
        if old[PyPSABusCol.CONTROL] in _CONTROL_TO_BUSTYPE
        else TranslationEvent(
            kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
            destinations=[
                DestinationField(
                    framework=Framework.SIENNA,
                    component=SiennaComponent.AC_BUS,
                    name=old[PyPSABusCol.NAME],
                    attribute=SiennaACBusCol.BUSTYPE,
                    value=_DEFAULT_BUSTYPE,
                )
            ],
            note=(
                f"n.buses.control={old[PyPSABusCol.CONTROL]!r} unrecognised; "
                f"defaulted to {_DEFAULT_BUSTYPE}"
                if old[PyPSABusCol.CONTROL]
                else f"n.buses.control absent; defaulted to {_DEFAULT_BUSTYPE}"
            ),
        )
    ],
)

BUS_ANGLE = Translation(
    exprs=[pl.lit(0.0).alias(SiennaACBusCol.ANGLE)],
    make_events=lambda old, _: [
        TranslationEvent(
            kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
            destinations=[
                DestinationField(
                    framework=Framework.SIENNA,
                    component=SiennaComponent.AC_BUS,
                    name=old[PyPSABusCol.NAME],
                    attribute=SiennaACBusCol.ANGLE,
                    value=0.0,
                )
            ],
            note="PyPSA Bus has no input angle field; initialised to 0.0",
        )
    ],
)

BUS_MAGNITUDE = Translation(
    exprs=[pl.col(PyPSABusCol.V_MAG_PU_SET).alias(SiennaACBusCol.MAGNITUDE)],
    make_events=lambda old, new: [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                SourceField(
                    framework=Framework.PYPSA,
                    component=PyPSAComponent.BUS,
                    name=old[PyPSABusCol.NAME],
                    attribute=PyPSABusCol.V_MAG_PU_SET,
                    value=old[PyPSABusCol.V_MAG_PU_SET],
                )
            ],
            destinations=[
                DestinationField(
                    framework=Framework.SIENNA,
                    component=SiennaComponent.AC_BUS,
                    name=old[PyPSABusCol.NAME],
                    attribute=SiennaACBusCol.MAGNITUDE,
                    value=new[SiennaACBusCol.MAGNITUDE],
                )
            ],
            derivation="direct",
        )
    ],
)

_is_voltage_limit_default = (
    pl.col(PyPSABusCol.V_MAG_PU_MIN) == _PYPSA_DEFAULT_V_MAG_PU_MIN
) & pl.col(PyPSABusCol.V_MAG_PU_MAX).is_infinite()

BUS_VOLTAGE_LIMITS = Translation(
    exprs=[
        pl.struct(
            min=pl.when(_is_voltage_limit_default)
            .then(pl.lit(_VOLTAGE_LIMIT_FALLBACK_MIN))
            .otherwise(pl.col(PyPSABusCol.V_MAG_PU_MIN))
            .cast(pl.Float64),
            max=pl.when(_is_voltage_limit_default)
            .then(pl.lit(_VOLTAGE_LIMIT_FALLBACK_MAX))
            .otherwise(pl.col(PyPSABusCol.V_MAG_PU_MAX))
            .cast(pl.Float64),
        )
        .cast(VOLTAGE_LIMIT_DTYPE)
        .alias(SiennaACBusCol.VOLTAGE_LIMITS)
    ],
    make_events=lambda old, new: [
        TranslationEvent(
            kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
            sources=[
                SourceField(
                    framework=Framework.PYPSA,
                    component=PyPSAComponent.BUS,
                    name=old[PyPSABusCol.NAME],
                    attribute=PyPSABusCol.V_MAG_PU_MIN,
                    value=old[PyPSABusCol.V_MAG_PU_MIN],
                ),
                SourceField(
                    framework=Framework.PYPSA,
                    component=PyPSAComponent.BUS,
                    name=old[PyPSABusCol.NAME],
                    attribute=PyPSABusCol.V_MAG_PU_MAX,
                    value=old[PyPSABusCol.V_MAG_PU_MAX],
                ),
            ],
            destinations=[
                DestinationField(
                    framework=Framework.SIENNA,
                    component=SiennaComponent.AC_BUS,
                    name=old[PyPSABusCol.NAME],
                    attribute=SiennaACBusCol.VOLTAGE_LIMITS,
                    value=new[SiennaACBusCol.VOLTAGE_LIMITS],
                )
            ],
            note=(
                f"PyPSA defaults (v_mag_pu_min=0.0, v_mag_pu_max=∞) are invalid for Sienna; "
                f"applying fallback ({_VOLTAGE_LIMIT_FALLBACK_MIN}, {_VOLTAGE_LIMIT_FALLBACK_MAX})"
            ),
        )
        if (
            old[PyPSABusCol.V_MAG_PU_MIN] == _PYPSA_DEFAULT_V_MAG_PU_MIN
            and math.isinf(old[PyPSABusCol.V_MAG_PU_MAX])
        )
        else TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                SourceField(
                    framework=Framework.PYPSA,
                    component=PyPSAComponent.BUS,
                    name=old[PyPSABusCol.NAME],
                    attribute=PyPSABusCol.V_MAG_PU_MIN,
                    value=old[PyPSABusCol.V_MAG_PU_MIN],
                ),
                SourceField(
                    framework=Framework.PYPSA,
                    component=PyPSAComponent.BUS,
                    name=old[PyPSABusCol.NAME],
                    attribute=PyPSABusCol.V_MAG_PU_MAX,
                    value=old[PyPSABusCol.V_MAG_PU_MAX],
                ),
            ],
            destinations=[
                DestinationField(
                    framework=Framework.SIENNA,
                    component=SiennaComponent.AC_BUS,
                    name=old[PyPSABusCol.NAME],
                    attribute=SiennaACBusCol.VOLTAGE_LIMITS,
                    value=new[SiennaACBusCol.VOLTAGE_LIMITS],
                )
            ],
            derivation="v_mag_pu_min, v_mag_pu_max -> voltage_limits.{min, max}",
        )
    ],
)

BUS_TRANSLATIONS: list[Translation] = [
    BUS_ID,
    BUS_NAME,
    BUS_NUMBER,
    BUS_AVAILABLE,
    BUS_BASE_VOLTAGE,
    BUS_AREA,
    BUS_SIENNA_TYPE,
    BUS_BUSTYPE,
    BUS_ANGLE,
    BUS_MAGNITUDE,
    BUS_VOLTAGE_LIMITS,
]


def build_bus_extensions(
    enriched_src: pl.DataFrame,
    dst: pl.DataFrame,
) -> list[BusExtension]:
    """Build extension records for all translated buses.

    Every bus produces a record preserving ``carrier`` (always ``"AC"`` after the
    AC filter, but stored for round-trip completeness).
    """
    name_to_src = {row[PyPSABusCol.NAME]: row for row in enriched_src.iter_rows(named=True)}
    records = [
        BusExtension(name=name, carrier=name_to_src[name][PyPSABusCol.CARRIER])
        for name in dst[SiennaACBusCol.NAME].to_list()
    ]
    return records
