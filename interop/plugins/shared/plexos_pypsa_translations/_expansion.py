"""What a PLEXOS object may build, and what building it costs.

A Generator, a Battery and a pumped-storage turbine all state a build the same way, so each
path hands this module the rated power of one unit beside the rated power the object already
has, and reads the destination decisions back.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from interop.plugins.shared.constants import (
    UNIT_DOLLARS_PER_MW,
    UNIT_DOLLARS_PER_MW_YEAR,
    UNIT_MW,
    UNIT_YEARS,
)
from interop.plugins.shared.plexos_constants import PlexosClass, PlexosProperty
from interop.plugins.shared.plexos_pypsa_translations._shared import as_rate
from interop.plugins.shared.plexos_pypsa_translations.constants import (
    DIRECT_DERIVATION,
    EXT_TECHNICAL_LIFE_FIELD,
    EXT_UNIT_SIZE_FIELD,
    NOTHING_TO_BUILD,
)
from interop.plugins.shared.plexos_pypsa_translations.decisions import (
    ComponentReporter,
    Decision,
    MappedColumns,
    SourceValue,
    maps_to,
)
from interop.plugins.shared.pypsa_constants import PyPSAGeneratorCol
from interop.plugins.shared.warning_text import name_a_few

log = logging.getLogger(__name__)

NOTHING_TO_REPORT = Decision.unreported(None)

NOTHING_BUILT_DERIVATION = "Units is zero, so none of the rated power is built yet"

P_NOM_CANDIDATE_DERIVATION = (
    "the object has no units yet, so its nominal power is the capacity it may build: "
    "one unit's rated power x Max Units Built"
)

_EXTENDABLE_DERIVATION = "Max Units Built above zero is what makes an object a candidate"
_NOT_EXTENDABLE_NOTE = "the object states no Max Units Built, so its capacity is fixed"
_P_NOM_MIN_DERIVATION = "the rated power the object already has, which a build cannot take away"
_P_NOM_MAX_DERIVATION = "the rated power it has + one unit's rated power x Max Units Built"
_DISCOUNT_RATE_DERIVATION = "WACC, read as a fraction where the model states a percentage"
_UNIT_SIZE_DERIVATION = (
    "PyPSA sizes a candidate by p_nom_max alone, so what one unit of it is travels beside it"
)
_TECHNICAL_LIFE_DERIVATION = (
    "PyPSA's one lifetime holds the capital recovery period, so the technology lifetime "
    "travels beside it"
)
_NO_BUILD_COST_NOTE = (
    "a candidate with no Build Cost prices building nothing, so an expansion would take it for free"
)
_NO_WACC_NOTE = (
    "a candidate with no WACC gives PyPSA no discount rate to annuitise its Build Cost over, "
    "so PyPSA refuses the network"
)
_NO_ECONOMIC_LIFE_NOTE = (
    "a candidate with no Economic Life gives PyPSA no period to annuitise its Build Cost over, "
    "so PyPSA prices the build as a perpetuity"
)

UNIT_SIZE_COLUMN = MappedColumns((EXT_UNIT_SIZE_FIELD,), UNIT_MW)
TECHNICAL_LIFE_COLUMN = MappedColumns((EXT_TECHNICAL_LIFE_FIELD,), UNIT_YEARS)


@dataclass(frozen=True)
class RatedCapacity:
    """The rated power an object already has, beside the rated power of one unit of it."""

    existing: Decision
    unit_size: Decision


@dataclass(frozen=True)
class CandidateSource:
    """One staged PLEXOS object as the expansion rule reads it."""

    plexos_class: PlexosClass
    name: str
    props: dict[str, float]
    stated_units: dict[str, str | None]
    rated: RatedCapacity

    @property
    def max_units_built(self) -> float:
        return self.props.get(PlexosProperty.MAX_UNITS_BUILT, NOTHING_TO_BUILD)

    @property
    def is_candidate(self) -> bool:
        return self.max_units_built > NOTHING_TO_BUILD

    def name_units_built(self) -> SourceValue:
        return SourceValue(
            self.plexos_class, self.name, PlexosProperty.MAX_UNITS_BUILT, self.max_units_built
        )


@dataclass(frozen=True)
class ExpansionDecisions:
    p_nom_extendable: Decision = maps_to(PyPSAGeneratorCol.P_NOM_EXTENDABLE)
    p_nom_min: Decision = maps_to(PyPSAGeneratorCol.P_NOM_MIN, unit=UNIT_MW)
    p_nom_max: Decision = maps_to(PyPSAGeneratorCol.P_NOM_MAX, unit=UNIT_MW)
    overnight_cost: Decision = maps_to(PyPSAGeneratorCol.OVERNIGHT_COST, unit=UNIT_DOLLARS_PER_MW)
    discount_rate: Decision = maps_to(PyPSAGeneratorCol.DISCOUNT_RATE)
    lifetime: Decision = maps_to(PyPSAGeneratorCol.LIFETIME, unit=UNIT_YEARS)
    fom_cost: Decision = maps_to(PyPSAGeneratorCol.FOM_COST, unit=UNIT_DOLLARS_PER_MW_YEAR)
    # What the sidecar carries because the network file has no column for it.
    unit_size: Decision = NOTHING_TO_REPORT
    technical_life: Decision = NOTHING_TO_REPORT


FIXED_CAPACITY = ExpansionDecisions(
    p_nom_extendable=Decision.default(False, _NOT_EXTENDABLE_NOTE),  # noqa: FBT003
    p_nom_min=NOTHING_TO_REPORT,
    p_nom_max=NOTHING_TO_REPORT,
    overnight_cost=NOTHING_TO_REPORT,
    discount_rate=NOTHING_TO_REPORT,
    lifetime=NOTHING_TO_REPORT,
    fom_cost=NOTHING_TO_REPORT,
)


def derive_expansion(source: CandidateSource) -> ExpansionDecisions:
    if not source.is_candidate:
        return FIXED_CAPACITY
    rated = source.rated
    built = source.name_units_built()
    return ExpansionDecisions(
        p_nom_extendable=Decision.derived(True, [built], _EXTENDABLE_DERIVATION),
        p_nom_min=Decision.derived(
            rated.existing.value, rated.existing.sources, _P_NOM_MIN_DERIVATION
        ),
        p_nom_max=Decision.derived(
            rated.existing.value + rated.unit_size.value * source.max_units_built,
            gather_sources(rated.existing.sources, rated.unit_size.sources, [built]),
            _P_NOM_MAX_DERIVATION,
        ),
        overnight_cost=_from_property(
            source, PlexosProperty.BUILD_COST, UNIT_DOLLARS_PER_MW, DIRECT_DERIVATION
        ),
        discount_rate=_discount_rate(source),
        lifetime=_from_property(
            source, PlexosProperty.ECONOMIC_LIFE, UNIT_YEARS, DIRECT_DERIVATION
        ),
        fom_cost=_from_property(
            source, PlexosProperty.FOM_CHARGE, UNIT_DOLLARS_PER_MW_YEAR, DIRECT_DERIVATION
        ),
        unit_size=Decision.derived(
            rated.unit_size.value, rated.unit_size.sources, _UNIT_SIZE_DERIVATION
        ),
        technical_life=_from_property(
            source, PlexosProperty.TECHNICAL_LIFE, UNIT_YEARS, _TECHNICAL_LIFE_DERIVATION
        ),
    )


def derive_buildable(source: CandidateSource) -> Decision:
    """The capacity a candidate may build, which stands as its p_nom while it has none.

    PyPSA optimises ``p_nom_opt`` between ``p_nom_min`` and ``p_nom_max`` and reads ``p_nom``
    only for an object whose capacity is fixed, so what stands here does not bind the
    dispatch. It is what every per-unit field on the component is read against --
    ``p_min_pu``, a ramp limit, an availability profile stated in MW -- and against nothing
    each of those would come out at zero.
    """
    return Decision.derived(
        source.rated.unit_size.value * source.max_units_built,
        [*source.rated.unit_size.sources, source.name_units_built()],
        P_NOM_CANDIDATE_DERIVATION,
    )


def derive_p_nom(source: CandidateSource) -> Decision:
    if source.rated.existing.value or not source.is_candidate:
        return source.rated.existing
    return derive_buildable(source)


@dataclass(frozen=True)
class UnpricedBuild:
    """A property a candidate has to state before PyPSA can price building it."""

    plexos_property: str
    unit: str | None
    note: str


_PRICES_A_BUILD = (
    UnpricedBuild(PlexosProperty.BUILD_COST, UNIT_DOLLARS_PER_MW, _NO_BUILD_COST_NOTE),
    UnpricedBuild(PlexosProperty.WACC, None, _NO_WACC_NOTE),
    UnpricedBuild(PlexosProperty.ECONOMIC_LIFE, UNIT_YEARS, _NO_ECONOMIC_LIFE_NOTE),
)


@dataclass(frozen=True)
class UnpricedCandidate:
    """One candidate left out, and the property it left out that priced its build."""

    plexos_class: PlexosClass
    name: str
    unpriced: UnpricedBuild

    @property
    def source(self) -> SourceValue:
        return SourceValue(
            self.plexos_class, self.name, self.unpriced.plexos_property, None, self.unpriced.unit
        )

    @property
    def note(self) -> str:
        return self.unpriced.note


def find_unpriced_build(
    plexos_class: PlexosClass, name: str, props: dict[str, float]
) -> UnpricedCandidate | None:
    """The first property a candidate leaves out that stops PyPSA pricing its build."""
    if props.get(PlexosProperty.MAX_UNITS_BUILT, NOTHING_TO_BUILD) <= NOTHING_TO_BUILD:
        return None
    unpriced = next((one for one in _PRICES_A_BUILD if one.plexos_property not in props), None)
    return None if unpriced is None else UnpricedCandidate(plexos_class, name, unpriced)


def warn_unpriced_builds(candidates: Sequence[UnpricedCandidate]) -> None:
    """One warning per class and property a candidate left out, naming a few of the objects."""
    by_property: dict[tuple[str, str], list[str]] = {}
    for one in candidates:
        key = (one.plexos_class, one.unpriced.plexos_property)
        by_property.setdefault(key, []).append(one.name)
    for (plexos_class, plexos_property), names in sorted(by_property.items()):
        log.warning(
            "plexos: %d candidate %s(s) state no %s, so each is left out. Each one: %s",
            len(names),
            plexos_class,
            plexos_property,
            name_a_few(sorted(names)),
        )


def record_expansion_extensions(
    name: str, expansion: ExpansionDecisions, reporter: ComponentReporter
) -> None:
    reporter.record(name, UNIT_SIZE_COLUMN, expansion.unit_size)
    reporter.record(name, TECHNICAL_LIFE_COLUMN, expansion.technical_life)


def read_sidecar_value(decision: Decision) -> float | None:
    return None if decision.value is None else float(decision.value)


def gather_sources(*groups: tuple[SourceValue, ...] | list[SourceValue]) -> list[SourceValue]:
    """Every source of several values in order, naming a source shared by two of them once."""
    gathered: dict[SourceValue, None] = {}
    for group in groups:
        for source in group:
            gathered[source] = None
    return list(gathered)


def _discount_rate(source: CandidateSource) -> Decision:
    wacc = source.props.get(PlexosProperty.WACC)
    rate = as_rate(wacc, source.stated_units.get(PlexosProperty.WACC))
    if rate is None:
        return NOTHING_TO_REPORT
    stated = SourceValue(source.plexos_class, source.name, PlexosProperty.WACC, wacc)
    return Decision.derived(rate, [stated], _DISCOUNT_RATE_DERIVATION)


def _from_property(
    source: CandidateSource, plexos_property: str, unit: str | None, derivation: str
) -> Decision:
    value = source.props.get(plexos_property)
    if value is None:
        return NOTHING_TO_REPORT
    stated = SourceValue(source.plexos_class, source.name, plexos_property, value, unit)
    return Decision.derived(value, [stated], derivation)
