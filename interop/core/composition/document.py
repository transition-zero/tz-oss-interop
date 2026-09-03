"""Composed manifests: reading one off disk, and the frameworks it declares."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from interop.core.runner import PipelineSpec, list_pipelines, read_pipeline_document
from interop.ports.errors import UserInputError

_COMPOSE_KEY = "compose"


class LegSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pipeline: str
    params: dict[str, Any] = Field(default_factory=dict)


class ComposedPipelineSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_framework: str
    destination_framework: str
    mappings: list[LegSpec] = Field(default_factory=list)
    compose: list[LegSpec] = Field(min_length=2)


PipelineDocument = PipelineSpec | ComposedPipelineSpec


class CompositionError(UserInputError):
    """A composed manifest the composer cannot run, reported as a one-line message."""


class FrameworkMismatchError(UserInputError, ValueError):
    def __init__(
        self,
        declared: PipelineDocument,
        expected_source: str,
        expected_destination: str,
    ) -> None:
        super().__init__(
            f"Pipeline declares source_framework={declared.source_framework!r}, "
            f"destination_framework={declared.destination_framework!r} but caller "
            f"requested {expected_source!r} -> {expected_destination!r}"
        )

        self.declared = declared
        self.expected_source = expected_source
        self.expected_destination = expected_destination


def load_pipeline_document(name: str, project_root: Path | None = None) -> PipelineDocument:
    data = read_pipeline_document(name, project_root)
    if isinstance(data, dict) and _COMPOSE_KEY in data:
        return ComposedPipelineSpec.model_validate(data)
    return PipelineSpec.model_validate(data)


def load_leg_spec(name: str, project_root: Path | None = None) -> PipelineSpec:
    document = load_pipeline_document(name, project_root)
    if isinstance(document, ComposedPipelineSpec):
        raise CompositionError(
            f"Leg {name!r} is itself a composed pipeline. Composing a composed pipeline is "
            "not supported; list its legs directly instead."
        )
    return document


def list_pipelines_by_framework_pair(
    project_root: Path | None = None,
) -> dict[tuple[str, str], list[str]]:
    pairs: dict[tuple[str, str], list[str]] = {}
    for name in list_pipelines(project_root):
        document = load_pipeline_document(name, project_root)
        key = (document.source_framework, document.destination_framework)
        pairs.setdefault(key, []).append(name)
    for names in pairs.values():
        names.sort()
    return pairs


def validate_frameworks(
    declared: PipelineDocument, source_framework: str, destination_framework: str
) -> None:
    frameworks_match = (
        declared.source_framework == source_framework
        and declared.destination_framework == destination_framework
    )
    if not frameworks_match:
        raise FrameworkMismatchError(declared, source_framework, destination_framework)
