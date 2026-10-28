import logging
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, ClassVar, NamedTuple

import questionary
from dishka import Container
from questionary import Choice

from interop.adapters.inbound.base import Launcher
from interop.adapters.inbound.interactive_cli.history import DetailKey, History, Invocation
from interop.adapters.inbound.interactive_cli.prompts import (
    choose_select_default,
    print_user_error,
)
from interop.adapters.inbound.interactive_cli.schema_prompts import (
    PATH_PROMPT_HINT,
    collect_node_params,
)
from interop.adapters.inbound.interactive_cli.solve_prompts import run_solve
from interop.ports.errors import UserInputError
from interop.ports.inbound.compare import CompareSide, CompareUseCase
from interop.ports.inbound.init_project import Example, InitProjectUseCase
from interop.ports.inbound.overrides import NodeOverrides
from interop.ports.inbound.pipeline_catalog import PipelineCatalogUseCase, PipelineStructure
from interop.ports.inbound.translate import TranslateUseCase
from interop.ports.inbound.validate import ValidateUseCase
from interop.ports.outbound.filesystem import Location, to_location
from interop.ports.outbound.validation import EnergyModelValidationError, ValidationSeverity
from interop.ports.outbound.validation_report import DEFAULT_VALIDATION_REPORT_PATH

log = logging.getLogger(__name__)

# History entries longer than this elide their tail in the menu so rows stay scannable.
_HISTORY_SUMMARY_LIMIT = 80


class Command(StrEnum):
    VALIDATE = "validate"
    TRANSLATE = "translate"
    INIT = "init"
    SOLVE = "solve"
    COMPARE = "compare"
    HISTORY = "history"
    QUIT = "quit"


def _dispatch(
    command: Command, container: Container, replay: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    """Run a command, optionally prefilling prompts from a recorded invocation.

    Returns the answers given at the prompts, for recording in history.
    """
    match command:
        case Command.VALIDATE:
            return _run_validate(container, replay)
        case Command.TRANSLATE:
            return _run_translate(container, replay)
        case Command.INIT:
            return _run_init(container, replay)
        case Command.SOLVE:
            return run_solve(container, replay)
        case Command.COMPARE:
            return _run_compare(container, replay)
        case _:
            print(f"{command}: not implemented")
            return None


def _command_description(command: Command) -> str:
    match command:
        case Command.VALIDATE:
            return "Validate a model's inputs against a pipeline's validators"
        case Command.TRANSLATE:
            return "Translate a model between frameworks using a pipeline"
        case Command.INIT:
            return "Scaffold a new interop project directory"
        case Command.SOLVE:
            return "Solve a translated system with PowerSimulations.jl"
        case Command.COMPARE:
            return "Compare model results for two different frameworks"
        case Command.HISTORY:
            return "Re-run a previous invocation"
        case Command.QUIT:
            return "Exit the shell"


def _select_pipeline(container: Container, replay: dict[str, Any]) -> tuple[str, str, str] | None:
    """Prompt for source/destination framework and pipeline; None if cancelled."""
    try:
        with container() as scope:
            catalog = scope.get(PipelineCatalogUseCase)
            by_pair = catalog.by_framework_pair()
    except UserInputError as exc:
        print_user_error(exc)
        return None
    if not by_pair:
        questionary.print("(no pipelines available)", style="fg:#888")
        return None

    sources = sorted({source for source, _ in by_pair})
    source_framework = questionary.select(
        "Source framework?",
        choices=sources,
        default=choose_select_default(replay.get(DetailKey.SOURCE_FRAMEWORK), sources),
    ).ask()
    if source_framework is None:
        return None

    destinations = sorted({dst for src, dst in by_pair if src == source_framework})
    destination_framework = questionary.select(
        "Destination framework?",
        choices=destinations,
        default=choose_select_default(replay.get(DetailKey.DESTINATION_FRAMEWORK), destinations),
    ).ask()
    if destination_framework is None:
        return None

    pipelines = by_pair[(source_framework, destination_framework)]
    pipeline_name = questionary.select(
        "Pipeline?",
        choices=pipelines,
        default=choose_select_default(replay.get(DetailKey.PIPELINE_NAME), pipelines),
    ).ask()
    if pipeline_name is None:
        return None
    return source_framework, destination_framework, pipeline_name


def _load_structure(container: Container, pipeline_name: str) -> PipelineStructure | None:
    """Fetch a pipeline's structure, printing and swallowing user errors."""
    try:
        with container() as scope:
            catalog: PipelineCatalogUseCase = scope.get(PipelineCatalogUseCase)
            return catalog.get_structure(pipeline_name)
    except UserInputError as exc:
        print_user_error(exc)
        return None


class _MappingsCancelled:
    """Sentinel: the user escaped a required user-mappings prompt."""


_MAPPINGS_CANCELLED = _MappingsCancelled()


_USER_MAPPINGS_PROMPT = "User mappings file?"
_SIDE_USER_MAPPINGS_PROMPT = "User mappings file for {framework}?"


def _prompt_user_mappings(
    needed: bool,
    replay: dict[str, Any],
    details: dict[str, Any],
    prompt: str = _USER_MAPPINGS_PROMPT,
) -> Location | None | _MappingsCancelled:
    """Prompt for a user-mappings file when the pipeline needs one.

    Returns the resolved Location, None when no file is needed, or the
    cancelled sentinel when the user escaped a required prompt (the caller
    then aborts, having already recorded the details gathered so far). The
    chosen path is recorded in `details` for history replay.
    """
    if not needed:
        return None
    mapping_path_str = questionary.path(
        f"{prompt}  {PATH_PROMPT_HINT}",
        default=replay.get(DetailKey.USER_MAPPINGS_PATH, "inputs/user_mappings.yaml"),
    ).ask()
    if mapping_path_str is None:
        questionary.print("a user mappings file is required to run this pipeline.", style="fg:red")
        return _MAPPINGS_CANCELLED
    details[DetailKey.USER_MAPPINGS_PATH] = mapping_path_str
    return to_location(mapping_path_str)


def _run_validate(
    container: Container, replay: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    replay = replay or {}
    selection = _select_pipeline(container, replay)
    if selection is None:
        return None
    source_framework, destination_framework, pipeline_name = selection

    pipeline_structure = _load_structure(container, pipeline_name)
    if pipeline_structure is None:
        return None

    source_overrides = collect_node_params(
        pipeline_structure.source.params_schema,
        pipeline_structure.source.yaml_params,
        "source",
        replay_params=replay.get(DetailKey.SOURCE_OVERRIDES),
    )
    details: dict[str, Any] = {
        DetailKey.SOURCE_FRAMEWORK: source_framework,
        DetailKey.DESTINATION_FRAMEWORK: destination_framework,
        DetailKey.PIPELINE_NAME: pipeline_name,
        DetailKey.SOURCE_OVERRIDES: source_overrides,
    }

    # validate builds the source and the validators and runs no steps, so a
    # mapping-consuming step is irrelevant to whether it needs a file.
    user_mappings_path = _prompt_user_mappings(
        pipeline_structure.validation_needs_user_mappings, replay, details
    )
    if isinstance(user_mappings_path, _MappingsCancelled):
        return details

    try:
        with container() as scope:
            use_case = scope.get(ValidateUseCase)
            result = use_case(
                source_framework,
                destination_framework,
                pipeline_name,
                overrides=NodeOverrides(source=source_overrides),
                user_mappings_path=user_mappings_path,
            )
    except UserInputError as exc:
        print_user_error(exc)
        return details
    except Exception as exc:
        questionary.print(f"validate failed: {exc}", style="fg:red")
        return details

    _print_checked_leg(pipeline_name, result.validated_pipeline)
    _print_validation_summary(result.errors)
    return details


def _print_checked_leg(chosen: str, validated: str) -> None:
    if validated == chosen:
        return
    questionary.print(
        f"{chosen} is a chain, so validate checked the first leg only ({validated}). "
        "The later legs have no input until the legs before them have run.",
        style="fg:#888",
    )


def _print_validation_summary(errors: list[EnergyModelValidationError]) -> None:
    n_critical = sum(1 for error in errors if error.severity is ValidationSeverity.CRITICAL)
    n_warning = len(errors) - n_critical
    if not errors:
        style = "fg:green"
    elif n_critical:
        style = "fg:red"
    else:
        style = "fg:yellow"
    questionary.print(
        f"found {len(errors)} validation issues ({n_critical} CRITICAL, {n_warning} WARNING); "
        f"wrote {DEFAULT_VALIDATION_REPORT_PATH}",
        style=style,
    )


def _run_translate(
    container: Container, replay: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    replay = replay or {}
    selection = _select_pipeline(container, replay)
    if selection is None:
        return None
    source_framework, destination_framework, pipeline_name = selection

    pipeline_structure = _load_structure(container, pipeline_name)
    if pipeline_structure is None:
        return None

    replay_steps = replay.get(DetailKey.STEP_OVERRIDES, {})
    replay_sinks = replay.get(DetailKey.SINK_OVERRIDES, {})
    source_overrides = collect_node_params(
        pipeline_structure.source.params_schema,
        pipeline_structure.source.yaml_params,
        "source",
        replay_params=replay.get(DetailKey.SOURCE_OVERRIDES),
    )
    step_overrides = {
        idx: collect_node_params(
            step.params_schema,
            step.yaml_params,
            f"step[{idx}]",
            replay_params=replay_steps.get(str(idx)),
        )
        for idx, step in enumerate(pipeline_structure.steps)
    }
    sink_overrides = {
        idx: collect_node_params(
            sink.params_schema,
            sink.yaml_params,
            f"sink[{idx}]",
            replay_params=replay_sinks.get(str(idx)),
        )
        for idx, sink in enumerate(pipeline_structure.sinks)
    }
    # JSON object keys are strings, so step/sink indices are recorded as strings.
    details: dict[str, Any] = {
        DetailKey.SOURCE_FRAMEWORK: source_framework,
        DetailKey.DESTINATION_FRAMEWORK: destination_framework,
        DetailKey.PIPELINE_NAME: pipeline_name,
        DetailKey.SOURCE_OVERRIDES: source_overrides,
        DetailKey.STEP_OVERRIDES: {str(idx): params for idx, params in step_overrides.items()},
        DetailKey.SINK_OVERRIDES: {str(idx): params for idx, params in sink_overrides.items()},
    }

    user_mappings_path = _prompt_user_mappings(
        pipeline_structure.needs_user_mappings, replay, details
    )
    if isinstance(user_mappings_path, _MappingsCancelled):
        return details

    start = time.monotonic()
    try:
        with container() as scope:
            use_case = scope.get(TranslateUseCase)
            result = use_case(
                source_framework,
                destination_framework,
                pipeline_name,
                overrides=NodeOverrides(
                    source=source_overrides, steps=step_overrides, sinks=sink_overrides
                ),
                user_mappings_path=user_mappings_path,
            )
    except UserInputError as exc:
        print_user_error(exc)
        return details
    except Exception as exc:
        # A failed run must not take the shell down with it; report and return to the menu.
        questionary.print(f"translate failed: {exc}", style="fg:red")
        return details
    log.info(result.summary(pipeline_name, time.monotonic() - start))
    return details


@dataclass(frozen=True)
class _SideReplay:
    """What a history replay gives one side of a comparison."""

    pipeline: Any
    params: dict[str, Any] | None
    user_mappings_path: Any


class _SideReplayKeys(NamedTuple):
    """The detail keys that one side of a comparison records its answers under."""

    pipeline: DetailKey
    params: DetailKey
    user_mappings_path: DetailKey


def _build_side_replay(replay: dict[str, Any], keys: _SideReplayKeys) -> _SideReplay:
    return _SideReplay(
        replay.get(keys.pipeline), replay.get(keys.params), replay.get(keys.user_mappings_path)
    )


_SIDE_A_REPLAY_KEYS = _SideReplayKeys(
    pipeline=DetailKey.SIDE_A_PIPELINE,
    params=DetailKey.SIDE_A_PARAMS,
    user_mappings_path=DetailKey.SIDE_A_USER_MAPPINGS_PATH,
)
_SIDE_B_REPLAY_KEYS = _SideReplayKeys(
    pipeline=DetailKey.SIDE_B_PIPELINE,
    params=DetailKey.SIDE_B_PARAMS,
    user_mappings_path=DetailKey.SIDE_B_USER_MAPPINGS_PATH,
)


def _build_compare_side(
    container: Container, framework: str, pipelines: list[str], replay: _SideReplay
) -> CompareSide | None:
    """Pick the framework's results pipeline (when it has more than one), its source params,
    and its user mappings file when the pipeline needs one."""
    pipeline_name = _choose_results_pipeline(framework, pipelines, replay.pipeline)
    if pipeline_name is None:
        return None
    with container() as scope:
        catalog = scope.get(PipelineCatalogUseCase)
        structure = catalog.get_structure(pipeline_name)
    source_params = collect_node_params(
        structure.source.params_schema, {}, framework, replay_params=replay.params
    )
    user_mappings_path = _prompt_side_user_mappings(
        framework, structure.needs_user_mappings, replay
    )
    if isinstance(user_mappings_path, _MappingsCancelled):
        return None
    return CompareSide(
        framework=framework,
        pipeline=pipeline_name,
        source_params=source_params,
        user_mappings_path=user_mappings_path,
    )


def _choose_results_pipeline(framework: str, pipelines: list[str], replay: Any) -> str | None:
    if len(pipelines) == 1:
        return pipelines[0]
    answer: str | None = questionary.select(
        f"Which {framework} results pipeline?",
        choices=sorted(pipelines),
        default=choose_select_default(replay, pipelines),
    ).ask()
    return answer


def _prompt_side_user_mappings(
    framework: str, needed: bool, replay: _SideReplay
) -> Location | None | _MappingsCancelled:
    side_replay: dict[str, Any] = (
        {}
        if replay.user_mappings_path is None
        else {DetailKey.USER_MAPPINGS_PATH: replay.user_mappings_path}
    )
    prompt = _SIDE_USER_MAPPINGS_PROMPT.format(framework=framework)
    return _prompt_user_mappings(needed, side_replay, {}, prompt)


def _build_mappings_details(side: CompareSide, key: DetailKey) -> dict[str, str]:
    """A side with no user mappings file records nothing, as translate does."""
    return {} if side.user_mappings_path is None else {key: str(side.user_mappings_path)}


def _run_compare(
    container: Container, replay: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    replay = replay or {}
    try:
        with container() as scope:
            pipelines_by_framework = scope.get(CompareUseCase).comparable_frameworks()
    except UserInputError as exc:
        print_user_error(exc)
        return None

    frameworks = sorted(pipelines_by_framework)
    framework_a = questionary.select(
        "First result's framework?",
        choices=frameworks,
        default=choose_select_default(replay.get(DetailKey.SIDE_A_FRAMEWORK), frameworks),
    ).ask()
    if framework_a is None:
        return None

    other_frameworks = [framework for framework in frameworks if framework != framework_a]
    framework_b = questionary.select(
        "Second result's framework?",
        choices=other_frameworks,
        default=choose_select_default(replay.get(DetailKey.SIDE_B_FRAMEWORK), other_frameworks),
    ).ask()
    if framework_b is None:
        return None

    side_a = _build_compare_side(
        container,
        framework_a,
        pipelines_by_framework[framework_a],
        _build_side_replay(replay, _SIDE_A_REPLAY_KEYS),
    )
    if side_a is None:
        return None
    side_b = _build_compare_side(
        container,
        framework_b,
        pipelines_by_framework[framework_b],
        _build_side_replay(replay, _SIDE_B_REPLAY_KEYS),
    )
    if side_b is None:
        return None

    raw_output = questionary.path(
        f"Output path for summary report?  {PATH_PROMPT_HINT}",
        default=str(replay.get(DetailKey.OUTPUT_PATH, "outputs/comparison_summary.md")),
    ).ask()
    if raw_output is None:
        return None
    output_path = Path(raw_output.strip()).expanduser()

    details: dict[str, Any] = {
        DetailKey.SIDE_A_FRAMEWORK: side_a.framework,
        DetailKey.SIDE_A_PIPELINE: side_a.pipeline,
        DetailKey.SIDE_A_PARAMS: side_a.source_params,
        DetailKey.SIDE_B_FRAMEWORK: side_b.framework,
        DetailKey.SIDE_B_PIPELINE: side_b.pipeline,
        DetailKey.SIDE_B_PARAMS: side_b.source_params,
        DetailKey.OUTPUT_PATH: str(output_path),
        **_build_mappings_details(side_a, DetailKey.SIDE_A_USER_MAPPINGS_PATH),
        **_build_mappings_details(side_b, DetailKey.SIDE_B_USER_MAPPINGS_PATH),
    }

    try:
        with container() as scope:
            use_case = scope.get(CompareUseCase)
            result = use_case(side_a, side_b, output_path)
    except UserInputError as exc:
        print_user_error(exc)
        return details
    except Exception as exc:
        # A failed run must not take the shell down with it; report and return to the menu.
        questionary.print(f"compare failed: {exc}", style="fg:red")
        return details

    questionary.print(result.summary(), style="fg:green")
    return details


def _run_init(container: Container, replay: dict[str, Any] | None = None) -> dict[str, Any] | None:
    replay = replay or {}
    default_target = str(replay.get(DetailKey.TARGET, ""))
    raw_target = questionary.text("Target directory?", default=default_target).ask()
    if raw_target is None:
        return None
    target = Path(raw_target)

    example_choices = [str(member) for member in Example]
    example_answer = questionary.select(
        "Scaffold an example?",
        choices=example_choices,
        default=choose_select_default(replay.get(DetailKey.EXAMPLE), example_choices),
    ).ask()
    if example_answer is None:
        return None
    example = Example(example_answer)

    try:
        with container() as scope:
            use_case = scope.get(InitProjectUseCase)
            use_case(target, example)
        _print_init_next_steps(target)
    except UserInputError as exc:
        print_user_error(exc)
    return {DetailKey.TARGET: str(target), DetailKey.EXAMPLE: str(example)}


def _print_init_next_steps(target: Path) -> None:
    questionary.print(f"\nInitialised interop project at {target}.", style="fg:green")
    questionary.print(
        "Next: cd into that directory and launch interop there, then pick 'translate'.\n"
        "Pipelines and plugins resolve against the current directory; put source\n"
        "files under inputs/ and find results (and decisions.md) under outputs/.\n"
        "The project ships no environment of its own, so run an already-installed\n"
        "interop binary (on PATH or by absolute path) from inside it.",
        style="fg:#888",
    )


def _details_summary(details: dict[str, Any] | None) -> str:
    """One-line rendering of an invocation's recorded answers for the history menu."""
    if not details:
        return ""
    parts: list[str] = []
    if DetailKey.SOURCE_FRAMEWORK in details:
        parts.append(
            f"{details[DetailKey.SOURCE_FRAMEWORK]} -> {details[DetailKey.DESTINATION_FRAMEWORK]}"
        )
    if DetailKey.PIPELINE_NAME in details:
        parts.append(str(details[DetailKey.PIPELINE_NAME]))
    override_groups = [
        details.get(DetailKey.SOURCE_OVERRIDES, {}),
        *details.get(DetailKey.STEP_OVERRIDES, {}).values(),
        *details.get(DetailKey.SINK_OVERRIDES, {}).values(),
    ]
    for overrides in override_groups:
        parts.extend(f"{name}={value}" for name, value in overrides.items())
    if DetailKey.TARGET in details:
        parts.append(f"target={details[DetailKey.TARGET]}")
    if DetailKey.SIENNA_JSON_PATH in details:
        parts.append(f"input_file={details[DetailKey.SIENNA_JSON_PATH]}")
    if DetailKey.NETWORK_MODEL in details:
        parts.append(f"model={details[DetailKey.NETWORK_MODEL]}")
    if DetailKey.SOLVER in details:
        parts.append(f"solver={details[DetailKey.SOLVER]}")
    if DetailKey.OUTPUT_DIR in details:
        parts.append(f"output_dir={details[DetailKey.OUTPUT_DIR]}")
    if DetailKey.SIDE_A_FRAMEWORK in details:
        parts.append(
            f"{details[DetailKey.SIDE_A_FRAMEWORK]} vs {details[DetailKey.SIDE_B_FRAMEWORK]}"
        )
    summary = " ".join(parts)
    if len(summary) > _HISTORY_SUMMARY_LIMIT:
        summary = summary[: _HISTORY_SUMMARY_LIMIT - 3] + "..."
    return summary


def _invocation_label(invocation: Invocation) -> str:
    label = f"{invocation['timestamp']}  {invocation['command']}"
    summary = _details_summary(invocation.get("details"))
    if summary:
        label = f"{label}  {summary}"
    return label


def _history_menu(history: History) -> Invocation | None:
    """Show recent invocations with their answers; return the pick or None if cancelled."""
    recent = history.recent()
    if not recent:
        questionary.print("(no previous invocations yet)", style="fg:#888")
        return None

    picked: Invocation | None = questionary.select(
        "Re-run which past invocation?",
        choices=[Choice(_invocation_label(inv), value=inv) for inv in recent],
    ).ask()
    return picked


def run(container: Container) -> None:
    history = History.load()
    questionary.print("interop interactive shell  (Ctrl-C to quit)\n", style="bold")

    while True:
        try:
            choice: Command | None = questionary.select(
                "What would you like to do?",
                choices=[
                    Choice(f"{c.value:<11}{_command_description(c)}", value=c) for c in Command
                ],
            ).ask()
        except KeyboardInterrupt:
            break

        match choice:
            case None | Command.QUIT:
                break
            case Command.HISTORY:
                picked = _history_menu(history)
                if picked is None:
                    continue
                command = Command(picked["command"])
                details = _dispatch(command, container, replay=picked.get("details"))
                history.record(command, details)
            case (
                Command.VALIDATE
                | Command.TRANSLATE
                | Command.INIT
                | Command.SOLVE
                | Command.COMPARE
            ):
                details = _dispatch(choice, container)
                history.record(choice, details)

    questionary.print("\nbye.", style="fg:#888")


class InteractiveCli(Launcher):
    name: ClassVar[str] = "interactive_cli"

    def run(self, container: Container) -> None:
        run(container)
