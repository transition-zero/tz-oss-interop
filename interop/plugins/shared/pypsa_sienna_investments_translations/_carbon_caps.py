"""Translation objects for an extensions-sidecar constraint -> Sienna CarbonCaps.

``CarbonCaps`` names no members and no region, so it holds the whole portfolio.
"""

from __future__ import annotations

from collections.abc import Sequence
from functools import partial
from typing import Any

import polars as pl

from interop.core.extensions import (
    ConstraintExtension,
    ConstraintLimit,
    ConstraintPeriod,
    ConstraintSense,
    ExtensionKind,
)
from interop.plugins.shared.pypsa_sienna_investments_translations._shared import (
    PORTFOLIO_ID_NOTE,
    investments_skip_report,
)
from interop.plugins.shared.pypsa_sienna_translations._shared import (
    pypsa_source_field,
    sienna_dest_field,
)
from interop.plugins.shared.sienna_constants import SIENNA_TYPE_ATTRIBUTE
from interop.plugins.shared.sienna_investments_constants import (
    SiennaCarbonCapsCol,
    SiennaInvestmentsComponent,
)
from interop.plugins.shared.translation_runner import (
    SkipRule,
    Translation,
    default_translation,
    direct_translation,
    row_position_id_translation,
)
from interop.ports.outbound.reporting import EventKind, TranslationEvent

# Source-table columns read off a sidecar record, none of which is a schema field.
CONSTRAINT_NAME = "name"
CONSTRAINT_SENSE = "sense"
LIMIT_PERIOD = "limit_period"
LIMIT_VALUE = "limit_value"
LIMIT_UNIT = "limit_unit"
COVERS_MODEL = "covers_model"

CARBON_CAPS_SOURCE_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    CONSTRAINT_NAME: pl.Utf8,
    CONSTRAINT_SENSE: pl.Utf8,
    LIMIT_PERIOD: pl.Utf8,
    LIMIT_VALUE: pl.Float64,
    LIMIT_UNIT: pl.Utf8,
    COVERS_MODEL: pl.Boolean,
}

# The span a cap is read from, most specific first. A yearly right-hand side is the one a
# cap on a target year holds, and a horizon-wide one is the only other span that bounds the
# whole run rather than a repeating window inside it.
_CAP_PERIODS: tuple[ConstraintPeriod, ...] = (ConstraintPeriod.YEAR, ConstraintPeriod.HORIZON)

_source = partial(pypsa_source_field, ExtensionKind.CONSTRAINT)
_dest = partial(sienna_dest_field, SiennaInvestmentsComponent.CARBON_CAPS)

C = SiennaCarbonCapsCol

_direct = partial(direct_translation, _source, _dest, name_col=CONSTRAINT_NAME)
_default = partial(default_translation, _dest, name_col=CONSTRAINT_NAME)

_constraint_skip = partial(
    investments_skip_report,
    component=ExtensionKind.CONSTRAINT,
    name_col=CONSTRAINT_NAME,
    counted_noun="constraint(s)",
)

SCOPED_CONSTRAINT_SKIP = _constraint_skip(
    reason="weight a named subset of the model rather than all of it",
    note=(
        "CarbonCaps names no members and no region, so a cap written from this constraint "
        "would hold the whole portfolio rather than the components the constraint names"
    ),
)

WRONG_SENSE_SKIP = _constraint_skip(
    reason="hold their weighted sum to something other than a ceiling",
    note="CarbonCaps states an upper limit, and this constraint does not",
    attribute_col=CONSTRAINT_SENSE,
)

NO_LIMIT_SKIP = _constraint_skip(
    reason="state no yearly or horizon-wide right-hand side",
    note="a cap with no limit bounds nothing, and no other span bounds the whole run",
)

CARBON_CAP_SKIPS: tuple[SkipRule, ...] = (
    SkipRule(keep=pl.col(CONSTRAINT_SENSE) == ConstraintSense.AT_MOST, report=WRONG_SENSE_SKIP),
    SkipRule(keep=pl.col(LIMIT_VALUE).is_not_null(), report=NO_LIMIT_SKIP),
    SkipRule(keep=pl.col(COVERS_MODEL), report=SCOPED_CONSTRAINT_SKIP),
)


def build_carbon_caps_source_table(
    records: Sequence[ConstraintExtension], model_components: set[str]
) -> pl.DataFrame:
    """One row per sidecar constraint, with the limit a cap would read and its reach.

    ``model_components`` is every component of the network a constraint could weight. A
    constraint naming all of them holds the whole model; one naming fewer holds a subset.
    """
    rows = [_read_record(record, model_components) for record in records]
    return pl.DataFrame(rows, schema=CARBON_CAPS_SOURCE_SCHEMA)


def _read_record(record: ConstraintExtension, model_components: set[str]) -> dict[str, Any]:
    limit = _choose_limit(record)
    members = {member.name for member in record.members}
    return {
        CONSTRAINT_NAME: record.name,
        CONSTRAINT_SENSE: None if record.sense is None else str(record.sense),
        LIMIT_PERIOD: None if limit is None else str(limit.period),
        LIMIT_VALUE: None if limit is None else limit.value,
        LIMIT_UNIT: None if limit is None else limit.unit,
        COVERS_MODEL: bool(model_components) and model_components <= members,
    }


def _choose_limit(record: ConstraintExtension) -> ConstraintLimit | None:
    for period in _CAP_PERIODS:
        for limit in record.limits:
            if limit.period == period:
                return limit
    return None


CARBON_CAP_NAME = _direct(source_col=CONSTRAINT_NAME, dest_col=C.NAME)

CARBON_CAP_AVAILABLE = _default(
    dest_col=C.AVAILABLE,
    value=True,
    note="a constraint the sidecar carries is one the model applies",
)

CARBON_CAP_SIENNA_TYPE = Translation(
    exprs=[],
    make_events=lambda old, _: [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[_source(old[CONSTRAINT_NAME], CONSTRAINT_SENSE, old[CONSTRAINT_SENSE])],
            destinations=[
                _dest(
                    old[CONSTRAINT_NAME],
                    SIENNA_TYPE_ATTRIBUTE,
                    SiennaInvestmentsComponent.CARBON_CAPS,
                )
            ],
            derivation="a ceiling over every component of the model -> CarbonCaps",
        )
    ],
)

CARBON_CAP_MAX_MTONS = Translation(
    exprs=[pl.col(LIMIT_VALUE).alias(C.MAX_MTONS)],
    make_events=lambda old, new: [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                _source(
                    old[CONSTRAINT_NAME],
                    f"{LIMIT_VALUE} ({old[LIMIT_PERIOD]})",
                    old[LIMIT_VALUE],
                    old[LIMIT_UNIT],
                )
            ],
            destinations=[_dest(old[CONSTRAINT_NAME], C.MAX_MTONS, new[C.MAX_MTONS])],
            derivation=f"the {old[LIMIT_PERIOD]} right-hand side of the constraint",
            note=(
                "max_mtons is read in million tonnes; the constraint states "
                f"{old[LIMIT_UNIT]}, and no conversion is applied"
                if old[LIMIT_UNIT]
                else "max_mtons is read in million tonnes, and the constraint names no unit"
            ),
        )
    ],
)

CARBON_CAP_TRANSLATIONS: list[Translation] = [
    CARBON_CAP_NAME,
    CARBON_CAP_AVAILABLE,
    CARBON_CAP_SIENNA_TYPE,
    CARBON_CAP_MAX_MTONS,
]


def build_carbon_cap_translations(start: int) -> list[Translation]:
    """Every CarbonCaps translation, including the one the shared id counter decides."""
    return [
        row_position_id_translation(
            _dest, dest_name_col=C.NAME, id_col=C.ID, note=PORTFOLIO_ID_NOTE, start=start
        ),
        *CARBON_CAP_TRANSLATIONS,
    ]
