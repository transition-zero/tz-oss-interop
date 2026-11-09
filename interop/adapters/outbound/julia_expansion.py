"""Runs PowerSystemsInvestments.jl via juliacall to expand a Sienna portfolio.

Every Julia call below is public API on the packages as published. This composes them; it
adds nothing to them. The portfolio carries no time series, so the series companion beside it
is attached to the components that came off disk before the model is built.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel, ValidationError

from interop.adapters.outbound.julia_packages import EXPANSION_PACKAGES, JuliaEnvironment
from interop.adapters.outbound.julia_session import (
    MIP_GAP_ATTRIBUTE,
    HiGHSAttribute,
    build_highs_args,
    is_julia_provisioned,
    reject_julia_errors,
    require_julia,
)
from interop.adapters.outbound.julia_strings import build_julia_path_text
from interop.plugins.shared.power_systems_investments_schema import (
    MODELLED_TECHNOLOGIES,
    ModelledTechnology,
)
from interop.plugins.shared.warning_text import name_a_few
from interop.ports.errors import UserInputError
from interop.ports.outbound.expansion import (
    INVESTMENT_FORMULATIONS,
    SERIES_JSON_SUFFIX,
    BalanceModel,
    ExpansionOutcome,
    ExpansionPort,
    ExpansionResultsLayout,
    InvestmentTreatment,
    PortfolioSeries,
)
from interop.ports.outbound.solver import HiGHSOptions

log = logging.getLogger(__name__)

_JSON_SUFFIX = ".json"

_BALANCE_MODELS: dict[BalanceModel, str] = {
    BalanceModel.SINGLE_REGION: "SingleRegionBalanceModel",
    BalanceModel.MULTI_REGION: "MultiRegionBalanceModel",
    BalanceModel.NODAL: "NodalBalanceModel",
}

# One formulation triple per technology type: how a plan may build it, how it runs, and how
# its contribution to a feasibility period is counted.
_FEASIBILITY_FORMULATION = "BasicDispatchFeasibility"
_TECHNOLOGY_MODELS: tuple[tuple[str, ModelledTechnology], ...] = tuple(
    (f"PSIP.{model.component}{{PSY.{model.parameter}}}", model) for model in MODELLED_TECHNOLOGIES
)

_POWER_SYSTEMS_INVESTMENTS_PACKAGES = "the PowerSystemsInvestments.jl packages"


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
        self._environment = JuliaEnvironment(
            packages=EXPANSION_PACKAGES,
            dev_checkout_paths={
                "PowerSystemsInvestments": settings.powersystemsinvestments_jl_path,
                "PowerSystemsInvestmentsPortfolios": (
                    settings.powersystemsinvestmentsportfolios_jl_path
                ),
            },
            description=_POWER_SYSTEMS_INVESTMENTS_PACKAGES,
        )

    def is_provisioned(self) -> bool:
        return is_julia_provisioned(self._environment)

    def solve_expansion(
        self,
        portfolio_json_path: Path,
        balance_model: BalanceModel,
        output_dir: Path | None = None,
        *,
        highs: HiGHSOptions,
        investment_treatment: InvestmentTreatment = InvestmentTreatment.CONTINUOUS,
        discount_rate: float | None = None,
    ) -> ExpansionOutcome:
        if not portfolio_json_path.is_file():
            raise UserInputError(f"file not found: {portfolio_json_path}")
        series_path = _build_series_path(portfolio_json_path)
        document = _read_series_document(series_path)
        resolved_output_dir = output_dir or (portfolio_json_path.parent / "expanded")
        resolved_output_dir.mkdir(parents=True, exist_ok=True)
        return _run_expansion(
            self._require_julia(),
            _ExpansionRequest(
                portfolio_json_path=portfolio_json_path,
                document=document,
                output_dir=resolved_output_dir,
                balance_model=balance_model,
                investment_treatment=investment_treatment,
                discount_rate=discount_rate,
                highs_args=build_highs_args(highs, _list_highs_attributes(investment_treatment)),
            ),
        )

    def _require_julia(self) -> Any:
        return require_julia(self._environment)


@dataclass(frozen=True)
class _ExpansionRequest:
    """Everything one run needs, past the Julia session itself."""

    portfolio_json_path: Path
    document: PortfolioSeries
    output_dir: Path
    balance_model: BalanceModel
    investment_treatment: InvestmentTreatment
    discount_rate: float | None
    highs_args: str


def _build_series_path(portfolio_json_path: Path) -> Path:
    """The companion beside the portfolio, named the way the sink wrote it."""
    stem = portfolio_json_path.name
    if stem.endswith(_JSON_SUFFIX):
        stem = stem[: -len(_JSON_SUFFIX)]
    return portfolio_json_path.parent / f"{stem}{SERIES_JSON_SUFFIX}"


def _read_series_document(series_path: Path) -> PortfolioSeries:
    """The companion, parsed before any of it reaches Julia source."""
    if not series_path.is_file():
        raise UserInputError(
            f"the portfolio names no time series of its own, and its companion "
            f"{series_path} is not there. Run the translation that writes both."
        )
    try:
        return PortfolioSeries.model_validate(json.loads(series_path.read_text(encoding="utf-8")))
    except (ValueError, ValidationError) as exc:
        raise UserInputError(
            f"{series_path.as_posix()} does not hold a series document that the expansion can "
            f"read: {_describe_unreadable(exc)}"
        ) from exc


def _describe_unreadable(exc: ValueError) -> str:
    """The first fault of a document that does not parse, and where it is."""
    if not isinstance(exc, ValidationError):
        return str(exc)
    first = exc.errors()[0]
    location = ".".join(str(part) for part in first["loc"])
    return f"{location}: {first['msg']} ({exc.error_count()} fault(s) in all)"


def _list_highs_attributes(investment_treatment: InvestmentTreatment) -> list[HiGHSAttribute]:
    """The attributes past the run's own answers; an integer plan is mixed-integer."""
    if investment_treatment is InvestmentTreatment.INTEGER:
        return [MIP_GAP_ATTRIBUTE]
    return []


def _run_expansion(jl: Any, request: _ExpansionRequest) -> ExpansionOutcome:
    """Build and solve the expansion, re-raising a Julia error as a user error."""
    with reject_julia_errors("Julia expansion error"):
        return _run_expansion_inner(jl, request)


def _run_expansion_inner(jl: Any, request: _ExpansionRequest) -> ExpansionOutcome:
    log.info("=== 1. Loading the portfolio ===")
    jl.seval("""
        using PowerSystems, PowerSystemsInvestmentsPortfolios, PowerSystemsInvestments
        using InfrastructureSystems, HiGHS, Dates, TimeSeries, CSV, DataFrames
        const IS = InfrastructureSystems
        const PSY = PowerSystems
        const PSIP = PowerSystemsInvestmentsPortfolios
        const PSIN = PowerSystemsInvestments
    """)
    portfolio_path = build_julia_path_text(request.portfolio_json_path)
    jl.seval(f'global portfolio = PSIP.Portfolio("{portfolio_path}")')

    log.info("=== 2. Attaching the time series the portfolio cannot carry ===")
    _add_series(jl, request.document)
    _add_existing_devices(jl, request.document)

    log.info("=== 3. Building the investment model template ===")
    _build_template(jl, request)
    models = _set_technology_models(jl, request.investment_treatment)
    log.info("technology models set: %s", ", ".join(models) or "none")
    _warn_unmodelled(jl, models)

    log.info("=== 4. Building the model ===")
    jl.seval(f"""
        global model = PSIN.InvestmentModel(
            template, PSIN.SingleInstanceSolve, portfolio;
            optimizer = PSIN.optimizer_with_attributes(HiGHS.Optimizer, {request.highs_args}),
            portfolio_to_file = false,
            store_variable_names = true,
        )
        PSIN.build!(model; output_dir = "{build_julia_path_text(request.output_dir)}")
    """)

    log.info("=== 5. Solving ===")
    # The default, true, copies the whole JuMP model to a file that nothing reads, which is slow.
    run_status = jl.seval("PSIN.solve!(model; export_optimization_problem = false)")
    objective = jl.seval("""
        global results = PSIN.OptimizationProblemResults(model)
        IS.Optimization.get_objective_value(results)
    """)

    log.info("=== 6. Exporting the decisions ===")
    _write_results(jl, request.output_dir)
    log.info("Results written to %s", request.output_dir)
    return ExpansionOutcome(str(run_status), float(objective))


# Two components of one type can share a name when their PowerSystems types differ.
_DEFINE_GET_ONE_COMPONENT = """
    function get_one_component(portfolio, type_name, component_name)
        technology_type = getproperty(PSIP, Symbol(type_name))
        matches = collect(IS.get_components(
            x -> PSIP.get_name(x) == component_name, technology_type, portfolio.data))
        length(matches) == 1 || error(
            "the portfolio holds $(length(matches)) $(type_name) components named " *
            "$(component_name), so a record that names it has no single owner")
        return only(matches)
    end
"""


def _add_series(jl: Any, document: PortfolioSeries) -> None:
    """Put each record on the component that came off disk, under the features it is read by."""
    jl.seval(_DEFINE_GET_ONE_COMPONENT)
    add_series = jl.seval("""
        function (portfolio, type_name, component_name, series_name, year, rep_day,
                  timestamps, values)
            component = get_one_component(portfolio, type_name, component_name)
            stamps = [DateTime(String(t)) for t in timestamps]
            data = TimeSeries.TimeArray(stamps, [Float64(v) for v in values])
            PSIP.add_time_series!(portfolio, component,
                IS.SingleTimeSeries(String(series_name), data);
                year = String(year), rep_day = Int(rep_day))
            return nothing
        end
    """)
    for record in document.records:
        add_series(
            jl.portfolio,
            record.component_type,
            record.component_name,
            record.series_name,
            record.year,
            record.rep_day,
            [stamp.isoformat() for stamp in record.list_timestamps()],
            record.values,
        )
    log.info("attached %d time series", len(document.records))


def _add_existing_devices(jl: Any, document: PortfolioSeries) -> None:
    """Give each technology the base system components that it already holds."""
    jl.seval(_DEFINE_GET_ONE_COMPONENT)
    add_devices = jl.seval("""
        function (portfolio, type_name, component_name, attribute_id, devices)
            component = get_one_component(portfolio, type_name, component_name)
            PSIP.add_supplemental_attribute!(portfolio, component,
                PSIP.ExistingDevices(; id = Int(attribute_id),
                                     existing_devices = String[String(d) for d in devices]))
            return nothing
        end
    """)
    records = document.existing_devices
    for attribute_id, record in enumerate(records, start=1):
        add_devices(
            jl.portfolio, record.component_type, record.component_name, attribute_id, record.devices
        )
    log.info("attached the existing devices of %d technologies", len(records))


def _build_template(jl: Any, request: _ExpansionRequest) -> None:
    """The periods a plan builds over, the days it is run over, and the network it respects."""
    slices = request.document.list_slices()
    discount_rate = _set_discount_rate(jl, request.discount_rate)
    # Each bound is a parsed date, so its text holds nothing but the date.
    periods = ", ".join(
        f'(Date("{period.start.isoformat()}"), Date("{period.end.isoformat()}"))'
        for period in request.document.periods
    )
    operational_days = ", ".join(
        "[" + ", ".join(f'DateTime("{stamp.isoformat()}")' for stamp in one.timestamps) + "]"
        for one in slices
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


def _set_discount_rate(jl: Any, stated: float | None) -> float:
    """The rate the plan discounts by, put on the portfolio because the model reads it there.

    The model builds its own container from the portfolio rather than from the template, so a
    rate given on the run has to reach the portfolio itself to take effect.
    """
    discount_rate = (
        float(jl.seval("PSIP.get_discount_rate(portfolio)")) if stated is None else stated
    )
    if not (math.isfinite(discount_rate) and discount_rate > 0.0):
        raise UserInputError(
            "the portfolio states a discount rate of "
            f"{discount_rate}, and the capital recovery factor divides by it. "
            "Give a positive rate on the run instead."
        )
    jl.seval(f"PSIP.set_discount_rate!(portfolio, {discount_rate})")
    return discount_rate


def _set_technology_models(jl: Any, investment_treatment: InvestmentTreatment) -> list[str]:
    """One formulation triple per type the portfolio holds, and none for a type it does not."""
    investment = INVESTMENT_FORMULATIONS[investment_treatment]
    set_models: list[str] = []
    for technology_type, model in _TECHNOLOGY_MODELS:
        if not _has_any(jl, technology_type):
            continue
        formulation = model.fixed_investment or investment
        jl.seval(f"""
            PSIN.set_technology_model!(template, portfolio, {technology_type},
                PSIN.{formulation}, PSIN.{model.operations}, PSIN.{_FEASIBILITY_FORMULATION})
        """)
        set_models.append(technology_type)
    return set_models


def _warn_unmodelled(jl: Any, models: list[str]) -> None:
    """Name the technologies of a type that no model covers, which the plan leaves out."""
    names = list(
        jl.seval(f"""
            let modelled = Set{{Type}}([{", ".join(models)}])
                [PSIP.get_name(x) for x in IS.get_components(PSIP.Technology, portfolio.data)
                 if !(typeof(x) in modelled)]
            end
        """)
    )
    if names:
        log.warning(
            "%d technology(ies) are of a type that no PowerSystemsInvestments model covers, "
            "so the plan leaves each out: %s",
            len(names),
            name_a_few(str(name) for name in names),
        )


def _has_any(jl: Any, technology_type: str) -> bool:
    return bool(
        jl.seval(f"length(collect(IS.get_components({technology_type}, portfolio.data))) > 0")
    )


def _write_results(jl: Any, output_dir: Path) -> None:
    """One CSV per decision and per stored expression, and the optimizer's statistics."""
    layout = ExpansionResultsLayout
    jl.seval(f"""
        let
            out = "{build_julia_path_text(output_dir)}"
            for (folder, names, read) in (
                    ("{layout.VARIABLES_DIR}", IS.Optimization.list_variable_names(results),
                     PSIN.read_variable),
                    ("{layout.EXPRESSIONS_DIR}", IS.Optimization.list_expression_names(results),
                     IS.Optimization.read_expression))
                root = joinpath(out, "{layout.WIDE_DIR}", folder)
                mkpath(root)
                for name in names
                    try
                        CSV.write(joinpath(root, string(name, "{layout.CSV_SUFFIX}")),
                                  read(results, name))
                    catch err
                        @warn "result export failed" name=name exception=err
                    end
                end
            end
            mkpath(joinpath(out, "{layout.STATISTICS_DIR}"))
            CSV.write(joinpath(out, "{layout.STATISTICS_DIR}", "{layout.OPTIMIZER_STATS_FILE}"),
                      IS.Optimization.read_optimizer_stats(results))
        end
    """)
