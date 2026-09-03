from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, TypeAlias, runtime_checkable

from pydantic import BaseModel

# A framework's name (e.g. "pypsa") and a pipeline's name (its manifest stem).
# Both are plain strings; the aliases only make the dict shapes below readable.
FrameworkName: TypeAlias = str
PipelineName: TypeAlias = str


@dataclass(frozen=True)
class NodeStructure:
    name: str
    yaml_params: dict[str, Any] = field(default_factory=dict)
    params_schema: type[BaseModel] | None = None


@dataclass(frozen=True)
class PipelineStructure:
    source_framework: str
    destination_framework: str
    source: NodeStructure
    steps: tuple[NodeStructure, ...] = ()
    sinks: tuple[NodeStructure, ...] = ()
    needs_user_mappings: bool = False
    # The first leg only, matching the one leg `validate` runs.
    validation_needs_user_mappings: bool = False


@runtime_checkable
class PipelineCatalogUseCase(Protocol):
    def by_framework_pair(
        self,
    ) -> dict[tuple[FrameworkName, FrameworkName], list[PipelineName]]: ...
    def results_pipelines_by_framework(self) -> dict[FrameworkName, list[PipelineName]]: ...
    def get_structure(self, name: str) -> PipelineStructure: ...
