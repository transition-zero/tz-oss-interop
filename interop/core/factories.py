from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Generic, Protocol, TypeAlias, TypeVar

from pydantic import BaseModel

from interop.core.pipeline import PipelineSteps, Sink, Source, TranslationStep, Validator
from interop.core.reporting import EventRecorder
from interop.core.user_mappings import UserMappingsLookup
from interop.ports.outbound.filesystem import FilesystemPort, OnWrite
from interop.ports.outbound.reporting import ReportingPort

P = TypeVar("P", covariant=True)

SourceFactory: TypeAlias = Callable[[str], Source]
StepFactory: TypeAlias = Callable[[str, PipelineSteps], TranslationStep]
SinkFactory: TypeAlias = Callable[[str], Sink]
ValidatorFactory: TypeAlias = Callable[[str], Validator]
SinkFactoryBuilder: TypeAlias = Callable[[FilesystemPort], SinkFactory]
# Do not collapse this into a plain factory. A composed run binds each leg's source to the
# filesystem that end of the chain uses, so there is no one process-wide port to bake in.
SourceFactoryBuilder: TypeAlias = Callable[[FilesystemPort, UserMappingsLookup], SourceFactory]
StepFactoryBuilder: TypeAlias = Callable[[EventRecorder, UserMappingsLookup], StepFactory]
ValidatorFactoryBuilder: TypeAlias = Callable[[UserMappingsLookup], ValidatorFactory]
ReporterBuilder: TypeAlias = Callable[[FilesystemPort], ReportingPort]
# A filesystem rooted at the given directory, for one end of a composed run's interior
# hand-off. Built per run, because the directory is the run's own scratch space.
InteriorFilesystemFactory: TypeAlias = Callable[[Path], FilesystemPort]
# A filesystem that passes every call to the one it wraps and reports each write.
WriteTrackingFilesystemFactory: TypeAlias = Callable[[FilesystemPort, OnWrite], FilesystemPort]


class SchemaCatalog(Protocol):
    def __call__(self, category: str, name: str) -> type[BaseModel] | None: ...


# AdapterFactory is generic over the port type. A previous version was tied to
# implementations of one port (FilesystemPort), which would not scale once
# other outbound ports (e.g. logger, metrics) join: every new port type would
# need its own factory function and TypeAlias. Instead, callers pass the port
# they want and get back a factory that resolves only adapters implementing
# it. The registry stays a single name -> class mapping; the port selection
# is enforced at factory time by the isinstance check in the di layer.
class AdapterFactory(Protocol, Generic[P]):
    def __call__(self, name: str) -> P: ...
