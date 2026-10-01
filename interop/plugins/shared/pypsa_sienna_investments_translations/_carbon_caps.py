"""Translation objects for an extensions-sidecar constraint -> Sienna CarbonCaps.

A constraint record states the same thing whichever framework wrote it, so every rule here
reads the record alone. The caller states which framework that was, through
``InvestmentsSource``.
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
from interop.plugins.shared.constants import Framework
from interop.plugins.shared.pypsa_sienna_investments_translations._shared import (
    PORTFOLIO_ID_NOTE,
    InvestmentsSource,
)
from interop.plugins.shared.pypsa_sienna_translations._shared import sienna_dest_field
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
APPLIES_TO_PLAN = "applies_to_expansion_plan"

CARBON_CAPS_SOURCE_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    CONSTRAINT_NAME: pl.Utf8,
    CONSTRAINT_SENSE: pl.Utf8,
    LIMIT_PERIOD: pl.Utf8,
    LIMIT_VALUE: pl.Float64,
    LIMIT_UNIT: pl.Utf8,
    COVERS_MODEL: pl.Boolean,
    APPLIES_TO_PLAN: pl.Boolean,
}

# The spans a cap is read from, most specific first: no other span bounds the whole run.
_CAP_PERIODS: tuple[ConstraintPeriod, ...] = (ConstraintPeriod.YEAR, ConstraintPeriod.HORIZON)

_dest = partial(sienna_dest_field, SiennaInvestmentsComponent.CARBON_CAPS)

C = SiennaCarbonCapsCol

_default = partial(default_translation, _dest, name_col=CONSTRAINT_NAME)

# What a warning calls the class a constraint record belongs to, whatever framework wrote it.
CONSTRAINT_PLURAL = "constraint(s)"

SCOPED_CONSTRAINT_REASON = "weight a named subset of the model rather than all of it"
SCOPED_CONSTRAINT_NOTE = (
    "CarbonCaps names no members and no region, so a cap written from this constraint "
    "would hold the whole portfolio rather than the components the constraint names"
)
WRONG_SENSE_REASON = "hold their weighted sum to something other than a ceiling"
WRONG_SENSE_NOTE = "CarbonCaps states an upper limit, and this constraint does not"
NO_LIMIT_REASON = "state no yearly or horizon-wide right-hand side"
NO_LIMIT_NOTE = "a cap with no limit bounds nothing, and no other span bounds the whole run"
NOT_IN_PLAN_REASON = "the expansion plan does not have to meet"
NOT_IN_PLAN_NOTE = (
    "the source states that the plan need not meet this constraint, so a cap written "
    "from it would bound an expansion problem the model leaves free"
)
NON_FINITE_LIMIT_REASON = "state a right-hand side that is not a finite number"
NON_FINITE_LIMIT_NOTE = (
    "max_mtons would be NaN or Infinity, which no JSON reader accepts as a number"
)


def constraint_source(framework: Framework, pipeline: str) -> InvestmentsSource:
    """The sidecar constraints of one framework, as the report names them."""
    return InvestmentsSource(
        framework=framework,
        pipeline=pipeline,
        component=ExtensionKind.CONSTRAINT,
        display=ExtensionKind.CONSTRAINT,
        plural=CONSTRAINT_PLURAL,
    )


def build_carbon_cap_skips(source: InvestmentsSource) -> tuple[SkipRule, ...]:
    """Every reason a constraint states no cap, in the order they apply."""
    skip = partial(source.skip, name_col=CONSTRAINT_NAME)
    return (
        # A source that states nothing about the plan leaves every constraint in it.
        SkipRule(
            keep=pl.col(APPLIES_TO_PLAN).fill_null(value=True),
            report=skip(
                reason=NOT_IN_PLAN_REASON, note=NOT_IN_PLAN_NOTE, attribute_col=APPLIES_TO_PLAN
            ),
        ),
        SkipRule(
            keep=pl.col(CONSTRAINT_SENSE) == ConstraintSense.AT_MOST,
            report=skip(
                reason=WRONG_SENSE_REASON, note=WRONG_SENSE_NOTE, attribute_col=CONSTRAINT_SENSE
            ),
        ),
        SkipRule(
            keep=pl.col(LIMIT_VALUE).is_not_null(),
            report=skip(reason=NO_LIMIT_REASON, note=NO_LIMIT_NOTE),
        ),
        # is_finite answers null for a null limit, so this rule follows the one that drops those.
        SkipRule(
            keep=pl.col(LIMIT_VALUE).is_finite(),
            report=skip(
                reason=NON_FINITE_LIMIT_REASON,
                note=NON_FINITE_LIMIT_NOTE,
                attribute_col=LIMIT_VALUE,
            ),
        ),
        SkipRule(
            keep=pl.col(COVERS_MODEL),
            report=skip(reason=SCOPED_CONSTRAINT_REASON, note=SCOPED_CONSTRAINT_NOTE),
        ),
    )


def build_carbon_caps_source_table(
    records: Sequence[ConstraintExtension], model_components: set[tuple[str, str]]
) -> pl.DataFrame:
    """One row per sidecar constraint, with the limit a cap would read and its reach.

    ``model_components`` is every component of the network a constraint could weight, each
    named with the class it belongs to. A constraint naming all of them holds the whole
    model; one naming fewer holds a subset. Two classes can hold an object of one name, so a
    member counts only where its class matches as well, and a member whose class the network
    states differently leaves the constraint short of the whole model.
    """
    rows = [_read_record(record, model_components) for record in records]
    return pl.DataFrame(rows, schema=CARBON_CAPS_SOURCE_SCHEMA)


def _read_record(
    record: ConstraintExtension, model_components: set[tuple[str, str]]
) -> dict[str, Any]:
    limit = _choose_limit(record)
    members = {(member.name, member.member_class) for member in record.members}
    return {
        CONSTRAINT_NAME: record.name,
        CONSTRAINT_SENSE: None if record.sense is None else str(record.sense),
        LIMIT_PERIOD: None if limit is None else str(limit.period),
        LIMIT_VALUE: None if limit is None else limit.value,
        LIMIT_UNIT: None if limit is None else limit.unit,
        COVERS_MODEL: bool(model_components) and model_components <= members,
        APPLIES_TO_PLAN: record.applies_to_expansion_plan,
    }


def _choose_limit(record: ConstraintExtension) -> ConstraintLimit | None:
    for period in _CAP_PERIODS:
        for limit in record.limits:
            if limit.period == period:
                return limit
    return None


CARBON_CAP_AVAILABLE = _default(
    dest_col=C.AVAILABLE,
    value=True,
    note="a constraint the sidecar carries is one the model applies",
)


def _sienna_type(source: InvestmentsSource) -> Translation:
    """A ceiling over the whole model is the one shape a CarbonCaps holds."""
    return Translation(
        exprs=[],
        make_events=lambda old, _: [
            TranslationEvent(
                kind=EventKind.VALUE_DERIVED,
                sources=[
                    source.field(old[CONSTRAINT_NAME], CONSTRAINT_SENSE, old[CONSTRAINT_SENSE])
                ],
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


def _max_mtons(source: InvestmentsSource) -> Translation:
    """The right-hand side the cap holds the whole model to."""
    return Translation(
        exprs=[pl.col(LIMIT_VALUE).alias(C.MAX_MTONS)],
        make_events=lambda old, new: [
            TranslationEvent(
                kind=EventKind.VALUE_DERIVED,
                sources=[
                    source.field(
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


def build_carbon_cap_translations(source: InvestmentsSource, start: int) -> list[Translation]:
    """Every CarbonCaps translation, including the one the shared id counter decides."""
    return [
        row_position_id_translation(
            _dest, dest_name_col=C.NAME, id_col=C.ID, note=PORTFOLIO_ID_NOTE, start=start
        ),
        direct_translation(
            source.field,
            _dest,
            name_col=CONSTRAINT_NAME,
            source_col=CONSTRAINT_NAME,
            dest_col=C.NAME,
        ),
        CARBON_CAP_AVAILABLE,
        _sienna_type(source),
        _max_mtons(source),
    ]
