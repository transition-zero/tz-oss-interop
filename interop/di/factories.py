from __future__ import annotations

import inspect
import typing
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from interop.core.factories import (
    AdapterFactory,
    SchemaCatalog,
    SinkFactory,
    SourceFactory,
    StepFactory,
    ValidatorFactory,
)
from interop.core.pipeline import PipelineSteps, Sink, Source, TranslationStep, Validator
from interop.core.reporting import EventRecorder, ScopedRecorder
from interop.core.user_mappings import (
    NodeClassLookup,
    NodeLookups,
    SinkClassLookup,
    UserMappings,
    UserMappingsLookup,
)
from interop.di.discovery import Category, Registry
from interop.ports.errors import UserInputError
from interop.ports.outbound.filesystem import FilesystemPort

T = TypeVar("T")
P = TypeVar("P", covariant=True)


class UnknownPluginError(UserInputError, KeyError):
    def __init__(self, category: Category, name: str, available: list[str]) -> None:
        super().__init__(
            f"No plugin registered as {name!r} in {category.value!r}. "
            f"Available: {sorted(available)}"
        )
        self.category = category
        self.name = name


class InvalidPluginError(UserInputError, TypeError):
    def __init__(self, category: Category, name: str, cls: type, protocol: type) -> None:
        super().__init__(
            f"{cls.__module__}.{cls.__qualname__} registered as {name!r} in "
            f"{category.value!r} does not implement {protocol.__name__}"
        )
        self.category = category
        self.name = name
        self.cls = cls
        self.protocol = protocol


class InvalidAdapterConfigError(UserInputError, ValueError):
    def __init__(self, port: type, name: str, original: ValidationError) -> None:
        super().__init__(f"Invalid config for adapter {name!r} (port {port.__name__}):\n{original}")
        self.port = port
        self.name = name
        self.original = original


class UnknownAdapterBindingError(UserInputError, KeyError):
    def __init__(self, port: type, binding_key: str, name: str, available: list[str]) -> None:
        super().__init__(
            f"adapters.yaml binds {binding_key!r} to adapter {name!r}, which is not "
            f"registered. Available adapters for {port.__name__}: {sorted(available)}"
        )
        self.port = port
        self.binding_key = binding_key
        self.name = name
        self.available = available


def make_source_factory(
    registry: Registry,
    fs: FilesystemPort,
    user_mappings_lookup: UserMappingsLookup,
) -> SourceFactory:
    def factory(name: str) -> Source:
        cls = _resolve(registry, Category.SOURCES, name)
        user_mapping_kwargs = _get_user_mapping_kwargs(cls, user_mappings_lookup)
        instance: Source = _instantiate(cls, fs=fs, **user_mapping_kwargs)
        return instance

    return factory


def make_step_factory(
    registry: Registry,
    recorder: EventRecorder,
    user_mappings_lookup: UserMappingsLookup,
) -> StepFactory:
    def factory(name: str, pipeline_steps: PipelineSteps) -> TranslationStep:
        cls = _resolve(registry, Category.STEPS, name)
        scoped = ScopedRecorder(recorder, step=name)
        user_mapping_kwargs = _get_user_mapping_kwargs(cls, user_mappings_lookup)
        instance: TranslationStep = _instantiate(
            cls, recorder=scoped, pipeline_steps=pipeline_steps, **user_mapping_kwargs
        )
        return instance

    return factory


def _get_user_mapping_kwargs(
    cls: type, user_mappings_map: UserMappingsLookup
) -> dict[str, UserMappings]:
    hints = typing.get_type_hints(cls.__init__)  # type: ignore[misc]
    return {
        param: user_mappings_map[hint_type]
        for param, hint_type in hints.items()
        if param != "return"
        and isinstance(hint_type, type)
        and issubclass(hint_type, UserMappings)
        and hint_type in user_mappings_map
    }


def make_validator_factory(
    registry: Registry, user_mappings_lookup: UserMappingsLookup
) -> ValidatorFactory:
    def factory(name: str) -> Validator:
        cls = _resolve(registry, Category.VALIDATORS, name)
        user_mapping_kwargs = _get_user_mapping_kwargs(cls, user_mappings_lookup)
        instance: Validator = _instantiate(cls, **user_mapping_kwargs)
        return instance

    return factory


def make_sink_factory(registry: Registry, fs: FilesystemPort) -> SinkFactory:
    def factory(name: str) -> Sink:
        cls = _resolve(registry, Category.SINKS, name)
        instance: Sink = _instantiate(cls, fs=fs)
        return instance

    return factory


def make_adapter_factory(
    registry: Registry,
    port: type[P],
    adapter_configs: dict[str, dict[str, Any]] | None = None,
    **extra_kwargs: object,
) -> AdapterFactory[P]:
    configs: dict[str, dict[str, Any]] = adapter_configs or {}

    def factory(name: str) -> P:
        bucket = registry.adapter_bucket(port)
        if name not in bucket:
            raise UnknownPluginError(Category.ADAPTERS, name, list(bucket))
        cls = bucket[name]
        schema = getattr(cls, "config_schema", None)
        available_kwargs: dict[str, object] = dict(extra_kwargs)
        if schema is not None:
            try:
                config = schema.model_validate(configs.get(name, {}))
            except ValidationError as exc:
                raise InvalidAdapterConfigError(port, name, exc) from exc
            available_kwargs["config"] = config
        instance: P = _instantiate(cls, **available_kwargs)
        return instance

    return factory


def make_node_lookups(registry: Registry) -> NodeLookups:
    return NodeLookups(
        source=_class_lookup(registry, Category.SOURCES),
        step=_class_lookup(registry, Category.STEPS),
        sink=_sink_lookup(registry),
        validator=_class_lookup(registry, Category.VALIDATORS),
    )


def _class_lookup(registry: Registry, category: Category) -> NodeClassLookup:
    def lookup(name: str) -> type:
        return _resolve(registry, category, name)

    return lookup


def _sink_lookup(registry: Registry) -> SinkClassLookup:
    def lookup(name: str) -> type[Sink]:
        # `_resolve` has already rejected anything that does not inherit Sink.
        return typing.cast(type[Sink], _resolve(registry, Category.SINKS, name))

    return lookup


def make_schema_catalog(registry: Registry) -> SchemaCatalog:
    def catalog(category: str, name: str) -> type[BaseModel] | None:
        return get_params_schema(registry, Category(category), name)

    return catalog


def get_params_schema(registry: Registry, category: Category, name: str) -> type[BaseModel] | None:
    """Return the Pydantic schema for a node's params, or None if it takes none."""
    cls = _resolve(registry, category, name)
    schema = getattr(cls, "params_schema", None)
    if schema is None:
        return None
    if not isinstance(schema, type) or not issubclass(schema, BaseModel):
        raise TypeError(
            f"{cls.__name__} (registered as {name!r} in {category.value!r}) "
            "declares a params_schema that is not a Pydantic model"
        )
    return schema


def _resolve(registry: Registry, category: Category, name: str) -> type:
    bucket = registry.pipeline_node_bucket(category)
    if name not in bucket:
        raise UnknownPluginError(category, name, list(bucket))
    return bucket[name].resolve()


def _instantiate(cls: type[T], **available_kwargs: object) -> T:
    sig = inspect.signature(cls)
    accepted = {k: v for k, v in available_kwargs.items() if k in sig.parameters}
    return cls(**accepted)
