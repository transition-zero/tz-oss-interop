import logging
import time
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any, ClassVar

import questionary
from dishka import Container
from questionary import Choice

from interop.adapters.inbound.base import Launcher
from interop.adapters.inbound.interactive_cli.history import DetailKey, History, Invocation
from interop.adapters.inbound.interactive_cli.schema_prompts import (
    PATH_PROMPT_HINT,
    collect_node_params,
)
from interop.ports.errors import UserInputError
from interop.ports.inbound.compare import CompareSide, CompareUseCase
from interop.ports.inbound.init_project import Example, InitProjectUseCase
from interop.ports.inbound.overrides import NodeOverrides
from interop.ports.inbound.pipeline_catalog import PipelineCatalogUseCase, PipelineStructure
from interop.ports.inbound.solve import (
    DEFAULT_LOOK_AHEAD_DAYS,
    ModelType,
    SolveNetworkRequest,
    SolveSiennaRequest,
    SolveUseCase,
)
from interop.ports.inbound.translate import TranslateUseCase
from interop.ports.inbound.validate import ValidateUseCase
from interop.ports.outbound.filesystem import Location, to_location
from interop.ports.outbound.network_solver import SolveWindowLength
from interop.ports.outbound.solver import HiGHSCrossover, HiGHSPresolve, HiGHSSolver
from interop.ports.outbound.unit_commitment import UnitCommitmentTreatment
from interop.ports.outbound.validation import EnergyModelValidationError, ValidationSeverity
from interop.ports.outbound.validation_report import DEFAULT_VALIDATION_REPORT_PATH

log = logging.getLogger(__name__)

# History entries longer than this elide their tail in the menu so rows stay scannable.
_HISTORY_SUMMARY_LIMIT = 80


def _print_user_error(exc: UserInputError) -> None:
    questionary.print(str(exc), style="fg:red")


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
            return _run_solve(container, replay)
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


def _select_default(value: Any, options: list[str]) -> str | None:
    """A recorded answer is only usable as a select default if it is still a choice."""
    if isinstance(value, str) and value in options:
        return value
    return None


def _select_pipeline(container: Container, replay: dict[str, Any]) -> tuple[str, str, str] | None:
    """Prompt for source/destination framework and pipeline; None if cancelled."""
    try:
        with container() as scope:
            catalog = scope.get(PipelineCatalogUseCase)
            by_pair = catalog.by_framework_pair()
    except UserInputError as exc:
        _print_user_error(exc)
        return None
    if not by_pair:
        questionary.print("(no pipelines available)", style="fg:#888")
        return None

    sources = sorted({source for source, _ in by_pair})
    source_framework = questionary.select(
        "Source framework?",
        choices=sources,
        default=_select_default(replay.get(DetailKey.SOURCE_FRAMEWORK), sources),
    ).ask()
    if source_framework is None:
        return None

    destinations = sorted({dst for src, dst in by_pair if src == source_framework})
    destination_framework = questionary.select(
        "Destination framework?",
        choices=destinations,
        default=_select_default(replay.get(DetailKey.DESTINATION_FRAMEWORK), destinations),
    ).ask()
    if destination_framework is None:
        return None

    pipelines = by_pair[(source_framework, destination_framework)]
    pipeline_name = questionary.select(
        "Pipeline?",
        choices=pipelines,
        default=_select_default(replay.get(DetailKey.PIPELINE_NAME), pipelines),
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
        _print_user_error(exc)
        return None


class _MappingsCancelled:
    """Sentinel: the user escaped a required user-mappings prompt."""


_MAPPINGS_CANCELLED = _MappingsCancelled()


def _prompt_user_mappings(
    needed: bool, replay: dict[str, Any], details: dict[str, Any]
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
        f"User mappings file?  {PATH_PROMPT_HINT}",
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
        _print_user_error(exc)
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
        _print_user_error(exc)
        return details
    except Exception as exc:
        # A failed run must not take the shell down with it; report and return to the menu.
        questionary.print(f"translate failed: {exc}", style="fg:red")
        return details
    log.info(result.summary(pipeline_name, time.monotonic() - start))
    return details


_MODEL_TYPES = [m.value for m in ModelType]
_NETWORK_MODELS = ["dcp", "ptdf", "copperplate"]
_SOLVER_ALGORITHMS = [s.value for s in HiGHSSolver]
_PRESOLVE_OPTIONS = [s.value for s in HiGHSPresolve]
_CROSSOVER_OPTIONS = [s.value for s in HiGHSCrossover]
_UNIT_COMMITMENT_TREATMENTS = [t.value for t in UnitCommitmentTreatment]
_SOLVE_WINDOWS = [w.value for w in SolveWindowLength]

# PowerSimulations has no relaxed unit commitment formulation, so the two answers mean
# something different here from what they mean on the PyPSA path.
_SIENNA_UNIT_COMMITMENT_PROMPT = (
    "Unit commitment treatment? (exact = on/off as true binary decisions, applying the "
    "start-up cost and the minimum up and down times; linearised = economic dispatch, "
    "which is faster and applies neither)"
)


def _run_solve(container: Container, replay: dict[str, Any] | None = None) -> dict[str, Any] | None:
    replay = replay or {}
    model_type = questionary.select(
        "Model type?",
        choices=_MODEL_TYPES,
        default=_select_default(replay.get(DetailKey.MODEL_TYPE), _MODEL_TYPES),
    ).ask()
    if model_type is None:
        return None
    if model_type == ModelType.PYPSA:
        return _run_solve_pypsa(container, replay)

    try:
        with container() as scope:
            solver_is_provisioned = scope.get(SolveUseCase).is_provisioned()
    except UserInputError as exc:
        _print_user_error(exc)
        return None
    if not solver_is_provisioned:
        questionary.print(
            "Julia and the PowerSimulations.jl solver packages will be downloaded and "
            "compiled before solving. This needs an internet connection; progress is "
            "printed as it runs."
        )
        download_accepted = questionary.confirm("Download and continue?").ask()
        if not download_accepted:
            questionary.print("Solve cancelled.")
            return None

    raw_path = questionary.path(
        f"Path to PowerSimulations.jl system JSON?  {PATH_PROMPT_HINT}",
        default=str(replay.get(DetailKey.SIENNA_JSON_PATH, "")),
    ).ask()
    if raw_path is None:
        return None

    sienna_json_path = Path(raw_path.strip()).expanduser()
    if not sienna_json_path.is_file():
        _print_user_error(UserInputError(f"file not found: {sienna_json_path}"))
        return None

    network_model = questionary.select(
        "Network model?",
        choices=_NETWORK_MODELS,
        default=_select_default(replay.get(DetailKey.NETWORK_MODEL), _NETWORK_MODELS),
    ).ask()
    if network_model is None:
        return None

    unit_commitment = questionary.select(
        _SIENNA_UNIT_COMMITMENT_PROMPT,
        choices=_UNIT_COMMITMENT_TREATMENTS,
        default=_select_default(replay.get(DetailKey.UNIT_COMMITMENT), _UNIT_COMMITMENT_TREATMENTS),
    ).ask()
    if unit_commitment is None:
        return None

    solver = questionary.select(
        "HiGHS solver algorithm?",
        choices=_SOLVER_ALGORITHMS,
        default=_select_default(replay.get(DetailKey.SOLVER), _SOLVER_ALGORITHMS),
    ).ask()
    if solver is None:
        return None

    presolve = questionary.select(
        "Presolve? (choose = HiGHS decides automatically)",
        choices=_PRESOLVE_OPTIONS,
        default=_select_default(replay.get(DetailKey.PRESOLVE), _PRESOLVE_OPTIONS),
    ).ask()
    if presolve is None:
        return None

    run_crossover = questionary.select(
        "Run crossover after IPM? (choose = HiGHS decides automatically)",
        choices=_CROSSOVER_OPTIONS,
        default=_select_default(replay.get(DetailKey.RUN_CROSSOVER), _CROSSOVER_OPTIONS),
    ).ask()
    if run_crossover is None:
        return None

    raw_time_limit = questionary.text(
        "Time limit in seconds? (blank = no limit)",
        default=str(replay.get(DetailKey.TIME_LIMIT_SECONDS, "")),
    ).ask()
    if raw_time_limit is None:
        return None
    time_limit_seconds: float | None = None
    if raw_time_limit.strip():
        try:
            time_limit_seconds = float(raw_time_limit.strip())
        except ValueError:
            _print_user_error(UserInputError(f"invalid time limit: {raw_time_limit!r}"))
            return None

    default_output = str(replay.get(DetailKey.OUTPUT_DIR) or sienna_json_path.parent / "solved")
    raw_output = questionary.path(
        f"Output directory?  {PATH_PROMPT_HINT}", default=default_output
    ).ask()
    if raw_output is None:
        return None
    output_dir = Path(raw_output.strip()).expanduser()

    details: dict[str, Any] = {
        DetailKey.MODEL_TYPE: model_type,
        DetailKey.SIENNA_JSON_PATH: str(sienna_json_path),
        DetailKey.NETWORK_MODEL: network_model,
        DetailKey.UNIT_COMMITMENT: unit_commitment,
        DetailKey.SOLVER: solver,
        DetailKey.PRESOLVE: presolve,
        DetailKey.RUN_CROSSOVER: run_crossover,
        DetailKey.TIME_LIMIT_SECONDS: str(time_limit_seconds)
        if time_limit_seconds is not None
        else "",
        DetailKey.OUTPUT_DIR: str(output_dir),
    }

    try:
        with container() as scope:
            use_case = scope.get(SolveUseCase)
            result = use_case(
                SolveSiennaRequest(
                    sienna_json_path=sienna_json_path,
                    network_model=network_model,
                    output_dir=output_dir,
                    unit_commitment=UnitCommitmentTreatment(unit_commitment),
                    solver=HiGHSSolver(solver),
                    presolve=HiGHSPresolve(presolve),
                    run_crossover=HiGHSCrossover(run_crossover),
                    time_limit_seconds=time_limit_seconds,
                )
            )
    except UserInputError as exc:
        _print_user_error(exc)
        return details

    style = "fg:green" if result.is_success() else "fg:red"
    questionary.print(result.summary(), style=style)
    return details


def _parse_optional_date(raw: str) -> date | None:
    """A blank answer means "every snapshot"; anything else must be an ISO date."""
    if not raw.strip():
        return None
    return date.fromisoformat(raw.strip())


def _parse_look_ahead_days(raw: str) -> int:
    """Read the typed look-ahead; the use case owns whether the number itself is usable."""
    if not raw.strip():
        return DEFAULT_LOOK_AHEAD_DAYS
    try:
        return int(raw.strip())
    except ValueError:
        raise ValueError(f"invalid look-ahead, expected a whole number of days: {raw!r}") from None


def _run_solve_pypsa(
    container: Container, replay: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    replay = replay or {}
    raw_path = questionary.path(
        f"Path to PyPSA network?  {PATH_PROMPT_HINT}",
        default=str(replay.get(DetailKey.NETWORK_PATH, "")),
    ).ask()
    if raw_path is None:
        return None
    network_path = Path(raw_path.strip()).expanduser()
    if not network_path.exists():
        _print_user_error(UserInputError(f"path not found: {network_path}"))
        return None

    default_output = str(replay.get(DetailKey.OUTPUT_DIR) or network_path.parent / "solved")
    raw_output = questionary.path(
        f"Output directory?  {PATH_PROMPT_HINT}", default=default_output
    ).ask()
    if raw_output is None:
        return None
    output_dir = Path(raw_output.strip()).expanduser()

    raw_start = questionary.text(
        "Start date? (YYYY-MM-DD, blank = every snapshot)",
        default=str(replay.get(DetailKey.START_DATE, "")),
    ).ask()
    if raw_start is None:
        return None
    raw_end = questionary.text(
        "End date? (YYYY-MM-DD, blank = every snapshot)",
        default=str(replay.get(DetailKey.END_DATE, "")),
    ).ask()
    if raw_end is None:
        return None
    try:
        start = _parse_optional_date(raw_start)
        end = _parse_optional_date(raw_end)
    except ValueError:
        _print_user_error(
            UserInputError(f"invalid date, expected YYYY-MM-DD: {raw_start!r}/{raw_end!r}")
        )
        return None

    unit_commitment = questionary.select(
        "Unit commitment treatment? (exact = on/off as true binary decisions; "
        "linearised = faster relaxation, keeps start-up/min up-down as a continuous fraction)",
        choices=_UNIT_COMMITMENT_TREATMENTS,
        default=_select_default(replay.get(DetailKey.UNIT_COMMITMENT), _UNIT_COMMITMENT_TREATMENTS),
    ).ask()
    if unit_commitment is None:
        return None

    window = questionary.select(
        "How much of the range does one solve cover? (nothing carries from one window to "
        "the next, so a shorter window is faster but resets storage more often)",
        choices=_SOLVE_WINDOWS,
        default=_select_default(replay.get(DetailKey.SOLVE_WINDOW), _SOLVE_WINDOWS),
    ).ask()
    if window is None:
        return None

    raw_look_ahead = questionary.text(
        "Days to solve past the end of each window and then discard? (stops storage being "
        "emptied into a window's last hours)",
        default=str(replay.get(DetailKey.LOOK_AHEAD_DAYS, DEFAULT_LOOK_AHEAD_DAYS)),
    ).ask()
    if raw_look_ahead is None:
        return None
    try:
        look_ahead_days = _parse_look_ahead_days(raw_look_ahead)
    except ValueError as exc:
        _print_user_error(UserInputError(str(exc)))
        return None

    details: dict[str, Any] = {
        DetailKey.MODEL_TYPE: ModelType.PYPSA.value,
        DetailKey.NETWORK_PATH: str(network_path),
        DetailKey.OUTPUT_DIR: str(output_dir),
        DetailKey.START_DATE: str(start) if start is not None else "",
        DetailKey.END_DATE: str(end) if end is not None else "",
        DetailKey.UNIT_COMMITMENT: unit_commitment,
        DetailKey.SOLVE_WINDOW: window,
        DetailKey.LOOK_AHEAD_DAYS: str(look_ahead_days),
    }

    try:
        with container() as scope:
            use_case = scope.get(SolveUseCase)
            result = use_case(
                SolveNetworkRequest(
                    network_path=network_path,
                    output_dir=output_dir,
                    start=start,
                    end=end,
                    unit_commitment=UnitCommitmentTreatment(unit_commitment),
                    window=SolveWindowLength(window),
                    look_ahead_days=look_ahead_days,
                )
            )
    except UserInputError as exc:
        _print_user_error(exc)
        return details

    style = "fg:green" if result.is_success() else "fg:red"
    questionary.print(result.summary(), style=style)
    return details


def _collect_compare_side(
    container: Container,
    framework: str,
    pipelines: list[str],
    replay_pipeline: Any,
    replay_params: dict[str, Any] | None,
) -> CompareSide | None:
    """Pick the framework's results pipeline (when it has more than one) and its source params."""
    if len(pipelines) == 1:
        pipeline_name = pipelines[0]
    else:
        pipeline_name = questionary.select(
            f"Which {framework} results pipeline?",
            choices=sorted(pipelines),
            default=_select_default(replay_pipeline, pipelines),
        ).ask()
        if pipeline_name is None:
            return None

    with container() as scope:
        catalog = scope.get(PipelineCatalogUseCase)
        structure = catalog.get_structure(pipeline_name)
    source_params = collect_node_params(
        structure.source.params_schema, {}, framework, replay_params=replay_params
    )
    return CompareSide(framework=framework, pipeline=pipeline_name, source_params=source_params)


def _run_compare(
    container: Container, replay: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    replay = replay or {}
    try:
        with container() as scope:
            pipelines_by_framework = scope.get(CompareUseCase).comparable_frameworks()
    except UserInputError as exc:
        _print_user_error(exc)
        return None

    frameworks = sorted(pipelines_by_framework)
    framework_a = questionary.select(
        "First result's framework?",
        choices=frameworks,
        default=_select_default(replay.get(DetailKey.SIDE_A_FRAMEWORK), frameworks),
    ).ask()
    if framework_a is None:
        return None

    other_frameworks = [framework for framework in frameworks if framework != framework_a]
    framework_b = questionary.select(
        "Second result's framework?",
        choices=other_frameworks,
        default=_select_default(replay.get(DetailKey.SIDE_B_FRAMEWORK), other_frameworks),
    ).ask()
    if framework_b is None:
        return None

    side_a = _collect_compare_side(
        container,
        framework_a,
        pipelines_by_framework[framework_a],
        replay.get(DetailKey.SIDE_A_PIPELINE),
        replay.get(DetailKey.SIDE_A_PARAMS),
    )
    if side_a is None:
        return None
    side_b = _collect_compare_side(
        container,
        framework_b,
        pipelines_by_framework[framework_b],
        replay.get(DetailKey.SIDE_B_PIPELINE),
        replay.get(DetailKey.SIDE_B_PARAMS),
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
    }

    try:
        with container() as scope:
            use_case = scope.get(CompareUseCase)
            result = use_case(side_a, side_b, output_path)
    except UserInputError as exc:
        _print_user_error(exc)
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
        default=_select_default(replay.get(DetailKey.EXAMPLE), example_choices),
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
        _print_user_error(exc)
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
