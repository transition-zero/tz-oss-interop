"""The prompts of the solve command, one path for each model type that it runs.

Each path asks its questions into one answers object, then builds the request that the use
case runs and the details that history records from those answers.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, NamedTuple

import questionary
from dishka import Container

from interop.adapters.inbound.interactive_cli.history import DetailKey
from interop.adapters.inbound.interactive_cli.prompts import (
    choose_select_default,
    print_user_error,
)
from interop.adapters.inbound.interactive_cli.schema_prompts import PATH_PROMPT_HINT
from interop.ports.errors import UserInputError
from interop.ports.inbound.solve import (
    DEFAULT_LOOK_AHEAD_DAYS,
    ModelType,
    SolveExpansionRequest,
    SolveNetworkRequest,
    SolveRequest,
    SolveSiennaRequest,
    SolveUseCase,
)
from interop.ports.outbound.expansion import BalanceModel, InvestmentTreatment
from interop.ports.outbound.network_solver import SolveWindowLength
from interop.ports.outbound.solver import (
    HiGHSCrossover,
    HiGHSOptions,
    HiGHSPresolve,
    HiGHSSolver,
    UnservedEnergy,
)
from interop.ports.outbound.unit_commitment import UnitCommitmentTreatment

_MODEL_TYPES = [m.value for m in ModelType]
_NETWORK_MODELS = ["dcp", "ptdf", "copperplate"]
_SOLVER_ALGORITHMS = [s.value for s in HiGHSSolver]
_PRESOLVE_OPTIONS = [s.value for s in HiGHSPresolve]
_CROSSOVER_OPTIONS = [s.value for s in HiGHSCrossover]
_UNIT_COMMITMENT_TREATMENTS = [t.value for t in UnitCommitmentTreatment]
_UNSERVED_ENERGY_OPTIONS = [u.value for u in UnservedEnergy]
_SOLVE_WINDOWS = [w.value for w in SolveWindowLength]
_BALANCE_MODELS = [b.value for b in BalanceModel]
_INVESTMENT_TREATMENTS = [t.value for t in InvestmentTreatment]

_BALANCE_MODEL_PROMPT = (
    "Balance model? (single-region = one zone; multi-region = zone by zone; nodal = bus by bus)"
)

# ContinuousInvestment builds any amount of capacity; IntegerInvestment builds whole units
# only, which is a mixed-integer problem and much slower.
_INVESTMENT_TREATMENT_PROMPT = (
    "Investment treatment? (continuous = build any amount of capacity; integer = build "
    "whole units only, which is slower)"
)

# PowerSimulations has no relaxed unit commitment formulation, so the two answers mean
# something different here from what they mean on the PyPSA path.
_SIENNA_UNIT_COMMITMENT_PROMPT = (
    "Unit commitment treatment? (exact = on/off as true binary decisions, applying the "
    "start-up cost and the minimum up and down times; linearised = economic dispatch, "
    "which is faster and applies neither)"
)

_PYPSA_UNIT_COMMITMENT_PROMPT = (
    "Unit commitment treatment? (exact = on/off as true binary decisions; "
    "linearised = faster relaxation, keeps start-up/min up-down as a continuous fraction)"
)

_SOLVE_WINDOW_PROMPT = (
    "How much of the range does one solve cover? (nothing carries from one window to "
    "the next, so a shorter window is faster but resets storage more often)"
)

_LOOK_AHEAD_PROMPT = (
    "Days to solve past the end of each window and then discard? (stops storage being "
    "emptied into a window's last hours)"
)

_UNSERVED_ENERGY_PROMPT = (
    "Unserved energy? (refused = every load is met, so one short hour makes the solve "
    "infeasible; penalised = a shortfall goes unserved at a high penalty cost)"
)

_POWER_SIMULATIONS_PACKAGES = "the PowerSimulations.jl solver packages"
_POWER_SYSTEMS_INVESTMENTS_PACKAGES = "the PowerSystemsInvestments.jl packages"

_SOLVED_DIR = "solved"
_EXPANDED_DIR = "expanded"


def run_solve(container: Container, replay: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Ask which model type to solve, then run the path of that type."""
    recorded = replay or {}
    model_type = _prompt_choice("Model type?", _MODEL_TYPES, recorded.get(DetailKey.MODEL_TYPE))
    if model_type is None:
        return None
    if model_type == ModelType.PYPSA:
        return _run_solve_network(container, recorded)
    if model_type == ModelType.SIENNA_INVESTMENTS:
        return _run_solve_expansion(container, recorded)
    return _run_solve_dispatch(container, recorded)


def _run_solve_dispatch(container: Container, replay: dict[str, Any]) -> dict[str, Any] | None:
    """Dispatch a Sienna system with PowerSimulations."""
    if not _prompt_download_consent(
        container, _POWER_SIMULATIONS_PACKAGES, _is_dispatch_provisioned
    ):
        return None
    answers = _prompt_dispatch_answers(replay)
    if answers is None:
        return None
    return _run_solve_request(
        container, _build_dispatch_request(answers), _build_dispatch_details(answers)
    )


def _run_solve_expansion(container: Container, replay: dict[str, Any]) -> dict[str, Any] | None:
    """Expand a Sienna portfolio, asking only what the portfolio itself does not state."""
    if not _prompt_download_consent(
        container, _POWER_SYSTEMS_INVESTMENTS_PACKAGES, _is_expansion_provisioned
    ):
        return None
    answers = _prompt_expansion_answers(replay)
    if answers is None:
        return None
    return _run_solve_request(
        container, _build_expansion_request(answers), _build_expansion_details(answers)
    )


def _run_solve_network(container: Container, replay: dict[str, Any]) -> dict[str, Any] | None:
    """Solve a PyPSA network with HiGHS, over a range of dates."""
    answers = _prompt_network_answers(replay)
    if answers is None:
        return None
    return _run_solve_request(
        container, _build_network_request(answers), _build_network_details(answers)
    )


def _run_solve_request(
    container: Container, request: SolveRequest, details: dict[str, Any]
) -> dict[str, Any]:
    """Run the request, print its summary or its user error, and give back the details."""
    try:
        with container() as scope:
            result = scope.get(SolveUseCase)(request)
    except UserInputError as exc:
        print_user_error(exc)
        return details
    questionary.print(result.summary(), style="fg:green" if result.is_success() else "fg:red")
    return details


def _is_dispatch_provisioned(use_case: SolveUseCase) -> bool:
    return use_case.is_provisioned()


def _is_expansion_provisioned(use_case: SolveUseCase) -> bool:
    return use_case.is_expansion_provisioned()


def _prompt_download_consent(
    container: Container, packages: str, is_provisioned: Callable[[SolveUseCase], bool]
) -> bool:
    """Warn before a first run downloads Julia, and ask whether to go on.

    A run whose packages are already installed asks nothing.
    """
    try:
        with container() as scope:
            is_ready = is_provisioned(scope.get(SolveUseCase))
    except UserInputError as exc:
        print_user_error(exc)
        return False
    if is_ready:
        return True
    questionary.print(
        f"Julia and {packages} will be downloaded and compiled before solving. This needs "
        "an internet connection; progress is printed as it runs."
    )
    if questionary.confirm("Download and continue?").ask():
        return True
    questionary.print("Solve cancelled.")
    return False


@dataclass(frozen=True)
class _DispatchAnswers:
    """Everything the dispatch prompts collected."""

    sienna_json_path: Path
    network_model: str
    unserved_energy: UnservedEnergy
    unit_commitment: UnitCommitmentTreatment
    highs: HiGHSOptions
    output_dir: Path


def _prompt_dispatch_answers(replay: dict[str, Any]) -> _DispatchAnswers | None:
    sienna_json_path = _prompt_input_file(
        "Path to PowerSimulations.jl system JSON?", replay.get(DetailKey.SIENNA_JSON_PATH)
    )
    if sienna_json_path is None:
        return None
    network_model = _prompt_choice(
        "Network model?", _NETWORK_MODELS, replay.get(DetailKey.NETWORK_MODEL)
    )
    if network_model is None:
        return None
    unserved_energy = _prompt_unserved_energy(replay)
    if unserved_energy is None:
        return None
    unit_commitment = _prompt_unit_commitment(_SIENNA_UNIT_COMMITMENT_PROMPT, replay)
    if unit_commitment is None:
        return None
    highs = _prompt_highs_options(replay)
    if highs is None:
        return None
    output_dir = _prompt_output_dir(replay, sienna_json_path.parent / _SOLVED_DIR)
    if output_dir is None:
        return None
    return _DispatchAnswers(
        sienna_json_path, network_model, unserved_energy, unit_commitment, highs, output_dir
    )


def _build_dispatch_request(answers: _DispatchAnswers) -> SolveSiennaRequest:
    return SolveSiennaRequest(
        sienna_json_path=answers.sienna_json_path,
        network_model=answers.network_model,
        output_dir=answers.output_dir,
        unserved_energy=answers.unserved_energy,
        unit_commitment=answers.unit_commitment,
        highs=answers.highs,
    )


def _build_dispatch_details(answers: _DispatchAnswers) -> dict[str, Any]:
    return {
        DetailKey.MODEL_TYPE: ModelType.SIENNA.value,
        DetailKey.SIENNA_JSON_PATH: str(answers.sienna_json_path),
        DetailKey.NETWORK_MODEL: answers.network_model,
        DetailKey.UNSERVED_ENERGY: answers.unserved_energy.value,
        DetailKey.UNIT_COMMITMENT: answers.unit_commitment.value,
        **_build_highs_details(answers.highs),
        DetailKey.OUTPUT_DIR: str(answers.output_dir),
    }


@dataclass(frozen=True)
class _ExpansionAnswers:
    """Everything the expansion prompts collected, past what the portfolio states itself."""

    portfolio_json_path: Path
    balance_model: BalanceModel
    investment_treatment: InvestmentTreatment
    discount_rate: float | None
    highs: HiGHSOptions
    output_dir: Path


def _prompt_expansion_answers(replay: dict[str, Any]) -> _ExpansionAnswers | None:
    portfolio_json_path = _prompt_input_file(
        "Path to the PowerSystemsInvestments portfolio JSON?",
        replay.get(DetailKey.PORTFOLIO_JSON_PATH),
    )
    if portfolio_json_path is None:
        return None
    balance_model = _prompt_choice(
        _BALANCE_MODEL_PROMPT, _BALANCE_MODELS, replay.get(DetailKey.BALANCE_MODEL)
    )
    if balance_model is None:
        return None
    investment_treatment = _prompt_choice(
        _INVESTMENT_TREATMENT_PROMPT,
        _INVESTMENT_TREATMENTS,
        replay.get(DetailKey.INVESTMENT_TREATMENT),
    )
    if investment_treatment is None:
        return None
    discount_rate = _prompt_optional_number(
        _OptionalNumberPrompt(
            "Discount rate? (blank = the rate the portfolio states)", "discount rate"
        ),
        replay.get(DetailKey.DISCOUNT_RATE),
    )
    if isinstance(discount_rate, _NoAnswer):
        return None
    highs = _prompt_highs_options(replay)
    if highs is None:
        return None
    output_dir = _prompt_output_dir(replay, portfolio_json_path.parent / _EXPANDED_DIR)
    if output_dir is None:
        return None
    return _ExpansionAnswers(
        portfolio_json_path,
        BalanceModel(balance_model),
        InvestmentTreatment(investment_treatment),
        discount_rate,
        highs,
        output_dir,
    )


def _build_expansion_request(answers: _ExpansionAnswers) -> SolveExpansionRequest:
    return SolveExpansionRequest(
        portfolio_json_path=answers.portfolio_json_path,
        balance_model=answers.balance_model,
        output_dir=answers.output_dir,
        investment_treatment=answers.investment_treatment,
        discount_rate=answers.discount_rate,
        highs=answers.highs,
    )


def _build_expansion_details(answers: _ExpansionAnswers) -> dict[str, Any]:
    return {
        DetailKey.MODEL_TYPE: ModelType.SIENNA_INVESTMENTS.value,
        DetailKey.PORTFOLIO_JSON_PATH: str(answers.portfolio_json_path),
        DetailKey.BALANCE_MODEL: answers.balance_model.value,
        DetailKey.INVESTMENT_TREATMENT: answers.investment_treatment.value,
        DetailKey.DISCOUNT_RATE: _serialise_optional_number(answers.discount_rate),
        **_build_highs_details(answers.highs),
        DetailKey.OUTPUT_DIR: str(answers.output_dir),
    }


@dataclass(frozen=True)
class _NetworkAnswers:
    """Everything the PyPSA solve prompts collected."""

    network_path: Path
    output_dir: Path
    start: date | None
    end: date | None
    unit_commitment: UnitCommitmentTreatment
    window: SolveWindowLength
    unserved_energy: UnservedEnergy
    look_ahead_days: int


def _prompt_network_answers(replay: dict[str, Any]) -> _NetworkAnswers | None:
    network_path = _prompt_network_path(replay)
    if network_path is None:
        return None
    output_dir = _prompt_output_dir(replay, network_path.parent / _SOLVED_DIR)
    if output_dir is None:
        return None
    dates = _prompt_date_range(replay)
    if dates is None:
        return None
    unit_commitment = _prompt_unit_commitment(_PYPSA_UNIT_COMMITMENT_PROMPT, replay)
    if unit_commitment is None:
        return None
    window = _prompt_choice(
        _SOLVE_WINDOW_PROMPT, _SOLVE_WINDOWS, replay.get(DetailKey.SOLVE_WINDOW)
    )
    if window is None:
        return None
    unserved_energy = _prompt_unserved_energy(replay)
    if unserved_energy is None:
        return None
    look_ahead_days = _prompt_look_ahead_days(replay)
    if look_ahead_days is None:
        return None
    return _NetworkAnswers(
        network_path,
        output_dir,
        dates.start,
        dates.end,
        unit_commitment,
        SolveWindowLength(window),
        unserved_energy,
        look_ahead_days,
    )


def _build_network_request(answers: _NetworkAnswers) -> SolveNetworkRequest:
    return SolveNetworkRequest(
        network_path=answers.network_path,
        output_dir=answers.output_dir,
        start=answers.start,
        end=answers.end,
        unit_commitment=answers.unit_commitment,
        window=answers.window,
        look_ahead_days=answers.look_ahead_days,
        unserved_energy=answers.unserved_energy,
    )


def _build_network_details(answers: _NetworkAnswers) -> dict[str, Any]:
    return {
        DetailKey.MODEL_TYPE: ModelType.PYPSA.value,
        DetailKey.NETWORK_PATH: str(answers.network_path),
        DetailKey.OUTPUT_DIR: str(answers.output_dir),
        DetailKey.START_DATE: _serialise_optional_date(answers.start),
        DetailKey.END_DATE: _serialise_optional_date(answers.end),
        DetailKey.UNIT_COMMITMENT: answers.unit_commitment.value,
        DetailKey.SOLVE_WINDOW: answers.window.value,
        DetailKey.UNSERVED_ENERGY: answers.unserved_energy.value,
        DetailKey.LOOK_AHEAD_DAYS: str(answers.look_ahead_days),
    }


def _prompt_highs_options(replay: dict[str, Any]) -> HiGHSOptions | None:
    """The four HiGHS answers, or None where the user cancelled or typed an unreadable limit."""
    solver = _prompt_choice(
        "HiGHS solver algorithm?", _SOLVER_ALGORITHMS, replay.get(DetailKey.SOLVER)
    )
    if solver is None:
        return None
    presolve = _prompt_choice(
        "Presolve? (choose = HiGHS decides automatically)",
        _PRESOLVE_OPTIONS,
        replay.get(DetailKey.PRESOLVE),
    )
    if presolve is None:
        return None
    run_crossover = _prompt_choice(
        "Run crossover after IPM? (choose = HiGHS decides automatically)",
        _CROSSOVER_OPTIONS,
        replay.get(DetailKey.RUN_CROSSOVER),
    )
    if run_crossover is None:
        return None
    time_limit_seconds = _prompt_optional_number(
        _OptionalNumberPrompt("Time limit in seconds? (blank = no limit)", "time limit"),
        replay.get(DetailKey.TIME_LIMIT_SECONDS),
    )
    if isinstance(time_limit_seconds, _NoAnswer):
        return None
    return HiGHSOptions(
        HiGHSSolver(solver),
        HiGHSPresolve(presolve),
        HiGHSCrossover(run_crossover),
        time_limit_seconds,
    )


def _build_highs_details(highs: HiGHSOptions) -> dict[str, str]:
    return {
        DetailKey.SOLVER: highs.solver.value,
        DetailKey.PRESOLVE: highs.presolve.value,
        DetailKey.RUN_CROSSOVER: highs.run_crossover.value,
        DetailKey.TIME_LIMIT_SECONDS: _serialise_optional_number(highs.time_limit_seconds),
    }


def _prompt_choice(message: str, choices: list[str], recorded: Any) -> str | None:
    """One select, defaulting to the recorded answer while it is still a choice."""
    answer: str | None = questionary.select(
        message, choices=choices, default=choose_select_default(recorded, choices)
    ).ask()
    return answer


def _prompt_unserved_energy(replay: dict[str, Any]) -> UnservedEnergy | None:
    answer = _prompt_choice(
        _UNSERVED_ENERGY_PROMPT, _UNSERVED_ENERGY_OPTIONS, replay.get(DetailKey.UNSERVED_ENERGY)
    )
    return None if answer is None else UnservedEnergy(answer)


def _prompt_unit_commitment(message: str, replay: dict[str, Any]) -> UnitCommitmentTreatment | None:
    answer = _prompt_choice(
        message, _UNIT_COMMITMENT_TREATMENTS, replay.get(DetailKey.UNIT_COMMITMENT)
    )
    return None if answer is None else UnitCommitmentTreatment(answer)


def _prompt_input_file(message: str, recorded: Any) -> Path | None:
    """A path to a file that must exist, or None where the user cancelled or it is not there."""
    raw_path = questionary.path(f"{message}  {PATH_PROMPT_HINT}", default=str(recorded or "")).ask()
    if raw_path is None:
        return None
    path = Path(raw_path.strip()).expanduser()
    if not path.is_file():
        print_user_error(UserInputError(f"file not found: {path}"))
        return None
    return path


def _prompt_network_path(replay: dict[str, Any]) -> Path | None:
    """A network file or a directory of them, or None where the user cancelled or it is absent."""
    raw_path = questionary.path(
        f"Path to PyPSA network?  {PATH_PROMPT_HINT}",
        default=str(replay.get(DetailKey.NETWORK_PATH, "")),
    ).ask()
    if raw_path is None:
        return None
    network_path = Path(raw_path.strip()).expanduser()
    if not network_path.exists():
        print_user_error(UserInputError(f"path not found: {network_path}"))
        return None
    return network_path


def _prompt_output_dir(replay: dict[str, Any], fallback: Path) -> Path | None:
    default_output = str(replay.get(DetailKey.OUTPUT_DIR) or fallback)
    raw_output = questionary.path(
        f"Output directory?  {PATH_PROMPT_HINT}", default=default_output
    ).ask()
    return None if raw_output is None else Path(raw_output.strip()).expanduser()


@dataclass(frozen=True)
class _DateRange:
    """The inclusive calendar dates a PyPSA solve covers; None at an end means every snapshot."""

    start: date | None
    end: date | None


def _prompt_date_range(replay: dict[str, Any]) -> _DateRange | None:
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
        return _DateRange(_parse_optional_date(raw_start), _parse_optional_date(raw_end))
    except ValueError:
        print_user_error(
            UserInputError(f"invalid date, expected YYYY-MM-DD: {raw_start!r}/{raw_end!r}")
        )
        return None


def _parse_optional_date(raw: str) -> date | None:
    """A blank answer means "every snapshot"; anything else must be an ISO date."""
    if not raw.strip():
        return None
    return date.fromisoformat(raw.strip())


def _serialise_optional_date(value: date | None) -> str:
    return "" if value is None else str(value)


def _prompt_look_ahead_days(replay: dict[str, Any]) -> int | None:
    raw_look_ahead = questionary.text(
        _LOOK_AHEAD_PROMPT,
        default=str(replay.get(DetailKey.LOOK_AHEAD_DAYS, DEFAULT_LOOK_AHEAD_DAYS)),
    ).ask()
    if raw_look_ahead is None:
        return None
    try:
        return _parse_look_ahead_days(raw_look_ahead)
    except ValueError as exc:
        print_user_error(UserInputError(str(exc)))
        return None


def _parse_look_ahead_days(raw: str) -> int:
    """Read the typed look-ahead; the use case owns whether the number itself is usable."""
    if not raw.strip():
        return DEFAULT_LOOK_AHEAD_DAYS
    try:
        return int(raw.strip())
    except ValueError:
        raise ValueError(f"invalid look-ahead, expected a whole number of days: {raw!r}") from None


class _NoAnswer:
    """What a number prompt gives where the user cancelled it or typed what nobody can read."""


_NO_ANSWER = _NoAnswer()


class _OptionalNumberPrompt(NamedTuple):
    """A text prompt for a number that a blank answer leaves unstated, and what it names."""

    message: str
    label: str


def _prompt_optional_number(
    prompt: _OptionalNumberPrompt, recorded: Any
) -> float | None | _NoAnswer:
    """The typed number, None for a blank answer, or no answer at all."""
    raw = questionary.text(prompt.message, default=str(recorded or "")).ask()
    if raw is None:
        return _NO_ANSWER
    return _parse_optional_number(raw, prompt.label)


def _parse_optional_number(raw: str, label: str) -> float | None | _NoAnswer:
    if not raw.strip():
        return None
    try:
        return float(raw.strip())
    except ValueError:
        print_user_error(UserInputError(f"invalid {label}: {raw!r}"))
        return _NO_ANSWER


def _serialise_optional_number(value: float | None) -> str:
    return "" if value is None else str(value)
