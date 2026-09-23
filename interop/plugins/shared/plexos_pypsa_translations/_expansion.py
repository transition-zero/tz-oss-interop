"""What a PLEXOS object may build, and what building it costs."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from typing import Any

from interop.plugins.shared.constants import (
    UNIT_DOLLARS_PER_MW,
    UNIT_DOLLARS_PER_MW_YEAR,
    UNIT_MW,
    UNIT_YEARS,
)
from interop.plugins.shared.plexos_constants import PlexosClass, PlexosProperty, is_plexos_true
from interop.plugins.shared.plexos_pypsa_translations._shared import read_as_rate
from interop.plugins.shared.plexos_pypsa_translations.constants import (
    DEFAULT_UNITS,
    DIRECT_DERIVATION,
    EXT_FOM_CHARGE_FIELD,
    EXT_TECHNICAL_LIFE_FIELD,
    EXT_UNIT_SIZE_FIELD,
    NOTHING_TO_BUILD,
)
from interop.plugins.shared.plexos_pypsa_translations.decisions import (
    ComponentReporter,
    Decision,
    MappedColumns,
    SkipGroup,
    SkippedComponent,
    SourceValue,
    maps_to,
    warn_about_skips,
)
from interop.plugins.shared.pypsa_constants import PyPSAGeneratorCol

NOTHING_TO_REPORT = Decision.unreported(None)

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
_FOM_CHARGE_DERIVATION = (
    "PyPSA's fom_cost is a charge for the whole modelled horizon, not a yearly one, so a "
    "yearly charge travels beside the component instead"
)
_NO_BUILD_COST_NOTE = (
    "a candidate with no Build Cost prices building nothing, so an expansion would take it for free"
)
_NO_WACC_NOTE = (
    "a candidate with no WACC gives no discount rate to annuitise its Build Cost over, "
    "so PyPSA refuses the network"
)
_NO_ECONOMIC_LIFE_NOTE = (
    "a candidate with no Economic Life gives no period to annuitise its Build Cost over, "
    "so PyPSA prices the build as a perpetuity"
)
_OUT_OF_THE_PLAN_NOTE = (
    "the model leaves this object out of its long-term plan, so the plan may build none of it"
)
_NO_BUILD_COST_REASON = f"state no {PlexosProperty.BUILD_COST}"
_NO_WACC_REASON = f"state no {PlexosProperty.WACC}"
_NO_ECONOMIC_LIFE_REASON = f"state no {PlexosProperty.ECONOMIC_LIFE}"
_OUT_OF_THE_PLAN_REASON = "sit outside the long-term plan"
_BUILD_LEFT_OUT_NOTE = "; the object keeps the capacity it runs and only its build is left out"
_BUILD_LEFT_OUT_OUTCOME = "so each keeps the capacity it runs and none of the build it may make"
_BLOCKED_BUILD_DERIVATION = (
    "the model allows no build for this object, so it keeps the capacity it runs and that "
    "capacity is fixed"
)

UNIT_SIZE_COLUMN = MappedColumns((EXT_UNIT_SIZE_FIELD,), UNIT_MW)
TECHNICAL_LIFE_COLUMN = MappedColumns((EXT_TECHNICAL_LIFE_FIELD,), UNIT_YEARS)
FOM_CHARGE_COLUMN = MappedColumns((EXT_FOM_CHARGE_FIELD,), UNIT_DOLLARS_PER_MW_YEAR)


@dataclass(frozen=True)
class RatedCapacity:
    """The rated power an object already has, beside the rated power of one unit of it."""

    existing: Decision
    unit_size: Decision


@dataclass(frozen=True)
class CandidateSource:
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

    @property
    def rated_unit_count(self) -> float:
        """How many units the nominal power stands for.

        It is what the object runs, or what a candidate running none of them may build, which
        is the same reading ``derive_p_nom`` takes.
        """
        if self.rated.existing.value:
            return self.props.get(PlexosProperty.UNITS, DEFAULT_UNITS)
        return self.max_units_built

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
    # What the sidecar carries because the network file has no column for it.
    unit_size: Decision = NOTHING_TO_REPORT
    technical_life: Decision = NOTHING_TO_REPORT
    fom_charge: Decision = NOTHING_TO_REPORT
    dropped_build: SkippedComponent | None = None


FIXED_CAPACITY = ExpansionDecisions(
    p_nom_extendable=Decision.default(False, _NOT_EXTENDABLE_NOTE),  # noqa: FBT003
    p_nom_min=NOTHING_TO_REPORT,
    p_nom_max=NOTHING_TO_REPORT,
    overnight_cost=NOTHING_TO_REPORT,
    discount_rate=NOTHING_TO_REPORT,
    lifetime=NOTHING_TO_REPORT,
)


def derive_expansion(source: CandidateSource) -> ExpansionDecisions:
    if not source.is_candidate:
        return FIXED_CAPACITY
    blocking = _find_blocking_rule(source)
    if blocking is not None:
        return _derive_fixed_capacity(source, blocking)
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
        overnight_cost=_read_from_property(
            source, PlexosProperty.BUILD_COST, UNIT_DOLLARS_PER_MW, DIRECT_DERIVATION
        ),
        discount_rate=_derive_discount_rate(source),
        lifetime=_read_from_property(
            source, PlexosProperty.ECONOMIC_LIFE, UNIT_YEARS, DIRECT_DERIVATION
        ),
        unit_size=Decision.derived(
            rated.unit_size.value, rated.unit_size.sources, _UNIT_SIZE_DERIVATION
        ),
        technical_life=_read_from_property(
            source, PlexosProperty.TECHNICAL_LIFE, UNIT_YEARS, _TECHNICAL_LIFE_DERIVATION
        ),
        fom_charge=_read_from_property(
            source, PlexosProperty.FOM_CHARGE, UNIT_DOLLARS_PER_MW_YEAR, _FOM_CHARGE_DERIVATION
        ),
    )


def derive_buildable(source: CandidateSource) -> Decision:
    """PyPSA reads ``p_nom`` only where a capacity is fixed, so this value binds no dispatch.

    Do not leave a candidate's ``p_nom`` at zero. ``p_min_pu``, a ramp limit and an
    availability profile stated in MW are all read against it, and each one comes out at zero
    against nothing.
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


def _is_priced(stated: float | None) -> bool:
    return stated is not None and stated > 0.0


def _is_a_rate(stated: float | None) -> bool:
    """A WACC of zero is the rate of a model that does not discount, so it prices a build."""
    return stated is not None


def _is_in_the_plan(stated: float | None) -> bool:
    """An object saying nothing about the long-term plan is in it."""
    return stated is None or is_plexos_true(stated)


@dataclass(frozen=True)
class BuildRule:
    """A property that decides whether the translator writes a build for an object."""

    plexos_property: str
    unit: str | None
    note: str
    reason: str
    """Completes "N <objects> <reason>" in the one warning this rule speaks with."""

    is_satisfied: Callable[[float | None], bool]

    def allows_a_build(self, props: dict[str, float]) -> bool:
        return self.is_satisfied(props.get(self.plexos_property))


# The plan comes first, so an excluded object reads as excluded rather than as unpriced.
_BUILD_RULES = (
    BuildRule(
        PlexosProperty.INCLUDE_IN_LT_PLAN,
        None,
        _OUT_OF_THE_PLAN_NOTE,
        _OUT_OF_THE_PLAN_REASON,
        _is_in_the_plan,
    ),
    BuildRule(
        PlexosProperty.BUILD_COST,
        UNIT_DOLLARS_PER_MW,
        _NO_BUILD_COST_NOTE,
        _NO_BUILD_COST_REASON,
        _is_priced,
    ),
    BuildRule(PlexosProperty.WACC, None, _NO_WACC_NOTE, _NO_WACC_REASON, _is_a_rate),
    BuildRule(
        PlexosProperty.ECONOMIC_LIFE,
        UNIT_YEARS,
        _NO_ECONOMIC_LIFE_NOTE,
        _NO_ECONOMIC_LIFE_REASON,
        _is_priced,
    ),
)


def find_blocked_candidate(source: CandidateSource) -> SkippedComponent | None:
    """A candidate with nothing running yet that the model allows no build for.

    Its whole capacity is the build, so there is nothing to write once the build goes. An
    object that already runs states capacity a dispatch model needs, so it stays.
    """
    if source.rated.existing.value or not source.is_candidate:
        return None
    blocking = _find_blocking_rule(source)
    if blocking is None:
        return None
    return SkippedComponent(
        source=_name_blocking_property(source, blocking),
        note=blocking.note,
        warn_with=SkipGroup(
            counted=f"candidate {source.plexos_class}(s)",
            reason=blocking.reason,
        ),
    )


def record_expansion(name: str, expansion: ExpansionDecisions, reporter: ComponentReporter) -> None:
    reporter.record(name, UNIT_SIZE_COLUMN, expansion.unit_size)
    reporter.record(name, TECHNICAL_LIFE_COLUMN, expansion.technical_life)
    reporter.record(name, FOM_CHARGE_COLUMN, expansion.fom_charge)
    record_expansion_notes(reporter, name, expansion)


def record_expansion_notes(reporter: Any, name: str, expansion: ExpansionDecisions) -> None:
    """Why a build was left out, which is a reading of the model rather than of a destination."""
    if expansion.dropped_build is not None:
        reporter.record_dropped(expansion.dropped_build.source, expansion.dropped_build.note)


def warn_about_dropped_builds(expansions: Iterable[ExpansionDecisions]) -> None:
    """One line for each property that left a running object's build unpriced."""
    warn_about_skips([one.dropped_build for one in expansions if one.dropped_build is not None])


def read_sidecar_value(decision: Decision) -> float | None:
    return None if decision.value is None else float(decision.value)


def gather_sources(*groups: tuple[SourceValue, ...] | list[SourceValue]) -> list[SourceValue]:
    """Every source of several values in order, naming a source shared by two of them once."""
    gathered: dict[SourceValue, None] = {}
    for group in groups:
        for source in group:
            gathered[source] = None
    return list(gathered)


def _find_blocking_rule(source: CandidateSource) -> BuildRule | None:
    return next((one for one in _BUILD_RULES if not one.allows_a_build(source.props)), None)


def _derive_fixed_capacity(source: CandidateSource, blocking: BuildRule) -> ExpansionDecisions:
    return replace(
        FIXED_CAPACITY,
        p_nom_extendable=Decision.derived(
            False,  # noqa: FBT003
            [source.name_units_built()],
            _BLOCKED_BUILD_DERIVATION,
        ),
        dropped_build=SkippedComponent(
            source=_name_blocking_property(source, blocking),
            note=blocking.note + _BUILD_LEFT_OUT_NOTE,
            warn_with=SkipGroup(
                counted=f"{source.plexos_class}(s) that already run",
                reason=blocking.reason,
                outcome=_BUILD_LEFT_OUT_OUTCOME,
            ),
        ),
    )


def _name_blocking_property(source: CandidateSource, blocking: BuildRule) -> SourceValue:
    return SourceValue(
        source.plexos_class,
        source.name,
        blocking.plexos_property,
        source.props.get(blocking.plexos_property),
        blocking.unit,
    )


def _derive_discount_rate(source: CandidateSource) -> Decision:
    """The event names the WACC as the model wrote it, so the divide by 100 is visible."""
    wacc = source.props.get(PlexosProperty.WACC)
    stated_unit = source.stated_units.get(PlexosProperty.WACC)
    rate = read_as_rate(wacc, stated_unit)
    if rate is None:
        return NOTHING_TO_REPORT
    stated = SourceValue(source.plexos_class, source.name, PlexosProperty.WACC, wacc, stated_unit)
    return Decision.derived(rate, [stated], _DISCOUNT_RATE_DERIVATION)


def _read_from_property(
    source: CandidateSource, plexos_property: str, unit: str | None, derivation: str
) -> Decision:
    value = source.props.get(plexos_property)
    if value is None:
        return NOTHING_TO_REPORT
    stated = SourceValue(source.plexos_class, source.name, plexos_property, value, unit)
    return Decision.derived(value, [stated], derivation)
