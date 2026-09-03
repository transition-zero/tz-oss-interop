from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError

from interop.core.factories import (
    SinkFactory,
    SourceFactory,
    StepFactory,
    ValidatorFactory,
)
from interop.core.pipeline import (
    NodeKind,
    PipelineSteps,
    Sink,
    Source,
    State,
    TranslationStep,
    Validator,
)
from interop.ports.errors import UserInputError
from interop.ports.outbound.validation import (
    EnergyModelValidationError,
    ValidationFailedError,
    ValidationSeverity,
    ValidatorCrashedError,
)

# Results pipelines live in this subdirectory of pipelines/ so they stay separate from the
# framework-to-framework translations: translate lists only the latter, compare only the former.
RESULTS_SUBDIR = "results"

_MAPPINGS_SUBDIR = "mappings"

# Neither subtree holds a manifest a user picks: results pipelines belong to compare, and
# mapping pipelines are run by a composed pipeline that names them. Nothing in a manifest says
# so, since a mapping pipeline is an ordinary PipelineSpec and only the plugin registry knows
# that one of its sinks writes a user mappings file, so the directory says it instead.
_UNLISTED_SUBDIRS = (RESULTS_SUBDIR, _MAPPINGS_SUBDIR)


class NodeSpec(BaseModel):
    name: str
    params: dict[str, Any] = Field(default_factory=dict)


class PipelineSpec(BaseModel):
    source_framework: str
    destination_framework: str
    source: NodeSpec
    steps: list[NodeSpec] = Field(default_factory=list)
    sinks: list[NodeSpec] = Field(default_factory=list)
    validators: list[NodeSpec] = Field(default_factory=list)


class NodeParamsError(UserInputError, ValueError):
    def __init__(
        self,
        kind: NodeKind,
        spec: NodeSpec,
        node: Source | TranslationStep | Sink | Validator,
        original: ValidationError,
    ) -> None:
        super().__init__(
            f"Invalid params for {kind.value} node {spec.name!r} "
            f"({type(node).__module__}.{type(node).__qualname__}):\n{original}"
        )
        self.kind = kind
        self.spec = spec
        self.node = node
        self.original = original


class UnexpectedNodeParamsError(UserInputError, ValueError):
    def __init__(self, spec: NodeSpec) -> None:
        super().__init__(
            f"Node {spec.name!r} accepts no params but the pipeline supplied {spec.params!r}"
        )
        self.spec = spec


def read_pipeline_document(name: str, project_root: Path | None = None) -> Any:
    """The raw YAML of the named manifest, before any schema is chosen for it."""
    for path in _candidate_paths(name, project_root or Path.cwd()):
        if path.is_file():
            return yaml.safe_load(path.read_text(encoding="utf-8"))
    raise FileNotFoundError(name)


def load_pipeline(name: str, project_root: Path | None = None) -> PipelineSpec:
    return PipelineSpec.model_validate(read_pipeline_document(name, project_root))


def list_pipelines(project_root: Path | None = None) -> list[str]:
    """Names of the framework-to-framework translation pipelines.

    Pipelines may be organised into subdirectories of ``pipelines/`` for
    convenience, so the tree is searched recursively. Two subdirectories are the
    exception: ``results`` holds the results pipelines
    (``destination_framework == "results"``), listed by ``list_results_pipelines``,
    and ``mappings`` holds the mapping pipelines a composed pipeline runs.
    """
    return _translation_stems(_translation_dirs(project_root))


def list_results_pipelines(project_root: Path | None = None) -> list[str]:
    """Names of the results pipelines (the manifests in the ``results`` subdirectory)."""
    return _stems_in(_results_dirs(project_root))


def list_results_pipelines_by_framework(
    project_root: Path | None = None,
) -> dict[str, list[str]]:
    """Index the results pipelines by their source framework.

    Every results pipeline has ``destination_framework == "results"``, so the source
    framework is the meaningful key: the framework whose solve output it normalises.
    """
    pipelines_by_framework: dict[str, list[str]] = {}
    for name in list_results_pipelines(project_root):
        spec = load_pipeline(name, project_root)
        pipelines_by_framework.setdefault(spec.source_framework, []).append(name)
    for names in pipelines_by_framework.values():
        names.sort()
    return pipelines_by_framework


def _translation_dirs(project_root: Path | None) -> list[Path]:
    import interop

    root = project_root or Path.cwd()
    return [Path(interop.__file__).parent / "pipelines", root / "pipelines"]


def _results_dirs(project_root: Path | None) -> list[Path]:
    return [directory / RESULTS_SUBDIR for directory in _translation_dirs(project_root)]


def _stems_in(directories: list[Path]) -> list[str]:
    names: set[str] = set()
    for directory in directories:
        for path in directory.glob("*.yaml"):
            names.add(path.stem)
    return sorted(names)


def _translation_stems(directories: list[Path]) -> list[str]:
    """Stems of every translation manifest under the pipelines dirs, with the results and
    mappings subtrees excluded.
    """
    names: set[str] = set()
    for directory in directories:
        for path in directory.rglob("*.yaml"):
            parts = path.relative_to(directory).parts
            if any(subdir in parts for subdir in _UNLISTED_SUBDIRS):
                continue
            names.add(path.stem)
    return sorted(names)


def run_pipeline(
    spec: PipelineSpec,
    source_factory: SourceFactory,
    step_factory: StepFactory,
    sink_factory: SinkFactory,
    validator_factory: ValidatorFactory,
    *,
    keep_staging: bool = False,
    on_validators_complete: Callable[[list[EnergyModelValidationError]], None] | None = None,
) -> list[EnergyModelValidationError]:
    source = source_factory(spec.source.name)
    source_params = _build_params(NodeKind.SOURCE, source, spec.source)
    with source.load(source_params, keep_staging=keep_staging) as state:
        _run_validators(state, spec, validator_factory, on_validators_complete)
        _reject_untranslatable_input(state)

        pipeline_steps = PipelineSteps(frozenset(node.name for node in spec.steps))
        for step_node in spec.steps:
            step = step_factory(step_node.name, pipeline_steps)
            state = step.run(state, _build_params(NodeKind.STEP, step, step_node))

        for sink_node in spec.sinks:
            sink = sink_factory(sink_node.name)
            sink.write(state, _build_params(NodeKind.SINK, sink, sink_node))

        return list(state.validation_errors)


def run_validation(
    spec: PipelineSpec,
    source_factory: SourceFactory,
    validator_factory: ValidatorFactory,
    *,
    keep_staging: bool = False,
    on_validators_complete: Callable[[list[EnergyModelValidationError]], None] | None = None,
) -> list[EnergyModelValidationError]:
    """Load the source and run only the pipeline's validators, returning their errors."""
    source = source_factory(spec.source.name)
    source_params = _build_params(NodeKind.SOURCE, source, spec.source)
    with source.load(source_params, keep_staging=keep_staging) as state:
        _run_validators(state, spec, validator_factory, on_validators_complete)
        return list(state.validation_errors)


def _reject_untranslatable_input(state: State) -> None:
    """Stop a translate run whose validators found the input untranslatable.

    Only translation stops. `run_validation` backs the `validate` command, whose whole
    job is to report what it finds, so it collects the same findings and returns them.

    Raised after the caller has been handed the findings to report, so the run leaves
    behind a validation report naming everything to fix rather than only this message.
    """
    critical = [
        error for error in state.validation_errors if error.severity is ValidationSeverity.CRITICAL
    ]
    if critical:
        raise ValidationFailedError(critical)


def _run_validators(
    state: State,
    spec: PipelineSpec,
    validator_factory: ValidatorFactory,
    on_validators_complete: Callable[[list[EnergyModelValidationError]], None] | None,
) -> None:
    """Run every validator, then hand whatever they found to `on_validators_complete`.

    A validator that raises is a bug in that validator, not a finding about the input, so
    it is never recorded as one and the run fails. It does not stop the validators after
    it: a bug in one check would otherwise hide every real problem the others would have
    reported, leaving a user with nothing to act on. Crashes are collected and raised
    together once the findings have been handed over.

    Findings accumulate on the state, so they are complete once the loop ends. Handing them
    over in a `finally`, and before any step can raise, is what leaves a validation report
    on disk however the run ends.
    """
    crashes: list[ValidatorCrashedError] = []
    try:
        for validator_node in spec.validators:
            # Outside the guard below: building a node from its spec fails on the pipeline
            # the user declared, not on the validator's own code, so it is theirs to fix.
            validator = validator_factory(validator_node.name)
            params = _build_params(NodeKind.VALIDATOR, validator, validator_node)
            try:
                validator.validate(state, params)
            except Exception as crash:
                crashes.append(ValidatorCrashedError(validator_node.name, crash))
    finally:
        if on_validators_complete is not None:
            on_validators_complete(list(state.validation_errors))
    if crashes:
        named = ", ".join(crash.validator for crash in crashes)
        validators = "validator" if len(crashes) == 1 else "validators"
        raise ExceptionGroup(f"{len(crashes)} {validators} failed to run: {named}", crashes)


def _build_params(
    kind: NodeKind, node: Source | TranslationStep | Sink | Validator, spec: NodeSpec
) -> BaseModel | None:
    if node.params_schema is None:
        pipeline_supplied_unwanted_params = bool(spec.params)
        if pipeline_supplied_unwanted_params:
            raise UnexpectedNodeParamsError(spec)
        return None
    try:
        return node.params_schema(**spec.params)
    except ValidationError as e:
        raise NodeParamsError(kind, spec, node, e) from e


def _candidate_paths(name: str, project_root: Path) -> list[Path]:
    """Where a pipeline name might resolve, searched recursively.

    Each pipelines dir is walked recursively so a manifest nested in a subdirectory
    still loads by name. The results subtree is part of that walk, so a results
    pipeline loads too (compare runs each side's results pipeline through translate,
    which loads it by name). Package dirs come before project dirs, so a package
    pipeline wins when a name exists in both.
    """
    paths: list[Path] = []
    for directory in _translation_dirs(project_root):
        paths.extend(sorted(directory.rglob(f"{name}.yaml")))
    return paths
