"""What a PLEXOS object may build, and what building it costs.

A Generator, a Battery and a pumped-storage turbine all state a build the same way, so each
path hands this module the rated power of one unit beside the rated power the object already
has, and reads the destination decisions back.
"""

from __future__ import annotations

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

NOT_A_CANDIDATE = Decision.unreported(None)

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

UNIT_SIZE_COLUMN = MappedColumns((EXT_UNIT_SIZE_FIELD,), UNIT_MW)
TECHNICAL_LIFE_COLUMN = MappedColumns((EXT_TECHNICAL_LIFE_FIELD,), UNIT_YEARS)


@dataclass(frozen=True)
class RatedCapacity:
    """The rated power an object already has, beside the rated power of one unit of it.

    The two differ wherever a model states more than one unit, and wherever a candidate
    states no unit at all.
    """

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
    unit_size: Decision = NOT_A_CANDIDATE
    technical_life: Decision = NOT_A_CANDIDATE

    @property
    def is_candidate(self) -> bool:
        return bool(self.p_nom_extendable.value)


FIXED_CAPACITY = ExpansionDecisions(
    p_nom_extendable=Decision.default(False, _NOT_EXTENDABLE_NOTE),  # noqa: FBT003
    p_nom_min=NOT_A_CANDIDATE,
    p_nom_max=NOT_A_CANDIDATE,
    overnight_cost=NOT_A_CANDIDATE,
    discount_rate=NOT_A_CANDIDATE,
    lifetime=NOT_A_CANDIDATE,
    fom_cost=NOT_A_CANDIDATE,
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
    """The capacity a candidate may build, which stands as its p_nom while it has none."""
    return Decision.derived(
        source.rated.unit_size.value * source.max_units_built,
        [*source.rated.unit_size.sources, source.name_units_built()],
        P_NOM_CANDIDATE_DERIVATION,
    )


def derive_p_nom(source: CandidateSource) -> Decision:
    """What the object has, or what it may build where it has nothing yet."""
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
)


def find_unpriced_build(props: dict[str, float]) -> UnpricedBuild | None:
    """The first property a candidate leaves out that stops PyPSA pricing its build."""
    if props.get(PlexosProperty.MAX_UNITS_BUILT, NOTHING_TO_BUILD) <= NOTHING_TO_BUILD:
        return None
    return next((one for one in _PRICES_A_BUILD if one.plexos_property not in props), None)


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
        return NOT_A_CANDIDATE
    stated = SourceValue(source.plexos_class, source.name, PlexosProperty.WACC, wacc)
    return Decision.derived(rate, [stated], _DISCOUNT_RATE_DERIVATION)


def _from_property(
    source: CandidateSource, plexos_property: str, unit: str | None, derivation: str
) -> Decision:
    value = source.props.get(plexos_property)
    if value is None:
        return NOT_A_CANDIDATE
    stated = SourceValue(source.plexos_class, source.name, plexos_property, value, unit)
    return Decision.derived(value, [stated], derivation)
