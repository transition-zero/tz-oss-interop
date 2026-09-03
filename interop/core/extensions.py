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
from collections.abc import Sequence
from enum import StrEnum
from typing import Any, Generic, Literal, NamedTuple, TypeAlias, TypeVar, overload

import polars as pl
from pydantic import BaseModel, ConfigDict

from interop.core.reporting import EventRecorder
from interop.ports.errors import UserInputError
from interop.ports.outbound.reporting import EventKind, SourceField, TranslationEvent


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
    NETWORK = "network"  # PyPSA network-level attributes. No Sienna or PLEXOS equivalent.


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


class ExtensionRecord(BaseModel):
    """One component's record. ``name`` is the identifier in every framework."""

    model_config = ConfigDict(extra="forbid")

    name: str


class BusExtension(ExtensionRecord):
    # PyPSA Bus.carrier (AC or DC). Sienna ACBus and PLEXOS Node have no carrier field.
    carrier: str | None = None
    # $/MWh. PLEXOS states it on the Region containing the node; Sienna prices it on the load
    # rather than the bus. PyPSA has no field for it at all, so a chain through PyPSA needs
    # this to keep the price a shortfall is charged at.
    value_of_lost_load: float | None = None


class GeneratorExtension(ExtensionRecord):
    # PyPSA Generator.carrier. Sienna states fuel and prime mover instead, and several PyPSA
    # carriers share one (prime_mover, fuel) pair, so the reverse cannot recover this.
    carrier: str | None = None
    # PyPSA Generator.committable. Sienna decides commitment by component type.
    committable: bool | None = None
    # PyPSA only: neither Sienna nor PLEXOS carries a per-component expansion flag.
    p_nom_extendable: bool | None = None
    # PLEXOS only: the generator's category, a grouping string the user chooses.
    category: str | None = None


class LoadExtension(ExtensionRecord):
    carrier: str | None = None  # PyPSA Load.carrier
    type: str | None = None  # PyPSA Load.type, a free string
    # PyPSA Load.sign, -1 by convention. Sienna PowerLoad is positive-consumption by
    # definition, so it has nothing to state here.
    sign: float | None = None


class LineExtension(ExtensionRecord):
    carrier: str | None = None  # PyPSA Line.carrier
    # km. PyPSA Line.length and PLEXOS Length. SiennaSchemas Line holds only r, x, b, g,
    # rating and angle_limits, so a length has no home there.
    length: float | None = None
    # PyPSA Line.num_parallel; PLEXOS states the same idea as Units. No Sienna field.
    num_parallel: float | None = None
    s_nom_extendable: bool | None = None  # PyPSA only


class ControllableLineExtension(ExtensionRecord):
    carrier: str | None = None  # PyPSA Link.carrier
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


class StorageExtension(ExtensionRecord):
    p_nom_extendable: bool | None = None  # PyPSA only


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
    network: list[NetworkExtension] = []


EXTENSION_MODELS: dict[ExtensionKind, type[ExtensionRecord]] = {
    ExtensionKind.BUS: BusExtension,
    ExtensionKind.GENERATOR: GeneratorExtension,
    ExtensionKind.LOAD: LoadExtension,
    ExtensionKind.LINE: LineExtension,
    ExtensionKind.CONTROLLABLE_LINE: ControllableLineExtension,
    ExtensionKind.STORAGE: StorageExtension,
    ExtensionKind.RESERVE: ReserveExtension,
    ExtensionKind.NETWORK: NetworkExtension,
}

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


class Companion(NamedTuple):
    """The parquet a kind's series lives in, and the record field that names that file."""

    filename: str
    series_field: str


# Companions sit beside the sidecar and are named for what they hold. A kind with no entry
# states every value on the record itself.
_COMPANIONS: dict[ExtensionKind, Companion] = {
    ExtensionKind.RESERVE: Companion("reserves.parquet", "requirement_series"),
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
        getattr(record, companion.series_field, None) is not None for record in records
    )


_UNCONSUMED_NOTE = (
    "no mapping in this translation reads this extension record, so it is dropped rather "
    "than carried into the next sidecar"
)


def report_dropped(staged: StagedExtensions, framework: str, recorder: EventRecorder) -> None:
    """Report every record staged here as dropped."""
    for kind, records in staged.items():
        for record in records:
            recorder.append(
                TranslationEvent(
                    kind=EventKind.NOT_MAPPED,
                    sources=[SourceField(framework=framework, component=kind, name=record.name)],
                    note=_UNCONSUMED_NOTE,
                )
            )


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
    staged: StagedExtensions, kind: Literal[ExtensionKind.NETWORK], name: str
) -> NetworkExtension | None: ...


def record_for(staged: StagedExtensions, kind: ExtensionKind, name: str) -> Any:
    """One staged record, for a reader that is not a mapping hop. The kind fixes the type.

    No consume tracking: a caller reaching for one known record is not deciding what travels
    onward, so it has nothing to report as dropped.
    """
    return next((record for record in staged.get(kind, []) if record.name == name), None)


class ExtensionLookup(Generic[RecordT]):
    """One kind's staged records, by name.

    ``get`` always answers with a record, so a consumer reads a field rather than branching
    on whether the hop before it wrote anything. A name the sidecar never mentioned yields a
    record whose every field is unset, which is what "the source said nothing" means.
    """

    def __init__(self, model: type[RecordT], records: Sequence[RecordT], consumed: set[str]):
        self._model = model
        self._records = {record.name: record for record in records}
        self._consumed = consumed

    def get(self, name: str) -> RecordT:
        self._consumed.add(name)
        return self._records.get(name) or self._model(name=name)


class ExtensionReader:
    """What one hop staged, and what its mappings did with it.

    A record only reaches a sidecar because the hop before it had nowhere to put it, so a
    record no mapping here consumes is dropped and reported rather than relayed onward. One
    reader serves every mapping in a hop, so it can tell what nobody asked for.
    """

    def __init__(self, staged: StagedExtensions, framework: str) -> None:
        self._staged = staged
        self._framework = framework
        self._consumed: dict[ExtensionKind, set[str]] = {}

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
    def read(self, kind: Literal[ExtensionKind.NETWORK]) -> ExtensionLookup[NetworkExtension]: ...

    def read(self, kind: ExtensionKind) -> ExtensionLookup[Any]:
        """One kind's records, by name. The kind fixes the record type."""
        model = EXTENSION_MODELS[kind]
        return ExtensionLookup(
            model, self._staged.get(kind, []), self._consumed.setdefault(kind, set())
        )

    def relay(self, kind: ExtensionKind) -> list[ExtensionRecord]:
        """Every record of a kind, marked as read, for a hop that carries it on unchanged."""
        records = list(self._staged.get(kind, []))
        self._consumed.setdefault(kind, set()).update(record.name for record in records)
        return records

    def report_unconsumed(self, recorder: EventRecorder) -> None:
        """Report every staged record no mapping in this hop asked for."""
        for kind, records in self._staged.items():
            consumed = self._consumed.get(kind, set())
            unread = [record for record in records if record.name not in consumed]
            report_dropped({kind: unread}, self._framework, recorder)
