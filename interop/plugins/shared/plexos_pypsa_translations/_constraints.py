"""PLEXOS Constraint -> the translation report.

A PLEXOS Constraint holds a weighted sum over the objects it names to a right-hand side.
It weights each object by a coefficient stated on the membership, and it may state the
right-hand side over an hour, a day, a week, a month, a year, or the whole horizon.

PyPSA's GlobalConstraint limits one carrier over the whole horizon and has no way to name
a set of components, so no shape of Constraint has a home in the network file. Nothing is
carried, and each right-hand side is recorded against the object stating it, so a reader
sees which limits the network is not holding to rather than having to notice their absence.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.plexos_constants import (
    PlexosClass,
    PlexosCollection,
    PlexosObjectCol,
    PlexosProperty,
    PlexosResolvedTable,
)
from interop.plugins.shared.plexos_pypsa_translations._shared import (
    ObjectProperties,
    ObjectUnits,
    collapse_membership_properties_by_parent,
    collapse_properties_by_object,
    collapse_units_by_object,
    relate_children,
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

# The right-hand sides one Constraint may state, each over its own period.
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
class _Constraint:
    """One PLEXOS Constraint: which way it binds, over what, and to which right-hand sides.

    ``units`` holds the unit the model states each of its properties in, so a right-hand
    side is reported in the model's own terms rather than in one inferred from the
    coefficient beside it.
    """

    name: str
    sense: str
    coefficients: tuple[str, ...]
    members: tuple[str, ...]
    right_hand_sides: dict[str, float]
    units: dict[str, str | None]


def map_constraints(state: State, recorder: ScopedRecorder) -> None:
    """Report every PLEXOS Constraint, none of which the network file can hold."""
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
    coefficients = collapse_membership_properties_by_parent(
        properties, PlexosClass.CONSTRAINT, PlexosCollection.GENERATORS
    )
    members = relate_children(
        state.source_topology[PlexosResolvedTable.MEMBERSHIPS],
        PlexosClass.CONSTRAINT,
        PlexosCollection.GENERATORS,
    )
    return [_read_one(name, scalars, units, coefficients, members.get(name, [])) for name in names]


def _read_one(
    name: str,
    scalars: ObjectProperties,
    units: ObjectUnits,
    coefficients: ObjectProperties,
    members: list[str],
) -> _Constraint:
    stated = scalars.get(name, {})
    return _Constraint(
        name=name,
        sense=_read_sense(stated),
        coefficients=tuple(sorted(coefficients.get(name, {}))),
        members=tuple(members),
        right_hand_sides={
            property_name: stated[property_name]
            for property_name in _RIGHT_HAND_SIDES
            if property_name in stated
        },
        units=units.get(name, {}),
    )


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
    """One event per right-hand side stated, or one against the object where it states none."""
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
    """Which way the Constraint binds, over which Generators, and by which coefficient.

    A Constraint can name objects of any class. Only the Generators it names are read, so a
    Constraint over anything else is reported with nothing listed beside its sense.
    """
    if not constraint.members:
        return f"Sense {constraint.sense}, over no {PlexosClass.GENERATOR}"
    coefficients = " and ".join(constraint.coefficients) or _NO_COEFFICIENT
    return (
        f"Sense {constraint.sense} over {len(constraint.members)} "
        f"{PlexosClass.GENERATOR}(s) by {coefficients}: "
        f"{name_a_few(sorted(constraint.members))}"
    )


def _warn(constraints: list[_Constraint]) -> None:
    log.warning(
        "plexos: %s Constraint(s) limit what the model may dispatch, and PyPSA has no home "
        "for any of them, so none is enforced: %s",
        len(constraints),
        name_a_few(sorted(constraint.name for constraint in constraints)),
    )
