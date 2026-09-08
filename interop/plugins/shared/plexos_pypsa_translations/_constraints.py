"""PLEXOS Constraint -> extensions sidecar.

A PLEXOS Constraint holds a weighted sum over the objects it names to a right-hand side.
It weights each object by a coefficient stated on the membership, and it may state the
right-hand side over an hour, a day, a week, a month, a year, or the whole horizon.

PyPSA's GlobalConstraint limits one carrier over the whole horizon and has no way to name
a set of components, so no shape of Constraint has a home in the network file. Each one is
carried into the extensions sidecar instead, in framework-neutral terms (see
``interop/core/extensions.py``), so a later hop into a framework that can express it still
has the limit. A Constraint stating no sense, or no right-hand side at all, says too little
to carry, so it is left out and reported.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from interop.core.extensions import (
    ConstraintExtension,
    ConstraintLimit,
    ConstraintMember,
    ConstraintPeriod,
    ConstraintSense,
    ExtensionKind,
    append_extensions,
)
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.plexos_constants import (
    PlexosClass,
    PlexosObjectCol,
    PlexosProperty,
    PlexosResolvedTable,
    is_plexos_true,
)
from interop.plugins.shared.plexos_pypsa_translations._shared import (
    ClassMember,
    MemberProperties,
    ObjectProperties,
    ObjectUnits,
    collapse_member_properties,
    collapse_properties_by_object,
    collapse_units_by_object,
    relate_all_children,
)
from interop.plugins.shared.plexos_pypsa_translations.decisions import (
    SourceReporter,
    SourceValue,
)
from interop.plugins.shared.warning_text import name_a_few

log = logging.getLogger(__name__)

_CARRIED_NOTE = (
    "constraint carried to the extensions sidecar; PyPSA's GlobalConstraint cannot hold a "
    "weighted sum over the objects a Constraint names, so the network file itself does not "
    "limit them"
)
_NOT_CARRIED_NOTE = (
    "a Constraint holds a weighted sum over the objects it names to its right-hand side, "
    "which PyPSA's GlobalConstraint cannot express, so the limit is not carried"
)

# PLEXOS states which way a Constraint binds as one integer.
_SENSES: dict[float, ConstraintSense] = {
    -1.0: ConstraintSense.AT_MOST,
    0.0: ConstraintSense.EXACTLY,
    1.0: ConstraintSense.AT_LEAST,
}
_UNSTATED_SENSE = "unstated"

# The right-hand side properties, each with the span it holds the sum over.
_PERIODS: dict[str, ConstraintPeriod] = {
    PlexosProperty.RHS: ConstraintPeriod.HORIZON,
    PlexosProperty.RHS_HOUR: ConstraintPeriod.HOUR,
    PlexosProperty.RHS_DAY: ConstraintPeriod.DAY,
    PlexosProperty.RHS_WEEK: ConstraintPeriod.WEEK,
    PlexosProperty.RHS_MONTH: ConstraintPeriod.MONTH,
    PlexosProperty.RHS_YEAR: ConstraintPeriod.YEAR,
}

_NO_COEFFICIENT = "no coefficient"


@dataclass(frozen=True)
class _Term:
    """One object a Constraint weights, and the coefficient it is weighted by.

    A member the Constraint states no coefficient for still stands in the sum, so the
    coefficient and the property naming it are both optional.
    """

    member: ClassMember
    coefficient_property: str | None
    coefficient: float | None


@dataclass(frozen=True)
class _Constraint:
    name: str
    sense: ConstraintSense | None
    terms: tuple[_Term, ...]
    right_hand_sides: dict[str, float]
    units: dict[str, str | None]
    applies_to_expansion_plan: bool | None


@dataclass(frozen=True)
class _Outcome:
    """One Constraint and the record it travels as, which is None where it states too little."""

    constraint: _Constraint
    record: ConstraintExtension | None


def map_constraints(state: State, recorder: ScopedRecorder) -> None:
    constraints = _read_constraints(state)
    if not constraints:
        return
    outcomes = [_Outcome(constraint, _carry(constraint)) for constraint in constraints]
    reporter = SourceReporter(recorder)
    for outcome in outcomes:
        _record(reporter, outcome)
    append_extensions(
        state.destination_extensions,
        ExtensionKind.CONSTRAINT,
        [outcome.record for outcome in outcomes if outcome.record is not None],
    )
    _warn(constraints)


def _read_constraints(state: State) -> list[_Constraint]:
    names = _constraint_names(state)
    if not names:
        return []
    properties = state.source_topology[PlexosResolvedTable.PROPERTIES]
    scalars = collapse_properties_by_object(properties, PlexosClass.CONSTRAINT)
    units = collapse_units_by_object(properties, PlexosClass.CONSTRAINT)
    coefficients = collapse_member_properties(properties, PlexosClass.CONSTRAINT)
    members = relate_all_children(
        state.source_topology[PlexosResolvedTable.MEMBERSHIPS], PlexosClass.CONSTRAINT
    )
    return [
        _read_one(name, scalars, units, coefficients.get(name, {}), members.get(name, []))
        for name in names
    ]


def _read_one(
    name: str,
    scalars: ObjectProperties,
    units: ObjectUnits,
    coefficients: MemberProperties,
    members: list[ClassMember],
) -> _Constraint:
    stated = scalars.get(name, {})
    return _Constraint(
        name=name,
        sense=_read_sense(stated),
        terms=_build_terms(members, coefficients),
        right_hand_sides={
            property_name: stated[property_name]
            for property_name in _PERIODS
            if property_name in stated
        },
        units=units.get(name, {}),
        applies_to_expansion_plan=_read_plan_flag(stated),
    )


def _build_terms(members: list[ClassMember], coefficients: MemberProperties) -> tuple[_Term, ...]:
    """One term per coefficient a member is weighted by, and a bare term where it has none.

    A coefficient can name a member the memberships do not, so the two sources are read
    together and the result is ordered by class, then by name, then by property.
    """
    named = sorted(set(members) | set(coefficients))
    terms: list[_Term] = []
    for member in named:
        weights = coefficients.get(member, {})
        if not weights:
            terms.append(_Term(member, None, None))
            continue
        terms.extend(
            _Term(member, property_name, weights[property_name])
            for property_name in sorted(weights)
        )
    return tuple(terms)


def _constraint_names(state: State) -> list[str]:
    constraints = state.source_topology.get(PlexosClass.CONSTRAINT)
    if constraints is None:
        return []
    frame = constraints.select(PlexosObjectCol.NAME).collect()
    names: list[str] = frame[PlexosObjectCol.NAME].to_list()
    return names


def _read_sense(stated: dict[str, float]) -> ConstraintSense | None:
    code = stated.get(PlexosProperty.SENSE)
    return None if code is None else _SENSES.get(code)


def _read_plan_flag(stated: dict[str, float]) -> bool | None:
    flag = stated.get(PlexosProperty.INCLUDE_IN_LT_PLAN)
    return None if flag is None else is_plexos_true(flag)


def _carry(constraint: _Constraint) -> ConstraintExtension | None:
    """The sidecar record, or None where the constraint states too little to hold anything to.

    A limit needs both a sense and a right-hand side: without either there is no inequality
    to state, whatever the objects it names.
    """
    if constraint.sense is None or not constraint.right_hand_sides:
        return None
    return ConstraintExtension(
        name=constraint.name,
        sense=constraint.sense,
        limits=[
            ConstraintLimit(
                period=_PERIODS[property_name],
                value=value,
                unit=constraint.units.get(property_name),
            )
            for property_name, value in constraint.right_hand_sides.items()
        ],
        members=[_member(term) for term in constraint.terms],
        applies_to_expansion_plan=constraint.applies_to_expansion_plan,
    )


def _member(term: _Term) -> ConstraintMember:
    return ConstraintMember(
        name=term.member.name,
        member_class=term.member.member_class,
        coefficient=term.coefficient,
        coefficient_property=term.coefficient_property,
    )


def _record(reporter: SourceReporter, outcome: _Outcome) -> None:
    constraint = outcome.constraint
    carried = _CARRIED_NOTE if outcome.record is not None else _NOT_CARRIED_NOTE
    note = f"{carried}. {_describe(constraint)}"
    if not constraint.right_hand_sides:
        reporter.record_dropped(_source(constraint.name, None, None), note)
        return
    for property_name, value in constraint.right_hand_sides.items():
        unit = constraint.units.get(property_name)
        reporter.record_dropped(_source(constraint.name, property_name, value, unit), note)


def _source(
    name: str, attribute: str | None, value: object, unit: str | None = None
) -> SourceValue:
    return SourceValue(PlexosClass.CONSTRAINT, name, attribute, value, unit)


def _describe(constraint: _Constraint) -> str:
    """The sense the Constraint binds in, and the weighted sum it binds."""
    sense = constraint.sense or _UNSTATED_SENSE
    if not constraint.terms:
        return f"Sense {sense}, over no objects"
    return (
        f"Sense {sense} over {len(constraint.terms)} term(s): "
        f"{name_a_few(_describe_term(term) for term in constraint.terms)}"
    )


def _describe_term(term: _Term) -> str:
    if term.coefficient is None:
        return f"{term.member.member_class} {term.member.name} with {_NO_COEFFICIENT}"
    return (
        f"{term.coefficient} x {term.member.member_class} {term.member.name} "
        f"({term.coefficient_property})"
    )


def _warn(constraints: list[_Constraint]) -> None:
    log.warning(
        "plexos: %s Constraint(s) limit what the model may dispatch and the network file "
        "enforces none of them; each one the translator can read travels in the extensions "
        "sidecar: %s",
        len(constraints),
        name_a_few(sorted(constraint.name for constraint in constraints)),
    )
