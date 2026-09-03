from __future__ import annotations

import typing
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, NamedTuple

import yaml
from pydantic import ValidationError

from interop.core.composition.addressing import ParamAddress
from interop.core.user_mappings import NodeLookups, UserMappings, UserMappingsLookup
from interop.ports.errors import UserInputError
from interop.ports.outbound.filesystem import FilesystemPort, Location

if TYPE_CHECKING:
    from interop.core.runner import PipelineSpec


class MappingsFile(NamedTuple):
    """A mappings file travels with the filesystem that can read it: a derived one lives
    in the run's scratch space, which the configured port may not even address.
    """

    location: Location
    filesystem: FilesystemPort

    def locate(self) -> Location:
        """Where the file actually is, for a message the user reads."""
        return self.filesystem.locate(self.location)


class LabelledSpec(NamedTuple):
    """A pipeline spec, named when the caller runs several of them."""

    spec: PipelineSpec
    pipeline: str | None = None


class MappingsProducer(NamedTuple):
    """The sink that writes one schema's file, and the pipeline that sink belongs to."""

    address: ParamAddress
    pipeline: str | None = None

    def describe(self) -> str:
        sink = f"sink {self.address.node!r}"
        return sink if self.pipeline is None else f"pipeline {self.pipeline!r} {sink}"


@dataclass(frozen=True)
class ValidationInput:
    """What `validate` needs before it can run a pipeline's first leg.

    A schema a mapping pipeline derives is not the user's to supply, and validate runs no
    mapping pipelines, so there is nothing to ask for and nothing that would work.
    """

    needed: frozenset[type[UserMappings]]
    derived_elsewhere: frozenset[type[UserMappings]]

    @property
    def is_derived_elsewhere(self) -> bool:
        return bool(self.derived_elsewhere)

    @property
    def should_ask_the_user(self) -> bool:
        return bool(self.needed) and not self.derived_elsewhere


class UserMappingsLoader:
    def __init__(self, node_lookups: NodeLookups) -> None:
        self._node_lookups = node_lookups

    def collect_schemas_for_translate(self, spec: PipelineSpec) -> frozenset[type[UserMappings]]:
        """Everything `validate` needs, plus the steps it does not run."""
        schemas = set(self.collect_schemas_for_validate(spec))
        for step_node in spec.steps:
            schemas |= self._schemas_from_init(self._node_lookups.step(step_node.name))
        return frozenset(schemas)

    def collect_schemas_for_validate(self, spec: PipelineSpec) -> frozenset[type[UserMappings]]:
        """`validate` builds the source and the validators and nothing else, so a step's
        schema would name a node it never runs.
        """
        schemas = self._schemas_from_init(self._node_lookups.source(spec.source.name))
        for validator_node in spec.validators:
            schemas |= self._schemas_from_init(self._node_lookups.validator(validator_node.name))
        return frozenset(schemas)

    def collect_produced_mappings(
        self, spec: PipelineSpec
    ) -> dict[type[UserMappings], ParamAddress]:
        """Keyed by schema, because that is what routes a derived file to the leg that
        consumes it; nothing names a mappings file in a manifest.
        """
        folded = self.fold_produced_mappings([LabelledSpec(spec)])
        return {schema: producer.address for schema, producer in folded.items()}

    def fold_produced_mappings(
        self, labelled_specs: Iterable[LabelledSpec]
    ) -> dict[type[UserMappings], MappingsProducer]:
        """One schema has one producer, whether the two candidates are sinks in one pipeline
        or legs in one run: a file is routed by schema, so a second producer leaves nothing
        able to choose between the two.
        """
        producers: dict[type[UserMappings], MappingsProducer] = {}
        for labelled in labelled_specs:
            for schema, producer in self._collect_producers_in(labelled):
                _reject_second_producer(producers, schema, producer)
                producers[schema] = producer
        return producers

    def _collect_producers_in(
        self, labelled: LabelledSpec
    ) -> Iterator[tuple[type[UserMappings], MappingsProducer]]:
        for sink_node in labelled.spec.sinks:
            output = self._node_lookups.sink(sink_node.name).writes_user_mappings
            if output is None:
                continue
            address = ParamAddress(sink_node.name, output.path_param)
            yield output.schema, MappingsProducer(address, labelled.pipeline)

    def collect_schemas_produced_by(
        self, specs: Iterable[PipelineSpec]
    ) -> frozenset[type[UserMappings]]:
        """The schemas these pipelines write files for, which is what a later leg needing
        one does not have to be asked for.
        """
        return frozenset(
            schema for spec in specs for schema in self.collect_produced_mappings(spec)
        )

    def choose_validation_input(
        self, spec: PipelineSpec, mapping_specs: Iterable[PipelineSpec]
    ) -> ValidationInput:
        """One answer for both halves of the decision: the prompt and the refusal read the
        same object, so they cannot disagree about which files the user owns.
        """
        needed = self.collect_schemas_for_validate(spec)
        return ValidationInput(
            needed=needed,
            derived_elsewhere=needed & self.collect_schemas_produced_by(mapping_specs),
        )

    @staticmethod
    def _schemas_from_init(cls: type) -> set[type[UserMappings]]:
        hints = typing.get_type_hints(cls.__init__)  # type: ignore[misc]
        return {
            hint_type
            for param, hint_type in hints.items()
            if param != "return"
            and isinstance(hint_type, type)
            and issubclass(hint_type, UserMappings)
        }

    def load_for_validation(
        self, spec: PipelineSpec, file: MappingsFile | None
    ) -> UserMappingsLookup:
        """A pipeline whose source and validators need no mappings file accepts not being
        given one.
        """
        schemas = self.collect_schemas_for_validate(spec)
        return self._load(
            schemas,
            dict.fromkeys(schemas, file) if file else {},
            when_missing="none was provided",
        )

    def load_by_schema(
        self, spec: PipelineSpec, files: Mapping[type[UserMappings], MappingsFile]
    ) -> UserMappingsLookup:
        return self._load(
            self.collect_schemas_for_translate(spec),
            files,
            when_missing="none was provided and nothing in this run derives one",
        )

    def _load(
        self,
        schemas: frozenset[type[UserMappings]],
        files: Mapping[type[UserMappings], MappingsFile],
        *,
        when_missing: str,
    ) -> UserMappingsLookup:
        result: UserMappingsLookup = {}
        for schema in schemas:
            file = files.get(schema)
            if file is None:
                raise UserInputError(
                    f"This pipeline requires a {schema.__name__} user mappings file, "
                    f"but {when_missing}."
                )
            result[schema] = self._validate_as(schema, file)
        return result

    def _validate_as(self, schema: type[UserMappings], file: MappingsFile) -> UserMappings:
        try:
            return schema.model_validate(self._load_yaml(file))
        except ValidationError as exc:
            raise UserInputError(f"Invalid user mappings at {file.locate()}:\n{exc}") from exc

    @staticmethod
    def _load_yaml(file: MappingsFile) -> Any:
        path = file.locate()
        try:
            text = file.filesystem.read_bytes(file.location).decode()
        except FileNotFoundError:
            raise UserInputError(f"User mappings file not found: {path}") from None
        except OSError as exc:
            raise UserInputError(f"Could not read user mappings file: {path}: {exc}") from exc

        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise UserInputError(f"Invalid YAML in user mappings file: {path}:\n{exc}") from exc

        return data if data is not None else {}


def _reject_second_producer(
    producers: Mapping[type[UserMappings], MappingsProducer],
    schema: type[UserMappings],
    second: MappingsProducer,
) -> None:
    first = producers.get(schema)
    if first is not None:
        raise UserInputError(
            f"{_start_sentence(first.describe())} and {second.describe()} both write "
            f"{schema.__name__} mappings, so nothing can tell which file to use."
        )


def _start_sentence(text: str) -> str:
    return text[:1].upper() + text[1:]
