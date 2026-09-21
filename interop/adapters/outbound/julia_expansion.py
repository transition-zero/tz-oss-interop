"""Runs PowerSystemsInvestments.jl via juliacall to expand a Sienna portfolio.

Every Julia call below is public API on the packages as published. This composes them; it
adds nothing to them. The portfolio carries no time series, so the series companion beside it
is attached to the components that came off disk before the model is built.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel

from interop.adapters.outbound.julia_packages import declare_julia_packages
from interop.plugins.shared.power_systems_investments_schema import (
    SERIES_JSON_SUFFIX,
    SeriesDocument,
)
from interop.ports.errors import UserInputError
from interop.ports.outbound.expansion import BalanceModel, ExpansionPort, InvestmentTreatment
from interop.ports.outbound.solver import HiGHSCrossover, HiGHSPresolve, HiGHSSolver

log = logging.getLogger(__name__)

_JSON_SUFFIX = ".json"

_BALANCE_MODELS: dict[BalanceModel, str] = {
    BalanceModel.SINGLE_REGION: "SingleRegionBalanceModel",
    BalanceModel.MULTI_REGION: "MultiRegionBalanceModel",
    BalanceModel.NODAL: "NodalBalanceModel",
}

_INVESTMENT_FORMULATIONS: dict[InvestmentTreatment, str] = {
    InvestmentTreatment.CONTINUOUS: "ContinuousInvestment",
    InvestmentTreatment.INTEGER: "IntegerInvestment",
}

# One formulation triple per technology type: how a plan may build it, how it runs, and how
# its contribution to a feasibility period is counted. A demand requirement is not built, so
# its investment formulation is the one that states so.
_DEMAND_INVESTMENT = "StaticLoadInvestment"
_FEASIBILITY_FORMULATION = "BasicDispatchFeasibility"
_TECHNOLOGY_MODELS: tuple[tuple[str, str], ...] = (
    ("PSIP.DemandRequirement{PSY.PowerLoad}", "BasicDispatch"),
    ("PSIP.SupplyTechnology{PSY.RenewableDispatch}", "BasicDispatch"),
    ("PSIP.SupplyTechnology{PSY.ThermalStandard}", "BasicDispatch"),
    ("PSIP.SupplyTechnology{PSY.HydroDispatch}", "BasicDispatch"),
    ("PSIP.StorageTechnology{PSY.EnergyReservoirStorage}", "CyclicalStorageDispatch"),
    ("PSIP.AggregateTransportTechnology{PSY.ACBranch}", "BasicDispatch"),
)

# How far from proven optimality a mixed-integer run may stop, matching the dispatch path.
_MILP_REL_GAP = 0.01


def _julia_str(path: Path) -> str:
    return str(path).replace("\\", "/").replace('"', '\\"')


@dataclass(frozen=True)
class _OperationalSlice:
    """One representative day every technology states a profile over."""

    year: str
    rep_day: int
    weight: float
    timestamps: tuple[str, ...]


class JuliaExpansionConfig(BaseModel):
    powersystemsinvestments_jl_path: Path | None = None
    powersystemsinvestmentsportfolios_jl_path: Path | None = None


class JuliaExpansionAdapter(ExpansionPort):
    """Runs PowerSystemsInvestments.jl via juliacall to expand a Sienna portfolio."""

    name: ClassVar[str] = "julia_expansion"
    port: ClassVar[type] = ExpansionPort
    config_schema: ClassVar[type[BaseModel] | None] = JuliaExpansionConfig

    def __init__(self, config: JuliaExpansionConfig | None = None) -> None:
        settings = config or JuliaExpansionConfig()
        self._dev_checkout_paths: dict[str, Path | None] = {
            "PowerSystemsInvestments": settings.powersystemsinvestments_jl_path,
            "PowerSystemsInvestmentsPortfolios": (
                settings.powersystemsinvestmentsportfolios_jl_path
            ),
        }

    def is_provisioned(self) -> bool:
        """Report whether Julia and the declared packages are already installed."""
        declare_julia_packages(self._dev_checkout_paths)
        import juliapkg  # noqa: PLC0415

        return bool(juliapkg.resolve(dry_run=True))

    def solve_expansion(
        self,
        portfolio_json_path: Path,
        balance_model: BalanceModel,
        output_dir: Path | None = None,
        *,
        investment_treatment: InvestmentTreatment = InvestmentTreatment.CONTINUOUS,
        discount_rate: float | None = None,
        solver: HiGHSSolver = HiGHSSolver.SIMPLEX,
        presolve: HiGHSPresolve = HiGHSPresolve.CHOOSE,
        run_crossover: HiGHSCrossover = HiGHSCrossover.CHOOSE,
        time_limit_seconds: float | None = None,
    ) -> tuple[str, float]:
        if not portfolio_json_path.is_file():
            raise UserInputError(f"file not found: {portfolio_json_path}")
        series_path = _series_path(portfolio_json_path)
        document = _read_series_document(series_path)
        resolved_output_dir = output_dir or (portfolio_json_path.parent / "expanded")
        resolved_output_dir.mkdir(parents=True, exist_ok=True)
        return _run_expansion(
            self._bootstrap_julia(),
            _ExpansionRequest(
                portfolio_json_path=portfolio_json_path,
                document=document,
                output_dir=resolved_output_dir,
                balance_model=balance_model,
                investment_treatment=investment_treatment,
                discount_rate=discount_rate,
                highs_args=_build_highs_args(
                    solver, presolve, run_crossover, time_limit_seconds, investment_treatment
                ),
            ),
        )

    def _bootstrap_julia(self) -> Any:
        os.environ.setdefault("PYTHON_JULIACALL_HANDLE_SIGNALS", "yes")
        declare_julia_packages(self._dev_checkout_paths)
        log.info(
            "Preparing the Julia environment. The first run downloads Julia and the "
            "PowerSystemsInvestments.jl packages and compiles them. Later runs start much "
            "faster."
        )
        import faulthandler  # noqa: PLC0415

        faulthandler.disable()
        from juliacall import Main as jl  # noqa: PLC0415

        return jl


@dataclass(frozen=True)
class _ExpansionRequest:
    """Everything one run needs, past the Julia session itself."""

    portfolio_json_path: Path
    document: dict[str, Any]
    output_dir: Path
    balance_model: BalanceModel
    investment_treatment: InvestmentTreatment
    discount_rate: float | None
    highs_args: str


def _series_path(portfolio_json_path: Path) -> Path:
    """The companion beside the portfolio, named the way the sink wrote it."""
    stem = portfolio_json_path.name
    if stem.endswith(_JSON_SUFFIX):
        stem = stem[: -len(_JSON_SUFFIX)]
    return portfolio_json_path.parent / f"{stem}{SERIES_JSON_SUFFIX}"


def _read_series_document(series_path: Path) -> dict[str, Any]:
    if not series_path.is_file():
        raise UserInputError(
            f"the portfolio names no time series of its own, and its companion "
            f"{series_path} is not there. Run the translation that writes both."
        )
    document: dict[str, Any] = json.loads(series_path.read_text(encoding="utf-8"))
    return document


def _build_slices(document: dict[str, Any]) -> list[_OperationalSlice]:
    """One slice per (year, representative day) the records fall in, in the model's own order."""
    by_key: dict[tuple[str, int], _OperationalSlice] = {}
    for record in document[SeriesDocument.RECORDS]:
        key = (record[SeriesDocument.YEAR], record[SeriesDocument.REPRESENTATIVE_DAY])
        by_key.setdefault(key, _build_slice(record))
    return [by_key[key] for key in sorted(by_key)]


def _build_slice(record: dict[str, Any]) -> _OperationalSlice:
    return _OperationalSlice(
        year=record[SeriesDocument.YEAR],
        rep_day=record[SeriesDocument.REPRESENTATIVE_DAY],
        weight=record[SeriesDocument.WEIGHT],
        timestamps=tuple(_build_timestamps(record)),
    )


def _build_timestamps(record: dict[str, Any]) -> list[str]:
    """The instant of every value in one slice, which the model indexes its variables by."""
    start = datetime.fromisoformat(record[SeriesDocument.INITIAL_TIMESTAMP])
    step = timedelta(seconds=record[SeriesDocument.RESOLUTION_SECONDS])
    return [
        (start + step * index).isoformat() for index in range(len(record[SeriesDocument.VALUES]))
    ]


def _build_highs_args(
    solver: str,
    presolve: str,
    run_crossover: str,
    time_limit_seconds: float | None,
    investment_treatment: InvestmentTreatment,
) -> str:
    attributes: list[tuple[str, str]] = [
        ('"log_to_console"', "true"),
        ('"solver"', f'"{solver}"'),
        ('"presolve"', f'"{presolve}"'),
        ('"run_crossover"', f'"{run_crossover}"'),
    ]
    if investment_treatment is InvestmentTreatment.INTEGER:
        attributes.append(('"mip_rel_gap"', str(_MILP_REL_GAP)))
    if time_limit_seconds is not None:
        attributes.append(('"time_limit"', str(float(time_limit_seconds))))
    return ", ".join(f"{key} => {value}" for key, value in attributes)


def _run_expansion(jl: Any, request: _ExpansionRequest) -> tuple[str, float]:
    """Build and solve the expansion, re-raising a Julia error as a user error."""
    from juliacall import JuliaError  # noqa: PLC0415

    try:
        return _run_expansion_inner(jl, request)
    except JuliaError as exc:
        raise UserInputError(f"Julia expansion error:\n{exc}") from exc


def _run_expansion_inner(jl: Any, request: _ExpansionRequest) -> tuple[str, float]:
    log.info("=== 1. Loading the portfolio ===")
    jl.seval("""
        using PowerSystems, PowerSystemsInvestmentsPortfolios, PowerSystemsInvestments
        using InfrastructureSystems, HiGHS, Dates, TimeSeries, CSV, DataFrames
        const IS = InfrastructureSystems
        const PSY = PowerSystems
        const PSIP = PowerSystemsInvestmentsPortfolios
        const PSIN = PowerSystemsInvestments
    """)
    jl.seval(f'global portfolio = PSIP.Portfolio("{_julia_str(request.portfolio_json_path)}")')

    log.info("=== 2. Attaching the time series the portfolio cannot carry ===")
    _attach_series(jl, request.document)

    log.info("=== 3. Building the investment model template ===")
    _build_template(jl, request)
    models = _set_technology_models(jl, request.investment_treatment)
    log.info("technology models set: %s", ", ".join(models) or "none")

    log.info("=== 4. Building the model ===")
    jl.seval(f"""
        global model = PSIN.InvestmentModel(
            template, PSIN.SingleInstanceSolve, portfolio;
            optimizer = PSIN.optimizer_with_attributes(HiGHS.Optimizer, {request.highs_args}),
            portfolio_to_file = false,
            store_variable_names = true,
        )
        PSIN.build!(model; output_dir = "{_julia_str(request.output_dir)}")
    """)

    log.info("=== 5. Solving ===")
    run_status = jl.seval("PSIN.solve!(model)")
    objective = jl.seval("""
        global results = PSIN.OptimizationProblemResults(model)
        IS.Optimization.get_objective_value(results)
    """)

    log.info("=== 6. Exporting the decisions ===")
    _export_variables(jl, request.output_dir)
    log.info("Results written to %s", request.output_dir)
    return str(run_status), float(objective)


def _attach_series(jl: Any, document: dict[str, Any]) -> None:
    """Put each record on the component that came off disk, under the features it is read by."""
    attach = jl.seval("""
        function (portfolio, type_name, component_name, series_name, year, rep_day,
                  timestamps, values)
            technology_type = getproperty(PSIP, Symbol(type_name))
            component = first(IS.get_components(
                x -> PSIP.get_name(x) == component_name, technology_type, portfolio.data))
            stamps = [DateTime(String(t)) for t in timestamps]
            data = TimeSeries.TimeArray(stamps, [Float64(v) for v in values])
            PSIP.add_time_series!(portfolio, component,
                IS.SingleTimeSeries(String(series_name), data);
                year = String(year), rep_day = Int(rep_day))
            return nothing
        end
    """)
    for record in document[SeriesDocument.RECORDS]:
        attach(
            jl.portfolio,
            record[SeriesDocument.COMPONENT_TYPE],
            record[SeriesDocument.COMPONENT_NAME],
            record[SeriesDocument.SERIES_NAME],
            record[SeriesDocument.YEAR],
            record[SeriesDocument.REPRESENTATIVE_DAY],
            _build_timestamps(record),
            record[SeriesDocument.VALUES],
        )
    log.info("attached %d time series", len(document[SeriesDocument.RECORDS]))


def _build_template(jl: Any, request: _ExpansionRequest) -> None:
    """The periods a plan builds over, the days it is run over, and the network it respects."""
    slices = _build_slices(request.document)
    discount_rate = _read_discount_rate(jl, request.discount_rate)
    periods = ", ".join(
        f'(Date("{period[SeriesDocument.START]}"), Date("{period[SeriesDocument.END]}"))'
        for period in request.document[SeriesDocument.PERIODS]
    )
    operational_days = ", ".join(
        "[" + ", ".join(f'DateTime("{stamp}")' for stamp in one.timestamps) + "]" for one in slices
    )
    weights = ", ".join(str(float(one.weight)) for one in slices)
    jl.seval(f"""
        global template = PSIN.InvestmentModelTemplate(
            PSIN.DiscountedCashFlow({discount_rate},
                Year(PSIP.get_base_year(portfolio)), [{periods}]),
            PSIN.OperationalRepresentativeDays([{operational_days}], [{weights}]),
            PSIN.RepresentativePeriods(Vector{{Vector{{Dates}}}}()),
            PSIN.TransportModel(PSIN.{_BALANCE_MODELS[request.balance_model]};
                                use_slacks = false),
        )
    """)


def _read_discount_rate(jl: Any, stated: float | None) -> float:
    """The rate the plan discounts by, put on the portfolio because the model reads it there.

    The model builds its own container from the portfolio rather than from the template, so a
    rate given on the run has to reach the portfolio itself to take effect.
    """
    discount_rate = (
        float(jl.seval("PSIP.get_discount_rate(portfolio)")) if stated is None else stated
    )
    if discount_rate <= 0.0:
        raise UserInputError(
            "the portfolio states a discount rate of "
            f"{discount_rate}, and the capital recovery factor divides by it. "
            "Give a positive rate on the run instead."
        )
    jl.seval(f"PSIP.set_discount_rate!(portfolio, {discount_rate})")
    return discount_rate


def _set_technology_models(jl: Any, investment_treatment: InvestmentTreatment) -> list[str]:
    """One formulation triple per type the portfolio holds, and none for a type it does not."""
    investment = _INVESTMENT_FORMULATIONS[investment_treatment]
    set_models: list[str] = []
    for technology_type, operations in _TECHNOLOGY_MODELS:
        if not _holds_any(jl, technology_type):
            continue
        formulation = _DEMAND_INVESTMENT if "DemandRequirement" in technology_type else investment
        jl.seval(f"""
            PSIN.set_technology_model!(template, portfolio, {technology_type},
                PSIN.{formulation}, PSIN.{operations}, PSIN.{_FEASIBILITY_FORMULATION})
        """)
        set_models.append(technology_type)
    return set_models


def _holds_any(jl: Any, technology_type: str) -> bool:
    return bool(
        jl.seval(f"length(collect(IS.get_components({technology_type}, portfolio.data))) > 0")
    )


def _export_variables(jl: Any, output_dir: Path) -> None:
    """One CSV per decision the run took, in the layout the dispatch path already writes."""
    jl.seval(f"""
        let
            root = joinpath("{_julia_str(output_dir)}", "results_wide", "variables")
            mkpath(root)
            for name in IS.Optimization.list_variable_names(results)
                try
                    CSV.write(joinpath(root, string(name, ".csv")),
                              PSIN.read_variable(results, name))
                catch err
                    @warn "variable export failed" name=name exception=err
                end
            end
        end
    """)
