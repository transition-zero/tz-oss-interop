from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, NamedTuple

from pydantic import BaseModel

from interop.ports.errors import UserInputError
from interop.ports.outbound.solver import HiGHSCrossover, HiGHSPresolve, HiGHSSolver, SolverPort
from interop.ports.outbound.unit_commitment import UnitCommitmentTreatment

log = logging.getLogger(__name__)


def _julia_str(path: Path) -> str:
    return str(path).replace("\\", "/").replace('"', '\\"')


# PowerSimulations reads a thermal availability forecast and a fuel price series under these
# names; both are the conventional Sienna names, not ours.
_AVAILABILITY_SERIES = "max_active_power"
_FUEL_COST_SERIES = "fuel_cost"

# The PowerSimulations parameters a DeviceModel binds each of those series to.
_ACTIVE_POWER_PARAMETER = "ActivePowerTimeSeriesParameter"
_FUEL_COST_PARAMETER = "FuelCostParameter"

# The generator types whose formulation depends on whether they carry an availability series.
_THERMAL_STANDARD = "ThermalStandard"
_RENEWABLE_DISPATCH = "RenewableDispatch"
_RENEWABLE_NON_DISPATCH = "RenewableNonDispatch"
_AVAILABILITY_TYPES = (_THERMAL_STANDARD, _RENEWABLE_DISPATCH, _RENEWABLE_NON_DISPATCH)

# PowerSimulations has no relaxed unit commitment formulation, so linearised drops to economic
# dispatch, which has no on/off variable and applies neither the start cost nor the time limits.
_THERMAL_FORMULATIONS = {
    UnitCommitmentTreatment.EXACT: "ThermalStandardUnitCommitment",
    UnitCommitmentTreatment.LINEARISED: "ThermalBasicDispatch",
}

# How far from proven optimality a mixed-integer solve may stop, matching the PyPSA path.
_MILP_REL_GAP = 0.01

_NETWORK_MODEL_MAP: dict[str, str] = {
    "dcp": "DCPPowerModel",
    "ptdf": "PTDFPowerModel",
    "copperplate": "CopperPlatePowerModel",
}


@dataclass(frozen=True)
class _JuliaPackage:
    name: str
    uuid: str
    version: str | None = None


# Versions are pinned to the releases the solve pipeline was developed against;
# unpinned packages are constrained transitively by the pinned ones.
_JULIA_PACKAGES: tuple[_JuliaPackage, ...] = (
    _JuliaPackage("PowerSystems", "bcd98974-b02a-5e2f-9ee0-a103f5c450dd", "~5.9"),
    _JuliaPackage("PowerSimulations", "e690365d-45e2-57bb-ac84-44ba829e73c4", "~0.34"),
    _JuliaPackage("HydroPowerSimulations", "fc1677e0-6ad7-4515-bf3a-bd6bf20a0b1b", "~0.15"),
    _JuliaPackage("StorageSystemsSimulations", "e2f1a126-19d0-4674-9252-42b2384f8e3c", "~0.16"),
    _JuliaPackage("HiGHS", "87dc4568-4c63-4d18-b0c0-bb2238e4078b"),
    _JuliaPackage("TimeSeries", "9e3dc215-6440-5c97-bce1-76c03772f85e"),
    _JuliaPackage("CSV", "336ed68f-0bac-5ca0-87d4-7b16caf5d00b"),
    _JuliaPackage("DataFrames", "a93c6f00-e57d-5684-b7b6-d8193f3e46c0"),
)


class JuliaSolveConfig(BaseModel):
    powersystems_jl_path: Path | None = None
    powersimulations_jl_path: Path | None = None
    hydropowersimulations_jl_path: Path | None = None


class JuliaSolveAdapter(SolverPort):
    """Runs PowerSimulations.jl via juliacall to solve a Sienna JSON model."""

    name: ClassVar[str] = "julia_solver"
    port: ClassVar[type] = SolverPort
    config_schema: ClassVar[type[BaseModel] | None] = JuliaSolveConfig

    def __init__(self, config: JuliaSolveConfig | None = None) -> None:
        c = config or JuliaSolveConfig()
        self._dev_checkout_paths: dict[str, Path | None] = {
            "PowerSystems": c.powersystems_jl_path,
            "PowerSimulations": c.powersimulations_jl_path,
            "HydroPowerSimulations": c.hydropowersimulations_jl_path,
        }

    def is_provisioned(self) -> bool:
        """Report whether Julia and the declared packages are already installed.

        `juliapkg.resolve(dry_run=True)` returns True only when the current
        declarations match the last successful resolution, i.e. nothing would
        be downloaded; it never installs anything itself.
        """
        self._declare_julia_packages()
        import juliapkg  # noqa: PLC0415

        return bool(juliapkg.resolve(dry_run=True))

    def solve(
        self,
        sienna_json_path: Path,
        network_model: str,
        output_dir: Path | None = None,
        *,
        unit_commitment: UnitCommitmentTreatment = UnitCommitmentTreatment.EXACT,
        solver: HiGHSSolver = HiGHSSolver.SIMPLEX,
        presolve: HiGHSPresolve = HiGHSPresolve.CHOOSE,
        run_crossover: HiGHSCrossover = HiGHSCrossover.CHOOSE,
        time_limit_seconds: float | None = None,
    ) -> tuple[str, float]:
        if not sienna_json_path.is_file():
            raise UserInputError(f"file not found: {sienna_json_path}")
        julia_model = _NETWORK_MODEL_MAP.get(network_model)
        if julia_model is None:
            raise UserInputError(
                f"Unknown network model {network_model!r}. "
                f"Valid options: {sorted(_NETWORK_MODEL_MAP)}"
            )

        jl = self._bootstrap_julia()
        resolved_output_dir = output_dir or (sienna_json_path.parent / "solved")
        resolved_output_dir.mkdir(parents=True, exist_ok=True)

        return _run_pipeline(
            jl,
            sienna_json_path,
            julia_model,
            resolved_output_dir,
            unit_commitment=unit_commitment,
            solver=solver,
            presolve=presolve,
            run_crossover=run_crossover,
            time_limit_seconds=time_limit_seconds,
        )

    def _bootstrap_julia(self) -> Any:
        os.environ.setdefault("PYTHON_JULIACALL_HANDLE_SIGNALS", "yes")
        self._declare_julia_packages()

        log.info(
            "Preparing the Julia environment. The first run downloads Julia and the "
            "PowerSimulations.jl packages and compiles them. Later runs start much faster."
        )
        import faulthandler

        faulthandler.disable()
        from juliacall import Main as jl  # noqa: PLC0415

        return jl

    def _declare_julia_packages(self) -> None:
        """Declare the Julia dependencies with juliapkg before juliacall imports.

        juliapkg resolves the declarations on `import juliacall`: it finds a
        compatible Julia (downloading one if none is installed) and installs the
        declared packages into its managed project. Re-declaring an unchanged set
        is free; juliapkg skips resolution when the declarations' hash matches.
        """
        import juliapkg  # noqa: PLC0415

        for package in _JULIA_PACKAGES:
            checkout = self._dev_checkout_paths.get(package.name)
            if checkout is None:
                juliapkg.add(package.name, package.uuid, version=package.version)
            else:
                if not checkout.is_dir():
                    raise UserInputError(
                        f"{package.name} checkout not found at {checkout}. Fix the "
                        "path in adapters.yaml, or remove it to use the registry release."
                    )
                juliapkg.add(package.name, package.uuid, dev=True, path=str(checkout))


class _SeriesCoverage(NamedTuple):
    """What one Sienna type carries of each series a formulation can bind.

    PowerSimulations binds a series for a whole component type or for none of it, so a type
    only part of which carries one binds nothing.
    """

    type_name: str
    total: int
    with_availability: int
    with_fuel_cost: int
    has_reactive_power_limits: bool

    @property
    def binds_availability(self) -> bool:
        return self.total > 0 and self.with_availability == self.total

    @property
    def binds_fuel_cost(self) -> bool:
        return self.total > 0 and self.with_fuel_cost == self.total

    @property
    def is_partly_covered(self) -> bool:
        """Some components carry the availability series and the rest do not."""
        return 0 < self.with_availability < self.total


def _read_series_coverage(jl: Any) -> dict[str, _SeriesCoverage]:
    """Read what the components of each type carry, keyed by type.

    The first component of a type answers for the whole type on reactive power limits.
    """
    pairs = ", ".join(f'("{name}", {name})' for name in _AVAILABILITY_TYPES)
    counted = jl.seval(f"""
        let
            result = []
            for (name, T) in [{pairs}]
                comps = collect(get_components(T, sys))
                availability = 0
                fuel_cost = 0
                for comp in comps
                    if has_time_series(comp, SingleTimeSeries, "{_AVAILABILITY_SERIES}")
                        availability += 1
                    end
                    if has_time_series(comp, SingleTimeSeries, "{_FUEL_COST_SERIES}")
                        fuel_cost += 1
                    end
                end
                reactive = false
                if length(comps) > 0 && hasfield(T, :reactive_power_limits)
                    reactive = get_reactive_power_limits(first(comps)) !== nothing
                end
                push!(result, Dict(
                    "type_name" => name, "total" => length(comps),
                    "availability" => availability, "fuel_cost" => fuel_cost,
                    "reactive" => reactive))
            end
            result
        end
    """)
    coverages = [
        _SeriesCoverage(
            type_name=str(entry["type_name"]),
            total=int(entry["total"]),
            with_availability=int(entry["availability"]),
            with_fuel_cost=int(entry["fuel_cost"]),
            has_reactive_power_limits=bool(entry["reactive"]),
        )
        for entry in counted
    ]
    return {coverage.type_name: coverage for coverage in coverages}


def _thermal_device_model(
    coverage: _SeriesCoverage, unit_commitment: UnitCommitmentTreatment
) -> str:
    """The ThermalStandard DeviceModel, as a Julia expression.

    PowerSimulations names no series for a thermal generator by default, so without
    ``time_series_names`` it reads none, whatever a series is called.
    """
    formulation = _THERMAL_FORMULATIONS[unit_commitment]
    bound = _thermal_series_names(coverage)
    if not bound:
        return f"DeviceModel({_THERMAL_STANDARD}, {formulation})"
    named = ", ".join(f'{parameter} => "{series}"' for parameter, series in bound.items())
    return f"DeviceModel({_THERMAL_STANDARD}, {formulation}; time_series_names = Dict({named}))"


def _thermal_series_names(coverage: _SeriesCoverage) -> dict[str, str]:
    """The series a thermal DeviceModel names, each one only where the whole type carries it."""
    bound: dict[str, str] = {}
    if coverage.binds_availability:
        bound[_ACTIVE_POWER_PARAMETER] = _AVAILABILITY_SERIES
    if coverage.binds_fuel_cost:
        bound[_FUEL_COST_PARAMETER] = _FUEL_COST_SERIES
    return bound


def _renewable_device_model(coverage: _SeriesCoverage) -> str:
    """The DeviceModel for one dispatchable renewable type, as a Julia expression.

    A type that cannot bind an availability series holds its output fixed.
    """
    if not coverage.binds_availability:
        return f"DeviceModel({coverage.type_name}, FixedOutput)"
    formulation = (
        "RenewableFullDispatch"
        if coverage.has_reactive_power_limits
        else "RenewableConstantPowerFactor"
    )
    return f"DeviceModel({coverage.type_name}, {formulation})"


def _build_device_models(jl: Any, unit_commitment: UnitCommitmentTreatment) -> list[str]:
    """Every DeviceModel the ProblemTemplate takes, as Julia expressions."""
    coverage = _read_series_coverage(jl)
    _warn_partly_covered(coverage)
    return [
        _thermal_device_model(coverage[_THERMAL_STANDARD], unit_commitment),
        _renewable_device_model(coverage[_RENEWABLE_DISPATCH]),
        # A non-dispatchable type has no output decision to take, whatever series it carries.
        f"DeviceModel({_RENEWABLE_NON_DISPATCH}, FixedOutput)",
        "DeviceModel(PowerLoad, StaticPowerLoad)",
        # PowerLoadDispatch, not PowerLoadInterruption: the interrupting formulation gives
        # each load one binary per snapshot, so a load is served whole or cut whole, and a
        # small shortfall would cut a whole region. Dispatch cuts the shortfall itself.
        "DeviceModel(InterruptiblePowerLoad, PowerLoadDispatch)",
        "DeviceModel(Line, StaticBranch)",
        "DeviceModel(TwoTerminalGenericHVDCLine, HVDCTwoTerminalLossless)",
        "DeviceModel(HydroDispatch, HydroDispatchRunOfRiverBudget)",
    ]


def _warn_partly_covered(coverage: dict[str, _SeriesCoverage]) -> None:
    """Name each type only some of whose components carry an availability series.

    The ``sienna_to_powersimulations_fill_availability`` step gives every component of a
    type the series once any of them states one, so a system that step wrote never warns.
    """
    for entry in coverage.values():
        if not entry.is_partly_covered:
            continue
        log.warning(
            "solve: %d of %d %s carry a %s series, so the type binds none of them and "
            "each runs at its own limit",
            entry.with_availability,
            entry.total,
            entry.type_name,
            _AVAILABILITY_SERIES,
        )


def _build_highs_args(
    solver: str,
    presolve: str,
    run_crossover: str,
    time_limit_seconds: float | None,
    unit_commitment: UnitCommitmentTreatment,
) -> str:
    attrs: list[tuple[str, str]] = [
        ('"log_to_console"', "true"),
        ('"mip_detect_symmetry"', "false"),
        ('"parallel"', '"off"'),
        ('"solver"', f'"{solver}"'),
        ('"presolve"', f'"{presolve}"'),
        ('"run_crossover"', f'"{run_crossover}"'),
    ]
    if unit_commitment is UnitCommitmentTreatment.EXACT:
        attrs.append(('"mip_rel_gap"', str(_MILP_REL_GAP)))
    if time_limit_seconds is not None:
        attrs.append(('"time_limit"', str(float(time_limit_seconds))))
    return ", ".join(f"{k} => {v}" for k, v in attrs)


def _run_pipeline(
    jl: Any,
    sienna_json_path: Path,
    network_model: str,
    output_dir: Path,
    *,
    unit_commitment: UnitCommitmentTreatment,
    solver: str,
    presolve: str,
    run_crossover: str,
    time_limit_seconds: float | None,
) -> tuple[str, float]:
    """Build and solve the Sienna system in Julia, re-raising Julia errors as user errors."""
    from juliacall import JuliaError  # noqa: PLC0415

    sienna_json_str = _julia_str(sienna_json_path)
    try:
        return _run_pipeline_inner(
            jl,
            sienna_json_str,
            network_model,
            output_dir,
            unit_commitment=unit_commitment,
            solver=solver,
            presolve=presolve,
            run_crossover=run_crossover,
            time_limit_seconds=time_limit_seconds,
        )
    except JuliaError as exc:
        raise UserInputError(f"Julia solver error:\n{exc}") from exc


def _run_pipeline_inner(
    jl: Any,
    sienna_json_str: str,
    network_model: str,
    output_dir: Path,
    *,
    unit_commitment: UnitCommitmentTreatment,
    solver: str,
    presolve: str,
    run_crossover: str,
    time_limit_seconds: float | None,
) -> tuple[str, float]:

    log.info("=== 1. Loading Sienna system from JSON ===")
    jl.seval(f"""
        using PowerSystems, PowerSimulations, HiGHS, Dates, TimeSeries
        using HydroPowerSimulations
        using StorageSystemsSimulations
        global sys = System("{sienna_json_str}")
    """)

    log.info("=== 1b. Registering single-window forecast ===")
    ts_summary = jl.seval("""
        let
            lengths = Set{Int}()
            resolutions = Set{Dates.Period}()
            count = 0
            for ts in get_time_series_multiple(sys; type = SingleTimeSeries)
                count += 1
                push!(lengths, length(ts))
                push!(resolutions, PowerSystems.get_resolution(ts))
            end
            if count == 0
                error("No SingleTimeSeries found on system. Translator must emit forecast data before solve.")
            end
            if length(lengths) != 1 || length(resolutions) != 1
                mismatches = String[]
                for ts in get_time_series_multiple(sys; type = SingleTimeSeries)
                    push!(mismatches, string(PowerSystems.get_name(ts), " (length=", length(ts), ", resolution=", PowerSystems.get_resolution(ts), ")"))
                end
                error("SingleTimeSeries instances are not uniform across the system; cannot derive a single forecast window. Offenders: ", join(mismatches, "; "))
            end
            steps = first(lengths)
            resolution = first(resolutions)
            horizon = steps * resolution
            interval = horizon
            transform_single_time_series!(sys, horizon, interval)
            (steps, string(resolution), string(horizon), string(interval), count)
        end
    """)
    log.info(
        "horizon_steps=%s  resolution=%s  horizon=%s  interval=%s  ts_count=%s",
        int(ts_summary[0]),
        ts_summary[1],
        ts_summary[2],
        ts_summary[3],
        int(ts_summary[4]),
    )

    log.info("=== 2. Building problem template ===")
    models_julia = ", ".join(_build_device_models(jl, unit_commitment))
    jl.seval(f"""
        global template = ProblemTemplate({network_model})
        for model in Any[{models_julia}]
            try
                set_device_model!(template, model)
            catch err
                @warn "Could not set device model" model=model exception=err
            end
        end
    """)

    n_storage = int(jl.seval("length(collect(get_components(EnergyReservoirStorage, sys)))"))
    if n_storage > 0:
        jl.seval("""
            try
                set_device_model!(template, DeviceModel(
                    EnergyReservoirStorage,
                    StorageDispatchWithReserves;
                    attributes=Dict(
                        "reservation" => false,
                        "cycling_limits" => false,
                        "energy_target" => true,
                        "complete_coverage" => false,
                        "regularization" => false,
                    ),
                ))
            catch err
                @warn "Could not set storage device model" exception=err
            end
        """)

    log.info("=== 3. Building DecisionModel ===")
    out_dir_str = _julia_str(output_dir)
    highs_args = _build_highs_args(
        solver, presolve, run_crossover, time_limit_seconds, unit_commitment
    )
    jl.seval(f"""
        global problem = DecisionModel(
            template, sys;
            optimizer = optimizer_with_attributes(
                HiGHS.Optimizer,
                {highs_args}
            ),
            name = "interop_solve",
            optimizer_solve_log_print = true,
        )
        build!(problem; output_dir = "{out_dir_str}")
    """)

    log.info("=== 4. Solving ===")
    # export_optimization_problem defaults to true, which copies the whole solved JuMP model
    # to a MathOptFormat JSON file. That copy is impractically slow on a large system, so do
    # not drop this argument; nothing reads the file it would produce.
    run_status = jl.seval("solve!(problem; export_optimization_problem = false)")
    obj_value = jl.seval("""
        global results = OptimizationProblemResults(problem)
        get_objective_value(results)
    """)

    log.info("=== 5. Exporting results ===")
    wide_dir_str = _julia_str(output_dir / "results_wide")
    jl.seval("""
        let
            try
                export_results(results)
            catch err
                @warn "export_results failed" exception=(err, catch_backtrace())
            end
        end
    """)
    jl.seval(f"""
        using CSV, DataFrames
        let
            wide_root = "{wide_dir_str}"
            readers = (
                ("variables",     list_variable_names(results),     read_variable),
                ("aux_variables", list_aux_variable_names(results), read_aux_variable),
                ("duals",         list_dual_names(results),         read_dual),
                ("parameters",    list_parameter_names(results),    read_parameter),
                ("expressions",   list_expression_names(results),   read_expression),
            )
            for (label, names_, reader) in readers
                mkpath(joinpath(wide_root, label))
                for name in names_
                    try
                        df = reader(results, name; table_format=TableFormat.WIDE)
                        DataFrames.rename!(df, propertynames(df)[1] => :snapshot)
                        CSV.write(joinpath(wide_root, label, string(name, ".csv")), df)
                    catch err
                        @warn "wide export failed" label=label name=name exception=(err, catch_backtrace())
                    end
                end
            end
        end
    """)

    log.info("Results written to %s", output_dir)
    return str(run_status), float(obj_value)
