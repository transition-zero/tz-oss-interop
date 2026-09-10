"""What a PLEXOS object may build, and what building it costs."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace

from interop.plugins.shared.constants import (
    UNIT_DOLLARS_PER_MW,
    UNIT_DOLLARS_PER_MW_YEAR,
    UNIT_MW,
    UNIT_YEARS,
)
from interop.plugins.shared.plexos_constants import PlexosClass, PlexosProperty
from interop.plugins.shared.plexos_pypsa_translations._shared import as_rate
from interop.plugins.shared.plexos_pypsa_translations.constants import (
    DEFAULT_UNITS,
    DIRECT_DERIVATION,
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
    "a candidate with no WACC gives PyPSA no discount rate to annuitise its Build Cost over, "
    "so PyPSA refuses the network"
)
_NO_ECONOMIC_LIFE_NOTE = (
    "a candidate with no Economic Life gives PyPSA no period to annuitise its Build Cost over, "
    "so PyPSA prices the build as a perpetuity"
)
_BUILD_LEFT_OUT_NOTE = "; the object keeps the capacity it runs and only its build is left out"
_BUILD_LEFT_OUT_OUTCOME = "so each keeps the capacity it runs and none of the build it may make"
_UNPRICED_BUILD_DERIVATION = (
    "the model prices no build for this object, so it keeps the capacity it runs and that "
    "capacity is fixed"
)

UNIT_SIZE_COLUMN = MappedColumns(("extensions.unit_size_mw",), UNIT_MW)
TECHNICAL_LIFE_COLUMN = MappedColumns(("extensions.technical_life_years",), UNIT_YEARS)
FOM_CHARGE_COLUMN = MappedColumns(
    ("extensions.fom_charge_per_mw_year",), UNIT_DOLLARS_PER_MW_YEAR
)


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
    unpriced = _find_unpriced_build(source)
    if unpriced is not None:
        return _fixed_at_what_it_runs(source, unpriced)
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
        unit_size=Decision.derived(
            rated.unit_size.value, rated.unit_size.sources, _UNIT_SIZE_DERIVATION
        ),
        technical_life=_from_property(
            source, PlexosProperty.TECHNICAL_LIFE, UNIT_YEARS, _TECHNICAL_LIFE_DERIVATION
        ),
        fom_charge=_from_property(
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


@dataclass(frozen=True)
class UnpricedBuild:
    """A property a candidate has to state before PyPSA can price building it."""

    plexos_property: str
    unit: str | None
    note: str
    zero_is_a_price: bool = False
    """A WACC of zero is the rate of a model that does not discount, so it prices a build."""

    def prices_a_build(self, props: dict[str, float]) -> bool:
        stated = props.get(self.plexos_property)
        if stated is None:
            return False
        return stated > 0.0 or self.zero_is_a_price


_PRICES_A_BUILD = (
    UnpricedBuild(PlexosProperty.BUILD_COST, UNIT_DOLLARS_PER_MW, _NO_BUILD_COST_NOTE),
    UnpricedBuild(PlexosProperty.WACC, None, _NO_WACC_NOTE, zero_is_a_price=True),
    UnpricedBuild(PlexosProperty.ECONOMIC_LIFE, UNIT_YEARS, _NO_ECONOMIC_LIFE_NOTE),
)


def find_unpriced_candidate(source: CandidateSource) -> SkippedComponent | None:
    """A candidate with nothing running yet whose build the model prices nothing for.

    Its whole capacity is the build, so there is nothing to write once the build goes. An
    object that already runs states capacity a dispatch model needs, so it stays.
    """
    if source.rated.existing.value or not source.is_candidate:
        return None
    unpriced = _find_unpriced_build(source)
    if unpriced is None:
        return None
    return SkippedComponent(
        source=_names_unpriced(source, unpriced),
        note=unpriced.note,
        warn_with=SkipGroup(
            counted=f"candidate {source.plexos_class}(s)",
            reason=f"state no {unpriced.plexos_property}",
        ),
    )


def record_expansion(name: str, expansion: ExpansionDecisions, reporter: ComponentReporter) -> None:
    reporter.record(name, UNIT_SIZE_COLUMN, expansion.unit_size)
    reporter.record(name, TECHNICAL_LIFE_COLUMN, expansion.technical_life)
    reporter.record(name, FOM_CHARGE_COLUMN, expansion.fom_charge)
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


def _find_unpriced_build(source: CandidateSource) -> UnpricedBuild | None:
    return next((one for one in _PRICES_A_BUILD if not one.prices_a_build(source.props)), None)


def _fixed_at_what_it_runs(source: CandidateSource, unpriced: UnpricedBuild) -> ExpansionDecisions:
    return replace(
        FIXED_CAPACITY,
        p_nom_extendable=Decision.derived(
            False,  # noqa: FBT003
            [source.name_units_built()],
            _UNPRICED_BUILD_DERIVATION,
        ),
        dropped_build=SkippedComponent(
            source=_names_unpriced(source, unpriced),
            note=unpriced.note + _BUILD_LEFT_OUT_NOTE,
            warn_with=SkipGroup(
                counted=f"{source.plexos_class}(s) that already run",
                reason=f"state no {unpriced.plexos_property}",
                outcome=_BUILD_LEFT_OUT_OUTCOME,
            ),
        ),
    )


def _names_unpriced(source: CandidateSource, unpriced: UnpricedBuild) -> SourceValue:
    return SourceValue(
        source.plexos_class,
        source.name,
        unpriced.plexos_property,
        source.props.get(unpriced.plexos_property),
        unpriced.unit,
    )


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
