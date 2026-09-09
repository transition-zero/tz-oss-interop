"""PLEXOS Constraint -> the translation report.

A PLEXOS Constraint holds a weighted sum over the objects it names to a right-hand side.
It weights each object by a coefficient stated on the membership, and it may state the
right-hand side over an hour, a day, a week, a month, a year, or the whole horizon.

PyPSA's GlobalConstraint limits one carrier over the whole horizon and has no way to name
a set of components, so no shape of Constraint has a home in the network file.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.plexos_constants import (
    PlexosClass,
    PlexosObjectCol,
    PlexosProperty,
    PlexosResolvedTable,
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

_NOT_CARRIED_NOTE = (
    "a Constraint holds a weighted sum over the objects it names to its right-hand side, "
    "which PyPSA's GlobalConstraint cannot express, so the limit is not carried"
)

# PLEXOS states which way a Constraint binds as one integer.
_SENSES: dict[float, str] = {-1.0: "<=", 0.0: "==", 1.0: ">="}
_UNSTATED_SENSE = "unstated"

_RIGHT_HAND_SIDES = (
    PlexosProperty.RHS,
    PlexosProperty.RHS_HOUR,
    PlexosProperty.RHS_DAY,
    PlexosProperty.RHS_WEEK,
    PlexosProperty.RHS_MONTH,
    PlexosProperty.RHS_YEAR,
)

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
    sense: str
    terms: tuple[_Term, ...]
    right_hand_sides: dict[str, float]
    units: dict[str, str | None]


def map_constraints(state: State, recorder: ScopedRecorder) -> None:
    constraints = _read_constraints(state)
    if not constraints:
        return
    reporter = SourceReporter(recorder)
    for constraint in constraints:
        _record(reporter, constraint)
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
            for property_name in _RIGHT_HAND_SIDES
            if property_name in stated
        },
        units=units.get(name, {}),
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


def _read_sense(stated: dict[str, float]) -> str:
    code = stated.get(PlexosProperty.SENSE)
    return _UNSTATED_SENSE if code is None else _SENSES.get(code, _UNSTATED_SENSE)


def _record(reporter: SourceReporter, constraint: _Constraint) -> None:
    note = f"{_NOT_CARRIED_NOTE}. {_describe(constraint)}"
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
    if not constraint.terms:
        return f"Sense {constraint.sense}, over no objects"
    return (
        f"Sense {constraint.sense} over {len(constraint.terms)} term(s): "
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
        "plexos: %s Constraint(s) limit what the model may dispatch, and PyPSA has no home "
        "for any of them, so none is enforced: %s",
        len(constraints),
        name_a_few(sorted(constraint.name for constraint in constraints)),
    )
