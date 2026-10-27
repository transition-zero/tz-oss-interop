"""Everything a destination format cannot hold, in one shape every pipeline shares.

Translation is not one hop. Each hop drops what its destination cannot represent, so what a
hop sets aside travels beside its output and the next hop that has a home for it picks it
up. The document is keyed by kind, and the key fixes every attribute's type. ``name`` is the
only identifier, so a hop matches a record to a component without knowing which framework
wrote it.

Each field's comment says where the concept comes from: one framework, or the frameworks
that share it. A field only one framework carries is absent from the others' records rather
than living in a per-framework compartment. A field carries one quantity in one unit, and
each hop converts at its own edge.

These models are the schema and the runtime contract both. A mapping builds instances, which
mypy checks for field names and types, and a hop carries those instances as they are. The
only conversions are at the file edge, where the document is written and read back.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Generic, Literal, NamedTuple, TypeAlias, TypeVar, get_args, overload

import polars as pl
from pydantic import BaseModel, ConfigDict

from interop.core.extension_records import ByBus as ByBus
from interop.core.extension_records import ByFuel as ByFuel
from interop.core.extension_records import ByPollutant as ByPollutant
from interop.core.extension_records import ByYear as ByYear
from interop.core.extension_records import ExpansionExtension as ExpansionExtension
from interop.core.extension_records import ExtensionRecord as ExtensionRecord
from interop.core.extension_records import FlagByYear as FlagByYear
from interop.core.osemosys_extensions import ActivityExtension as ActivityExtension
from interop.core.osemosys_extensions import ConversionExtension as ConversionExtension
from interop.core.osemosys_extensions import OperatingMode as OperatingMode
from interop.core.osemosys_extensions import (
    RepresentativePeriodExtension as RepresentativePeriodExtension,
)
from interop.core.osemosys_extensions import TechnologyExtension as TechnologyExtension
from interop.core.osemosys_extensions import TechnologyLimits as TechnologyLimits
from interop.core.reporting import EventRecorder
from interop.ports.errors import UserInputError
from interop.ports.outbound.reporting import EventKind, SourceField, TranslationEvent
from interop.ports.warning_text import name_a_few

log = logging.getLogger(__name__)


class ExtensionKind(StrEnum):
    """What a record describes. Neutral: a kind names a concept, not a framework's class."""

    BUS = "bus"  # PyPSA Bus; Sienna ACBus; PLEXOS Node
    # Sienna ThermalStandard, RenewableDispatch, RenewableNonDispatch and HydroDispatch all
    # land here, alongside PyPSA Generator and PLEXOS Generator.
    GENERATOR = "generator"
    LOAD = "load"  # PyPSA Load; Sienna PowerLoad; PLEXOS Region and Node demand
    LINE = "line"  # a branch whose flow follows its impedance: PyPSA, Sienna and PLEXOS Line
    # A branch with a set point: PyPSA Link; Sienna TwoTerminalGenericHVDCLine. PLEXOS has
    # no separate class for it.
    CONTROLLABLE_LINE = "controllable_line"
    STORAGE = "storage"  # PyPSA StorageUnit; Sienna EnergyReservoirStorage; PLEXOS Storage
    # PLEXOS Reserve; Sienna VariableReserve and ConstantReserve. PyPSA has none, which is
    # why the concept needs the sidecar to survive a hop through it.
    RESERVE = "reserve"
    # PLEXOS Constraint. PyPSA's GlobalConstraint limits one carrier over the whole horizon
    # and cannot name a set of components, which is why the concept needs the sidecar to
    # survive a hop through it. Sienna has no equivalent either.
    CONSTRAINT = "constraint"
    NETWORK = "network"  # PyPSA network-level attributes. No Sienna or PLEXOS equivalent.
    # OSeMOSYS only: a span of hours that occurs a number of times in a year.
    REPRESENTATIVE_PERIOD = "representative_period"
    # OSeMOSYS only: the values of a portfolio technology that change from year to year.
    TECHNOLOGY = "technology"
    # A PyPSA Link that turns energy at one bus into energy at another bus, or out of the
    # model; OSeMOSYS states it as a conversion or an export technology; Sienna has no
    # component for it, so the whole record lives here.
    CONVERSION = "conversion"


class ReserveDirection(StrEnum):
    """Which way a reserve moves output."""

    UP = "up"  # Sienna ReserveDirection.UP; PLEXOS raise products, encoded inside Type
    DOWN = "down"  # Sienna ReserveDirection.DOWN; PLEXOS lower products, encoded inside Type
    SYMMETRIC = "symmetric"  # Sienna ReserveDirection.SYMMETRIC. PLEXOS has no equivalent.
    UNKNOWN = "unknown"  # ours: a source code we cannot map


class ReserveKind(StrEnum):
    """Which reserve product this is.

    PLEXOS states it inside the reserve ``Type`` integer; its own decode table names Raise,
    Lower, Regulation, Regulation Raise, Regulation Lower, Replacement, Operational and
    Inertia. Sienna draws the distinction by which component it builds, so it has no field
    to read this from: spinning is ``VariableReserve``, non-spinning is
    ``VariableReserveNonSpinning``.
    """

    SPINNING = "spinning"  # Sienna VariableReserve and ConstantReserve
    NON_SPINNING = "non_spinning"  # Sienna VariableReserveNonSpinning
    REGULATING = "regulating"  # PLEXOS Regulation, Regulation Raise and Regulation Lower
    REPLACEMENT = "replacement"  # PLEXOS Replacement
    OPERATING = "operating"  # PLEXOS Operational
    INERTIA = "inertia"  # PLEXOS Inertia
    # Ours: a source code we cannot map, and a code naming only a direction (PLEXOS's plain
    # Raise and Lower say which way the reserve moves output but not which product it is).
    UNKNOWN = "unknown"


class ConstraintSense(StrEnum):
    """Which way a constraint holds its weighted sum against the right-hand side."""

    AT_MOST = "<="  # PLEXOS Sense -1
    EXACTLY = "=="  # PLEXOS Sense 0
    AT_LEAST = ">="  # PLEXOS Sense 1


class ConstraintPeriod(StrEnum):
    """The span one right-hand side applies over."""

    HORIZON = "horizon"  # PLEXOS RHS
    HOUR = "hour"  # PLEXOS RHS Hour
    DAY = "day"  # PLEXOS RHS Day
    WEEK = "week"  # PLEXOS RHS Week
    MONTH = "month"  # PLEXOS RHS Month
    YEAR = "year"  # PLEXOS RHS Year


class BusExtension(ExtensionRecord):
    # PyPSA Bus.carrier (AC or DC). Sienna ACBus and PLEXOS Node have no carrier field.
    carrier: str | None = None
    # $/MWh. PLEXOS states it on the Region containing the node; Sienna prices it on the load
    # rather than the bus. PyPSA has no field for it at all, so a chain through PyPSA needs
    # this to keep the price a shortfall is charged at.
    value_of_lost_load: float | None = None
    # PyPSA Bus.location; the OSeMOSYS location of a fuel that is not electricity, whose bus
    # Sienna does not hold.
    location: str | None = None


class GeneratorExtension(ActivityExtension):
    # PyPSA Generator.carrier. Sienna states fuel and prime mover instead, and several PyPSA
    # carriers share one (prime_mover, fuel) pair, so the reverse cannot recover this.
    carrier: str | None = None
    # PyPSA Generator.committable. Sienna decides commitment by component type.
    committable: bool | None = None
    # PyPSA only: neither Sienna nor PLEXOS carries a per-component expansion flag.
    p_nom_extendable: bool | None = None
    # PLEXOS only: the generator's category, a grouping string the user chooses.
    category: str | None = None
    # PyPSA Generator.efficiency, which is one megawatt hour out per this much fuel in.
    # Sienna prices the fuel into the cost curve and states no efficiency of its own.
    efficiency: float | None = None
    # Ours: the companion parquet holding what the generator costs per MWh at each snapshot.
    # A Sienna cost curve states one price, so a fuel priced by date has no field here.
    marginal_cost_series: str | None = None
    # t for each MWh that the generator puts out, by pollutant, with the emissions of the fuel
    # that a plant burns; OSeMOSYS only, as PyPSA states Carrier.co2_emissions instead.
    emission_rates_t_per_mwh: ByPollutant | None = None
    # PyPSA Generator.bus, for a generator of a fuel that is not electricity, which Sienna does
    # not hold; OSeMOSYS fuel_supply.
    bus: str | None = None
    # MW of the fuel; PyPSA Generator.p_nom, for a generator that Sienna does not hold.
    p_nom: float | None = None
    # $/MWh of the fuel; PyPSA Generator.marginal_cost, for a generator that Sienna does not hold.
    marginal_cost: float | None = None
    # PyPSA Generator.p_max_pu, for a generator that Sienna does not hold; OSeMOSYS
    # AvailabilityFactor.
    p_max_pu: float | None = None
    # MWh of each fuel for each MWh of electricity, by the bus of the fuel; no PyPSA field, as
    # PyPSA states it as Link.bus0 and Link.efficiency; OSeMOSYS InputActivityRatio.
    fuel_buses: ByBus | None = None
    # $/MWh of electricity without the price of the fuels that fuel_buses names; no PyPSA
    # field, as PyPSA states it as Link.marginal_cost for each MWh of fuel.
    own_marginal_cost: float | None = None
    # t/MWh of electricity, by pollutant, without the emissions of the fuels that fuel_buses
    # names; no PyPSA field; OSeMOSYS EmissionActivityRatio of the plant only.
    own_emission_rates_t_per_mwh: ByPollutant | None = None
    # OSeMOSYS only: the technology and the operating mode that the generator stands for, when
    # it is a mode of a technology that is not a generator, such as an import mode of a line.
    source_technology: str | None = None
    source_mode: str | None = None


class LoadExtension(ExtensionRecord):
    carrier: str | None = None  # PyPSA Load.carrier
    type: str | None = None  # PyPSA Load.type, a free string
    # PyPSA Load.sign, -1 by convention. Sienna PowerLoad is positive-consumption by
    # definition, so it has nothing to state here.
    sign: float | None = None
    # PyPSA Load.bus, for a demand for a fuel that is not electricity, which Sienna does not hold.
    bus: str | None = None
    # MW of the fuel in each snapshot; PyPSA Load.p_set, for a load that Sienna does not hold.
    p_set: float | None = None
    # Ours: the companion parquet holding p_set at each snapshot, where the demand changes.
    p_set_series: str | None = None


class LineExtension(ExtensionRecord):
    carrier: str | None = None  # PyPSA Line.carrier
    # km. PyPSA Line.length and PLEXOS Length. SiennaSchemas Line holds only r, x, b, g,
    # rating and angle_limits, so a length has no home there.
    length: float | None = None
    # PyPSA Line.num_parallel; PLEXOS states the same idea as Units. No Sienna field.
    num_parallel: float | None = None
    s_nom_extendable: bool | None = None  # PyPSA only


class ControllableLineExtension(ActivityExtension):
    carrier: str | None = None  # PyPSA Link.carrier
    # $/MWh. PyPSA Link.marginal_cost, which PLEXOS states as a Wheeling Charge. Sienna
    # prices no flow over a branch, so the charge has no field there.
    marginal_cost: float | None = None
    p_nom_extendable: bool | None = None  # PyPSA only
    # PyPSA Link.p_max_pu. Sienna's active_power_limits_from folds p_nom * p_max_pu into one
    # number, so the split is unrecoverable without this.
    p_max_pu: float | None = None
    # PyPSA Link.p_min_pu. Sienna forces the from-end minimum to zero, so a positive lower
    # bound is lost without this.
    p_min_pu: float | None = None
    # Ours, not either framework's: a marker that PyPSA held a series where the destination
    # field is a single number, so a consumer knows the value was flattened.
    has_time_varying_efficiency: bool | None = None
    has_time_varying_p_max_pu: bool | None = None
    has_time_varying_p_min_pu: bool | None = None
    # Ours: the companion parquet holding the OSeMOSYS CapacityFactor of each snapshot, which
    # multiplies the static p_max_pu, as Sienna states one rating for a line and no series.
    p_max_pu_series: str | None = None
    # No PyPSA field: the line converts one electricity fuel into another at one location, so
    # the results count it neither as production nor as trade.
    is_conversion: bool | None = None


class StorageExtension(ActivityExtension):
    # PyPSA StorageUnit.carrier, or the OSeMOSYS category of the discharging technology.
    carrier: str | None = None
    p_nom_extendable: bool | None = None  # PyPSA only
    # h. PyPSA StorageUnit.max_hours. Sienna's HydroDispatch states the reservoir nowhere,
    # so a hydro unit loses it without this.
    max_hours: float | None = None
    # MWh. PyPSA StorageUnit.state_of_charge_initial, for the same reason.
    state_of_charge_initial: float | None = None
    # MW. PyPSA StorageUnit.inflow. Sienna reads a hydro budget as a time series alone, so a
    # static inflow has no field there.
    inflow_mw: float | None = None
    # Ours: the companion parquet holding the inflow at each snapshot, in MW, where the
    # reservoir refills at a rate that changes.
    inflow_series: str | None = None
    # Ours: the companion parquet holding the share of its rating the unit reaches at each
    # snapshot. Sienna states one rating and names no series against it.
    rating_series: str | None = None
    # $/MWh of energy capacity; PyPSA states it as Store.overnight_cost; OSeMOSYS
    # CapitalCostStorage.
    energy_overnight_cost: float | None = None
    # h at full power in one timeslice; no PyPSA field, because StorageUnit.max_hours is the
    # energy over the power; OSeMOSYS StorageMaxHours.
    duration_max_hours: float | None = None
    # PyPSA StorageUnit.cyclic_state_of_charge_per_period; OSeMOSYS StorageBalanceYear.
    cyclic_state_of_charge_per_period: bool | None = None
    # No PyPSA field; OSeMOSYS StorageBalanceSeason.
    cyclic_state_of_charge_per_season: bool | None = None
    # No PyPSA field; OSeMOSYS StorageBalanceDay.
    cyclic_state_of_charge_per_day: bool | None = None
    # $/MW/yr of the technology that charges the storage, where it does not also discharge it;
    # no PyPSA field, as PyPSA states it as fom_cost of the charging Link.
    charge_fom_cost: float | None = None


class ReserveExtension(ExtensionRecord):
    """A quantity of capacity held back, and who may hold it.

    PLEXOS and Sienna both have the concept and PyPSA has none, so this is the kind that a
    PLEXOS to PyPSA to Sienna chain depends on. The requirement normalises to megawatts:
    ``requirement_mw`` where it holds at every snapshot, ``requirement_series`` where it
    varies. A share of system load is a rule for computing megawatts, not a different
    quantity, so the hop holding the load resolves it and it never reaches here.
    """

    # MW. PLEXOS Min Provision; Sienna requirement.
    requirement_mw: float | None = None
    # Ours: the companion parquet holding the requirement at each snapshot, in MW. PLEXOS
    # holds a varying requirement in a Data File and Sienna in an attached series; neither
    # has a field naming one.
    requirement_series: str | None = None
    # PLEXOS's Generators collection; Sienna's service memberships on each contributing unit.
    contributing_generators: list[str] = []
    direction: ReserveDirection = ReserveDirection.UNKNOWN
    kind: ReserveKind = ReserveKind.UNKNOWN
    # s. Sienna sustained_time (default 3600); PLEXOS Duration.
    sustained_time_seconds: float | None = None
    is_available: bool | None = None  # Sienna available; PLEXOS Is Enabled
    # Sienna only: the cap on one unit's share of the requirement.
    max_participation_factor: float | None = None
    # cost/MW. PLEXOS VoRS. Sienna has no equivalent.
    shortage_price: float | None = None
    # PLEXOS Mutually Exclusive: this reserve draws on the same spare capacity as the other
    # reserves so marked. Sienna has no equivalent.
    is_mutually_exclusive: bool | None = None


class ConstraintMember(BaseModel):
    """One object a constraint weights, and the coefficient it is weighted by.

    Two classes can hold an object of the same name and a constraint can weight a generator
    and an emission alike, so the member carries the class its name belongs to. The
    coefficient is absent where the constraint names the object without weighting it.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    member_class: str  # PLEXOS Generator, Line, Emission and the rest
    coefficient: float | None = None
    # PLEXOS names the coefficient per class: Generation Coefficient, Flow Coefficient, and
    # so on. The name says which quantity of the member the coefficient weights.
    coefficient_property: str | None = None


class ConstraintLimit(BaseModel):
    """One right-hand side the weighted sum is held to, and the span it applies over."""

    model_config = ConfigDict(extra="forbid")

    period: ConstraintPeriod
    value: float
    unit: str | None = None  # the unit the source stated the limit in
    # PyPSA GlobalConstraint.investment_period: the year of a yearly limit; OSeMOSYS YEAR.
    investment_period: int | None = None


class ConstraintExtension(ExtensionRecord):
    """A weighted sum over named objects, held to one or more right-hand sides."""

    # PyPSA GlobalConstraint.type, primary_energy for an emission limit; renewable_share and
    # reserve_margin are ours and no PyPSA type, so PyPSA builds no constraint from them.
    type: str | None = None
    # PyPSA GlobalConstraint.carrier_attribute: the quantity of each member that the sum
    # counts, which is the pollutant of an OSeMOSYS emission limit.
    carrier_attribute: str | None = None
    sense: ConstraintSense | None = None
    limits: list[ConstraintLimit] = []
    members: list[ConstraintMember] = []
    # PLEXOS Include in LT Plan: whether the expansion plan has to meet the constraint as
    # well as the dispatch.
    applies_to_expansion_plan: bool | None = None


class NetworkExtension(ExtensionRecord):
    """The model file's own attributes. PyPSA only: neither Sienna nor PLEXOS has these."""

    pypsa_version: str | None = None
    # The solved objective. Present only for a network that was solved.
    objective: float | None = None


class Extensions(BaseModel):
    """The sidecar document. Each field name is a kind, and holds that kind's records."""

    model_config = ConfigDict(extra="forbid")

    bus: list[BusExtension] = []
    generator: list[GeneratorExtension] = []
    load: list[LoadExtension] = []
    line: list[LineExtension] = []
    controllable_line: list[ControllableLineExtension] = []
    storage: list[StorageExtension] = []
    reserve: list[ReserveExtension] = []
    constraint: list[ConstraintExtension] = []
    network: list[NetworkExtension] = []
    representative_period: list[RepresentativePeriodExtension] = []
    technology: list[TechnologyExtension] = []
    conversion: list[ConversionExtension] = []


def _build_extension_models() -> dict[ExtensionKind, type[ExtensionRecord]]:
    """The record model of each kind, read off the fields of the document."""
    fields = Extensions.model_fields
    if set(fields) != set(ExtensionKind):
        raise TypeError(
            f"the Extensions fields {sorted(fields)} must name each ExtensionKind once, "
            f"and only those: {sorted(str(kind) for kind in ExtensionKind)}"
        )
    return {ExtensionKind(kind): get_args(info.annotation)[0] for kind, info in fields.items()}


EXTENSION_MODELS: dict[ExtensionKind, type[ExtensionRecord]] = _build_extension_models()

# A PyPSA file holds one network and PyPSA gives it no name, so its record is named for what
# it describes.
NETWORK_RECORD_NAME = "network"

EXTENSIONS_FILENAME = "extensions.json"

RecordT = TypeVar("RecordT", bound=ExtensionRecord)

# What a hop holds on `State`, keyed by `ExtensionKind`. Records, not frames: a kind holds
# one small record per component, so the models are the runtime contract as well as the
# schema, and the only conversions are at the file edge.
StagedExtensions: TypeAlias = dict[ExtensionKind, list[ExtensionRecord]]

# The lazy half: the series a record points at instead of stating a scalar. Keyed the same
# way, so the two sides of a kind are looked up by the same key.
StagedExtensionSeries: TypeAlias = dict[ExtensionKind, pl.LazyFrame]


class LegacyExtensionsError(UserInputError, ValueError):
    """An extensions file written before the document was keyed by kind."""

    def __init__(self) -> None:
        super().__init__(
            "this extensions file is a list of records, which predates the kind-keyed "
            "extensions.json format; regenerate it by re-running the translation that "
            "wrote it"
        )


def parse_extensions(payload: object) -> Extensions:
    """The document a parsed extensions file states.

    A file this version cannot honour fails naming the field, rather than being quietly
    ignored: the sidecar arrives from a previous hop, so reading is where the models are
    worth validating at runtime.
    """
    if isinstance(payload, list):
        raise LegacyExtensionsError
    return Extensions.model_validate(payload)


def dump_extensions(document: Extensions, indent: int) -> str:
    """The sidecar text.

    A kind with no records and a field the source did not state are both absent, so the file
    states what is there and nothing else. A record's ``direction`` and ``kind`` survive as
    ``unknown``, which says we read a code and could not map it.
    """
    payload = document.model_dump(mode="json", exclude_none=True)
    stated = {kind: records for kind, records in payload.items() if records}
    return json.dumps(stated, indent=indent)


def build_extensions(staged: StagedExtensions) -> Extensions:
    """The document a pipeline's staged records make up."""
    return Extensions.model_validate({str(kind): records for kind, records in staged.items()})


def stage_extensions(document: Extensions) -> StagedExtensions:
    """One list of records per kind the document states any for."""
    staged: StagedExtensions = {}
    for kind in EXTENSION_MODELS:
        records: list[ExtensionRecord] = getattr(document, kind)
        if records:
            staged[kind] = list(records)
    return staged


def append_extensions(
    staged: StagedExtensions, kind: ExtensionKind, records: Sequence[ExtensionRecord]
) -> None:
    """Add one kind's records to what a hop has staged.

    Every producer goes through here, so two mappings that both emit a kind add to each
    other rather than the later one replacing the earlier.
    """
    staged.setdefault(kind, []).extend(records)


class CompanionSeriesCol(StrEnum):
    """Columns of a companion parquet, beside the row's value.

    The value column takes the name of the scalar field the series stands in for, so it
    carries that field's unit and a consumer never has to know what the source called it.
    """

    SNAPSHOT = "snapshot"
    NAME = "name"


class GeneratorCompanionCol(StrEnum):
    """Value columns of the generator companion parquet, named for the field each holds."""

    MARGINAL_COST = "marginal_cost"


class LoadCompanionCol(StrEnum):
    """Value columns of the load companion parquet, named for the field each holds."""

    P_SET = "p_set"


class StorageCompanionCol(StrEnum):
    """Value columns of the storage companion parquet, each named for the field it holds."""

    INFLOW_MW = "inflow_mw"
    RATING_PU = "rating_pu"


class ControllableLineCompanionCol(StrEnum):
    """Value columns of the controllable line companion parquet."""

    P_MAX_PU = "p_max_pu"


class Companion(NamedTuple):
    """The parquet a kind's series live in, and the record fields that name that file."""

    filename: str
    series_fields: tuple[str, ...]


# Companions sit beside the sidecar and are named for what they hold. A kind with no entry
# states every value on the record itself. One parquet holds every series of its kind, one
# column per field, so a kind naming two fields writes two value columns.
_COMPANIONS: dict[ExtensionKind, Companion] = {
    ExtensionKind.GENERATOR: Companion("generators.parquet", ("marginal_cost_series",)),
    ExtensionKind.LOAD: Companion("loads.parquet", ("p_set_series",)),
    ExtensionKind.RESERVE: Companion("reserves.parquet", ("requirement_series",)),
    ExtensionKind.STORAGE: Companion("storage.parquet", ("inflow_series", "rating_series")),
    ExtensionKind.CONTROLLABLE_LINE: Companion("controllable_lines.parquet", ("p_max_pu_series",)),
}


def companion_filename(kind: ExtensionKind) -> str:
    """The parquet beside the sidecar that holds one kind's series.

    Total, not a lookup that can miss: a kind only reaches here by staging a series, and a
    kind that stages one without naming a file for it is a wiring mistake, not model data.
    """
    companion = _COMPANIONS.get(kind)
    if companion is None:
        raise KeyError(f"extension kind {kind!r} stages a series but names no companion file")
    return companion.filename


def names_companion_series(kind: ExtensionKind, records: Sequence[ExtensionRecord]) -> bool:
    """Whether a kind's staged records point at a companion parquet beside the sidecar.

    A record states its value or names a series holding one value per snapshot, never both,
    so this asks the records rather than assuming every kind with a companion filename wrote
    one.
    """
    companion = _COMPANIONS.get(kind)
    return companion is not None and any(
        getattr(record, series_field, None) is not None
        for record in records
        for series_field in companion.series_fields
    )


_UNCONSUMED_NOTE = (
    "no mapping in this translation reads this extension record, so it is dropped rather "
    "than carried into the next sidecar"
)
_UNHANDLED_FIELD_NOTE = (
    "a mapping in this translation reads this extension record, but no mapping maps this "
    "field and none relays it, so it is dropped rather than carried into the next sidecar"
)
_UNCONSUMED_WARNING = "%d extension record(s) reach no mapping, so each is dropped: %s"
_UNHANDLED_FIELD_WARNING = (
    "%d field(s) of extension records reach no mapping and no relay, so each is dropped: %s"
)


def report_dropped(staged: StagedExtensions, framework: str, recorder: EventRecorder) -> None:
    """Report every record staged here as dropped, with one event each and one warning."""
    labels = [f"{kind} {record.name}" for kind, records in staged.items() for record in records]
    for kind, records in staged.items():
        for record in records:
            recorder.append(
                TranslationEvent(
                    kind=EventKind.NOT_MAPPED,
                    sources=[SourceField(framework=framework, component=kind, name=record.name)],
                    note=_UNCONSUMED_NOTE,
                )
            )
    if labels:
        log.warning(_UNCONSUMED_WARNING, len(labels), name_a_few(labels))


def build_stated_fields(record: ExtensionRecord) -> dict[str, Any]:
    """The fields a record states a value for, other than its name, by field name."""
    return {
        field_name: getattr(record, field_name)
        for field_name in record.model_dump(exclude={"name"}, exclude_none=True, exclude_unset=True)
    }


def _is_scalar(value: Any) -> bool:
    return isinstance(value, str | int | float | bool)


@overload
def record_for(
    staged: StagedExtensions, kind: Literal[ExtensionKind.BUS], name: str
) -> BusExtension | None: ...
@overload
def record_for(
    staged: StagedExtensions, kind: Literal[ExtensionKind.GENERATOR], name: str
) -> GeneratorExtension | None: ...
@overload
def record_for(
    staged: StagedExtensions, kind: Literal[ExtensionKind.LOAD], name: str
) -> LoadExtension | None: ...
@overload
def record_for(
    staged: StagedExtensions, kind: Literal[ExtensionKind.LINE], name: str
) -> LineExtension | None: ...
@overload
def record_for(
    staged: StagedExtensions, kind: Literal[ExtensionKind.CONTROLLABLE_LINE], name: str
) -> ControllableLineExtension | None: ...
@overload
def record_for(
    staged: StagedExtensions, kind: Literal[ExtensionKind.STORAGE], name: str
) -> StorageExtension | None: ...
@overload
def record_for(
    staged: StagedExtensions, kind: Literal[ExtensionKind.RESERVE], name: str
) -> ReserveExtension | None: ...
@overload
def record_for(
    staged: StagedExtensions, kind: Literal[ExtensionKind.CONSTRAINT], name: str
) -> ConstraintExtension | None: ...
@overload
def record_for(
    staged: StagedExtensions, kind: Literal[ExtensionKind.NETWORK], name: str
) -> NetworkExtension | None: ...
@overload
def record_for(
    staged: StagedExtensions, kind: Literal[ExtensionKind.REPRESENTATIVE_PERIOD], name: str
) -> RepresentativePeriodExtension | None: ...
@overload
def record_for(
    staged: StagedExtensions, kind: Literal[ExtensionKind.TECHNOLOGY], name: str
) -> TechnologyExtension | None: ...
@overload
def record_for(
    staged: StagedExtensions, kind: Literal[ExtensionKind.CONVERSION], name: str
) -> ConversionExtension | None: ...


def record_for(staged: StagedExtensions, kind: ExtensionKind, name: str) -> Any:
    """One staged record, for a reader that is not a mapping hop. The kind fixes the type.

    No consume tracking: a caller reaching for one known record is not deciding what travels
    onward, so it has nothing to report as dropped.
    """
    return next((record for record in staged.get(kind, []) if record.name == name), None)


@dataclass
class KindConsumption:
    """The records of one kind that readers took whole, and the fields handled in the rest."""

    whole: set[str] = field(default_factory=set)
    fields: dict[str, set[str]] = field(default_factory=dict)

    def list_unhandled_fields(self, record: ExtensionRecord) -> list[str]:
        """The stated fields of a record taken field by field that nothing handles."""
        if record.name in self.whole or record.name not in self.fields:
            return []
        handled = self.fields[record.name]
        return [name for name in build_stated_fields(record) if name not in handled]

    def is_unread(self, record: ExtensionRecord) -> bool:
        return record.name not in self.whole and record.name not in self.fields


class ExtensionLookup(Generic[RecordT]):
    """One kind's staged records, by name.

    ``get`` always answers with a record, so a consumer reads a field rather than branching
    on whether the hop before it wrote anything. A name the sidecar never mentioned yields a
    record whose every field is unset, which is what "the source said nothing" means.
    """

    def __init__(self, model: type[RecordT], records: Sequence[RecordT], consumed: KindConsumption):
        self._model = model
        self._records = {record.name: record for record in records}
        self._consumed = consumed

    def get(self, name: str) -> RecordT:
        self._consumed.whole.add(name)
        return self._find_or_build(name)

    def get_fields(self, name: str, mapped: Collection[str]) -> RecordT:
        """One record, of which the caller maps only the ``mapped`` fields."""
        self._consumed.fields.setdefault(name, set()).update(mapped)
        return self._find_or_build(name)

    def relay(self, name: str) -> RecordT:
        """A record of the stated fields of ``name`` that no mapping maps, marked as relayed."""
        handled = self._consumed.fields.setdefault(name, set())
        left = {
            field_name: value
            for field_name, value in build_stated_fields(self._find_or_build(name)).items()
            if field_name not in handled
        }
        handled.update(left)
        return self._model.model_validate({"name": name, **left})

    def list_records(self) -> list[RecordT]:
        """Every staged record of this kind, none of them marked as read."""
        return list(self._records.values())

    def read_all(self) -> list[RecordT]:
        """Every staged record of this kind, each one marked as read."""
        self._consumed.whole.update(self._records)
        return list(self._records.values())

    def _find_or_build(self, name: str) -> RecordT:
        return self._records.get(name) or self._model(name=name)


class DroppedField(NamedTuple):
    """One stated field of a record that no mapping maps and no relay passes on."""

    kind: ExtensionKind
    record: ExtensionRecord
    field_name: str

    @property
    def label(self) -> str:
        """The kind, the record and the field, as a warning names them."""
        return f"{self.kind} {self.record.name}.{self.field_name}"


@dataclass
class ExtensionConsumption:
    """The records and fields every reader of one hop has read, and the step to report a drop
    against.

    A hop may split its mappings across more than one step, so the readers those steps build
    share one of these and the run reports what none of them asked for once the last step
    has run. ``recorder`` belongs to the step that opened the sidecar, which is the step a
    record it holds no mapping for was offered to.
    """

    recorder: EventRecorder
    by_kind: dict[ExtensionKind, KindConsumption] = field(
        default_factory=lambda: {kind: KindConsumption() for kind in ExtensionKind}
    )

    def get_kind(self, kind: ExtensionKind) -> KindConsumption:
        return self.by_kind[kind]

    def report_unconsumed(self, staged: StagedExtensions, framework: str) -> None:
        """Report each record no reader read, and each field nothing maps or relays."""
        report_dropped(self._list_unread(staged), framework, self.recorder)
        dropped = self._list_dropped_fields(staged)
        for one in dropped:
            self._record_dropped_field(one, framework)
        if dropped:
            labels = [one.label for one in dropped]
            log.warning(_UNHANDLED_FIELD_WARNING, len(labels), name_a_few(labels))

    def _list_unread(self, staged: StagedExtensions) -> StagedExtensions:
        unread = {
            kind: [record for record in records if self.by_kind[kind].is_unread(record)]
            for kind, records in staged.items()
        }
        return {kind: records for kind, records in unread.items() if records}

    def _list_dropped_fields(self, staged: StagedExtensions) -> list[DroppedField]:
        return [
            DroppedField(kind, record, field_name)
            for kind, records in staged.items()
            for record in records
            for field_name in self.by_kind[kind].list_unhandled_fields(record)
        ]

    def _record_dropped_field(self, dropped: DroppedField, framework: str) -> None:
        value = getattr(dropped.record, dropped.field_name)
        self.recorder.append(
            TranslationEvent(
                kind=EventKind.NOT_MAPPED,
                sources=[
                    SourceField(
                        framework=framework,
                        component=dropped.kind,
                        name=dropped.record.name,
                        attribute=dropped.field_name,
                        value=value if _is_scalar(value) else None,
                    )
                ],
                note=_UNHANDLED_FIELD_NOTE,
            )
        )


class ExtensionReader:
    """What one hop staged, and what its mappings did with it.

    A record only reaches a sidecar because the hop before it had nowhere to put it, so a
    record no mapping here consumes is dropped and reported rather than relayed onward. One
    consumption record serves every mapping of a hop, so it can tell what nobody asked for.
    """

    def __init__(self, staged: StagedExtensions, consumption: ExtensionConsumption) -> None:
        self._staged = staged
        self._consumption = consumption

    @overload
    def read(self, kind: Literal[ExtensionKind.BUS]) -> ExtensionLookup[BusExtension]: ...
    @overload
    def read(
        self, kind: Literal[ExtensionKind.GENERATOR]
    ) -> ExtensionLookup[GeneratorExtension]: ...
    @overload
    def read(self, kind: Literal[ExtensionKind.LOAD]) -> ExtensionLookup[LoadExtension]: ...
    @overload
    def read(self, kind: Literal[ExtensionKind.LINE]) -> ExtensionLookup[LineExtension]: ...
    @overload
    def read(
        self, kind: Literal[ExtensionKind.CONTROLLABLE_LINE]
    ) -> ExtensionLookup[ControllableLineExtension]: ...
    @overload
    def read(self, kind: Literal[ExtensionKind.STORAGE]) -> ExtensionLookup[StorageExtension]: ...
    @overload
    def read(self, kind: Literal[ExtensionKind.RESERVE]) -> ExtensionLookup[ReserveExtension]: ...
    @overload
    def read(
        self, kind: Literal[ExtensionKind.CONSTRAINT]
    ) -> ExtensionLookup[ConstraintExtension]: ...
    @overload
    def read(self, kind: Literal[ExtensionKind.NETWORK]) -> ExtensionLookup[NetworkExtension]: ...
    @overload
    def read(
        self, kind: Literal[ExtensionKind.REPRESENTATIVE_PERIOD]
    ) -> ExtensionLookup[RepresentativePeriodExtension]: ...
    @overload
    def read(
        self, kind: Literal[ExtensionKind.TECHNOLOGY]
    ) -> ExtensionLookup[TechnologyExtension]: ...
    @overload
    def read(
        self, kind: Literal[ExtensionKind.CONVERSION]
    ) -> ExtensionLookup[ConversionExtension]: ...

    def read(self, kind: ExtensionKind) -> ExtensionLookup[Any]:
        """One kind's records, by name. The kind fixes the record type."""
        model = EXTENSION_MODELS[kind]
        return ExtensionLookup(model, self._staged.get(kind, []), self._consumption.get_kind(kind))

    def relay(self, kind: ExtensionKind) -> list[ExtensionRecord]:
        """Every record of a kind, marked as read, for a hop that carries it on unchanged."""
        records = list(self._staged.get(kind, []))
        self._consumption.get_kind(kind).whole.update(record.name for record in records)
        return records
