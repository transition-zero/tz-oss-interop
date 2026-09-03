"""Operation-cost event helpers for the sienna → PowerSimulations.jl step.

Converts Sienna source cost dicts to PS.jl format and emits a translation event
for every field mapping.  Separated from ``map_components`` because the four
cost-type branches account for ~40% of that module's line count.

Only ``PSCostType`` and ``build_operation_cost`` are intended for use outside
this module.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import Framework
from interop.plugins.shared.power_simulations_schema import (
    PowerSimulationsOpCostPath,
    PSHydroGenerationCost,
    PSLoadCost,
    PSOutputType,
    PSRenewableGenerationCost,
    PSStorageCost,
    PSThermalGenerationCost,
)
from interop.plugins.shared.sienna_constants import SiennaStructField
from interop.ports.outbound.reporting import (
    DestinationField,
    EventKind,
    SourceField,
    TranslationEvent,
)


class PSCostType(StrEnum):
    """Discriminator for PowerSystems.jl generation cost types.

    Extends ``SiennaCostType`` with PS.jl-only variants (HYDRO_GEN, STORAGE) that
    have no equivalent in SiennaSchemas but are required to produce valid PS.jl output.
    """

    THERMAL = "THERMAL"
    RENEWABLE = "RENEWABLE"
    HYDRO_GEN = "HYDRO_GEN"
    STORAGE = "STORAGE"
    LOAD = "LOAD"


def _cost_source(sienna_type: str, comp_name: str, field: str, value: Any) -> SourceField:
    return SourceField(Framework.SIENNA, sienna_type, comp_name, field, value)


def _cost_dest(sienna_type: str, comp_name: str, path: str, value: Any) -> DestinationField:
    return DestinationField(Framework.POWER_SIMULATIONS, sienna_type, comp_name, path, value)


def build_operation_cost(
    cost: Any,
    recorder: ScopedRecorder,
    sienna_type: str,
    comp_name: str,
) -> Any:
    """Convert a Sienna source cost dict to a PS.jl cost dict, emitting translation events."""
    if not isinstance(cost, dict):
        return cost

    cost_type = cost.get(SiennaStructField.COST_TYPE)

    match cost_type:
        case PSCostType.THERMAL:
            result = PSThermalGenerationCost.model_validate(cost).model_dump()
            _record_thermal_cost_events(cost, recorder, sienna_type, comp_name)
        case PSCostType.RENEWABLE:
            result = PSRenewableGenerationCost.model_validate(cost).model_dump()
            _record_single_variable_cost_events(
                cost,
                recorder,
                sienna_type,
                comp_name,
                source_cost_type=PSCostType.RENEWABLE,
                dest_output_type=PSOutputType.RENEWABLE_GENERATION_COST,
                derivation="Sienna RENEWABLE -> PS.jl RenewableGenerationCost __metadata__",
            )
        case PSCostType.HYDRO_GEN:
            result = PSHydroGenerationCost.model_validate(cost).model_dump()
            _record_single_variable_cost_events(
                cost,
                recorder,
                sienna_type,
                comp_name,
                source_cost_type=PSCostType.HYDRO_GEN,
                dest_output_type=PSOutputType.HYDRO_GENERATION_COST,
                derivation="Sienna HYDRO_GEN -> PS.jl HydroGenerationCost __metadata__",
            )
        case PSCostType.LOAD:
            result = PSLoadCost.model_validate(cost).model_dump()
            _record_single_variable_cost_events(
                cost,
                recorder,
                sienna_type,
                comp_name,
                source_cost_type=PSCostType.LOAD,
                dest_output_type=PSOutputType.LOAD_COST,
                derivation="Sienna LOAD -> PS.jl LoadCost __metadata__",
            )
        case PSCostType.STORAGE:
            result = PSStorageCost.model_validate(cost).model_dump()
            _record_storage_cost_events(cost, recorder, sienna_type, comp_name)
        case _:
            return cost

    return result


def _record_cost_curve_events(
    curve: dict[str, Any] | None,
    recorder: ScopedRecorder,
    sienna_type: str,
    comp_name: str,
    src_prefix: str,
    dest_meta_path: str,
    dest_proportional_path: str,
    dest_constant_path: str,
    dest_input_at_zero_path: str,
) -> None:
    if not isinstance(curve, dict):
        return
    vc = curve.get(SiennaStructField.VALUE_CURVE)
    if not isinstance(vc, dict):
        return
    fd = vc.get(SiennaStructField.FUNCTION_DATA)
    if not isinstance(fd, dict):
        return

    recorder.append(
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                _cost_source(
                    sienna_type,
                    comp_name,
                    f"{src_prefix}.value_curve.curve_type",
                    vc.get(SiennaStructField.CURVE_TYPE),
                )
            ],
            destinations=[
                _cost_dest(sienna_type, comp_name, dest_meta_path, PSOutputType.INPUT_OUTPUT_CURVE)
            ],
            derivation="Sienna curve_type -> PS.jl InputOutputCurve __metadata__",
        )
    )
    recorder.append(
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                _cost_source(
                    sienna_type,
                    comp_name,
                    f"{src_prefix}.value_curve.function_data.function_type",
                    fd.get(SiennaStructField.FUNCTION_TYPE),
                )
            ],
            destinations=[
                _cost_dest(
                    sienna_type,
                    comp_name,
                    dest_constant_path.replace("constant_term", "__metadata__.type"),
                    PSOutputType.LINEAR_FUNCTION_DATA,
                )
            ],
            derivation="Sienna function_type -> PS.jl LinearFunctionData __metadata__",
        )
    )
    prop = fd.get(SiennaStructField.PROPORTIONAL_TERM, 0.0)
    const = fd.get(SiennaStructField.CONSTANT_TERM, 0.0)
    recorder.append(
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                _cost_source(
                    sienna_type,
                    comp_name,
                    f"{src_prefix}.value_curve.function_data.proportional_term",
                    prop,
                )
            ],
            destinations=[_cost_dest(sienna_type, comp_name, dest_proportional_path, prop)],
            derivation="direct mapping",
        )
    )
    recorder.append(
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                _cost_source(
                    sienna_type,
                    comp_name,
                    f"{src_prefix}.value_curve.function_data.constant_term",
                    const,
                )
            ],
            destinations=[_cost_dest(sienna_type, comp_name, dest_constant_path, const)],
            derivation="direct mapping",
        )
    )
    input_at_zero = vc.get(SiennaStructField.INPUT_AT_ZERO)
    recorder.append(
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                _cost_source(
                    sienna_type, comp_name, f"{src_prefix}.value_curve.input_at_zero", input_at_zero
                )
            ],
            destinations=[
                _cost_dest(sienna_type, comp_name, dest_input_at_zero_path, input_at_zero)
            ],
            derivation="direct mapping",
        )
    )


def _record_thermal_cost_events(
    cost: dict[str, Any],
    recorder: ScopedRecorder,
    sienna_type: str,
    comp_name: str,
) -> None:
    recorder.append(
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                _cost_source(sienna_type, comp_name, "operation_cost.cost_type", PSCostType.THERMAL)
            ],
            destinations=[
                _cost_dest(
                    sienna_type,
                    comp_name,
                    PowerSimulationsOpCostPath.METADATA_TYPE,
                    PSOutputType.THERMAL_GENERATION_COST,
                )
            ],
            derivation="Sienna THERMAL -> PS.jl ThermalGenerationCost __metadata__",
        )
    )
    for field, path in (
        (SiennaStructField.FIXED, PowerSimulationsOpCostPath.FIXED),
        (SiennaStructField.START_UP, PowerSimulationsOpCostPath.START_UP),
        (SiennaStructField.SHUT_DOWN, PowerSimulationsOpCostPath.SHUT_DOWN),
    ):
        v = cost.get(field, 0.0)
        recorder.append(
            TranslationEvent(
                kind=EventKind.VALUE_DERIVED,
                sources=[_cost_source(sienna_type, comp_name, f"operation_cost.{field}", v)],
                destinations=[_cost_dest(sienna_type, comp_name, path, v)],
                derivation="direct mapping",
            )
        )
    variable = cost.get(SiennaStructField.VARIABLE)
    if isinstance(variable, dict):
        recorder.append(
            TranslationEvent(
                kind=EventKind.VALUE_DERIVED,
                sources=[
                    _cost_source(
                        sienna_type,
                        comp_name,
                        "operation_cost.variable.variable_cost_type",
                        variable.get(SiennaStructField.VARIABLE_COST_TYPE),
                    )
                ],
                destinations=[
                    _cost_dest(
                        sienna_type,
                        comp_name,
                        PowerSimulationsOpCostPath.VARIABLE_METADATA_TYPE,
                        PSOutputType.COST_CURVE,
                    )
                ],
                derivation="Sienna variable_cost_type -> PS.jl CostCurve __metadata__",
            )
        )
        _record_cost_curve_events(
            variable,
            recorder,
            sienna_type,
            comp_name,
            src_prefix="operation_cost.variable",
            dest_meta_path=PowerSimulationsOpCostPath.VALUE_CURVE_METADATA_TYPE,
            dest_proportional_path=PowerSimulationsOpCostPath.PROPORTIONAL_TERM,
            dest_constant_path=PowerSimulationsOpCostPath.CONSTANT_TERM,
            dest_input_at_zero_path=PowerSimulationsOpCostPath.INPUT_AT_ZERO,
        )


def _record_single_variable_cost_events(
    cost: dict[str, Any],
    recorder: ScopedRecorder,
    sienna_type: str,
    comp_name: str,
    source_cost_type: str,
    dest_output_type: str,
    derivation: str,
) -> None:
    """Record events for cost types with a single fixed field and one variable cost curve.

    Shared implementation for ``RENEWABLE`` and ``HYDRO_GEN``, which are structurally
    identical and differ only in the cost-type string and PS.jl output type.
    """
    recorder.append(
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                _cost_source(sienna_type, comp_name, "operation_cost.cost_type", source_cost_type)
            ],
            destinations=[
                _cost_dest(
                    sienna_type,
                    comp_name,
                    PowerSimulationsOpCostPath.METADATA_TYPE,
                    dest_output_type,
                )
            ],
            derivation=derivation,
        )
    )
    fixed = cost.get(SiennaStructField.FIXED, 0.0)
    recorder.append(
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                _cost_source(
                    sienna_type, comp_name, f"operation_cost.{SiennaStructField.FIXED}", fixed
                )
            ],
            destinations=[
                _cost_dest(sienna_type, comp_name, PowerSimulationsOpCostPath.FIXED, fixed)
            ],
            derivation="direct mapping",
        )
    )
    variable = cost.get(SiennaStructField.VARIABLE)
    if isinstance(variable, dict):
        recorder.append(
            TranslationEvent(
                kind=EventKind.VALUE_DERIVED,
                sources=[
                    _cost_source(
                        sienna_type,
                        comp_name,
                        "operation_cost.variable.variable_cost_type",
                        variable.get(SiennaStructField.VARIABLE_COST_TYPE),
                    )
                ],
                destinations=[
                    _cost_dest(
                        sienna_type,
                        comp_name,
                        PowerSimulationsOpCostPath.VARIABLE_METADATA_TYPE,
                        PSOutputType.COST_CURVE,
                    )
                ],
                derivation="Sienna variable_cost_type -> PS.jl CostCurve __metadata__",
            )
        )
        _record_cost_curve_events(
            variable,
            recorder,
            sienna_type,
            comp_name,
            src_prefix="operation_cost.variable",
            dest_meta_path=PowerSimulationsOpCostPath.VALUE_CURVE_METADATA_TYPE,
            dest_proportional_path=PowerSimulationsOpCostPath.PROPORTIONAL_TERM,
            dest_constant_path=PowerSimulationsOpCostPath.CONSTANT_TERM,
            dest_input_at_zero_path=PowerSimulationsOpCostPath.INPUT_AT_ZERO,
        )


def _record_storage_cost_events(
    cost: dict[str, Any],
    recorder: ScopedRecorder,
    sienna_type: str,
    comp_name: str,
) -> None:
    recorder.append(
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                _cost_source(sienna_type, comp_name, "operation_cost.cost_type", PSCostType.STORAGE)
            ],
            destinations=[
                _cost_dest(
                    sienna_type,
                    comp_name,
                    PowerSimulationsOpCostPath.METADATA_TYPE,
                    PSOutputType.STORAGE_COST,
                )
            ],
            derivation="Sienna STORAGE -> PS.jl StorageCost __metadata__",
        )
    )
    for field, path in (
        (SiennaStructField.FIXED, PowerSimulationsOpCostPath.FIXED),
        (SiennaStructField.START_UP, PowerSimulationsOpCostPath.START_UP),
        (SiennaStructField.SHUT_DOWN, PowerSimulationsOpCostPath.SHUT_DOWN),
        (SiennaStructField.ENERGY_SHORTAGE_COST, PowerSimulationsOpCostPath.ENERGY_SHORTAGE_COST),
    ):
        v = cost.get(field, 0.0)
        recorder.append(
            TranslationEvent(
                kind=EventKind.VALUE_DERIVED,
                sources=[_cost_source(sienna_type, comp_name, f"operation_cost.{field}", v)],
                destinations=[_cost_dest(sienna_type, comp_name, path, v)],
                derivation="direct mapping",
            )
        )
    discharge = cost.get(SiennaStructField.DISCHARGE_VARIABLE_COST)
    if isinstance(discharge, dict):
        recorder.append(
            TranslationEvent(
                kind=EventKind.VALUE_DERIVED,
                sources=[
                    _cost_source(
                        sienna_type,
                        comp_name,
                        "operation_cost.discharge_variable_cost.variable_cost_type",
                        discharge.get(SiennaStructField.VARIABLE_COST_TYPE),
                    )
                ],
                destinations=[
                    _cost_dest(
                        sienna_type,
                        comp_name,
                        PowerSimulationsOpCostPath.DISCHARGE_METADATA_TYPE,
                        PSOutputType.COST_CURVE,
                    )
                ],
                derivation="Sienna variable_cost_type -> PS.jl CostCurve __metadata__",
            )
        )
    charge = cost.get(SiennaStructField.CHARGE_VARIABLE_COST)
    if isinstance(charge, dict):
        recorder.append(
            TranslationEvent(
                kind=EventKind.VALUE_DERIVED,
                sources=[
                    _cost_source(
                        sienna_type,
                        comp_name,
                        "operation_cost.charge_variable_cost.variable_cost_type",
                        charge.get(SiennaStructField.VARIABLE_COST_TYPE),
                    )
                ],
                destinations=[
                    _cost_dest(
                        sienna_type,
                        comp_name,
                        PowerSimulationsOpCostPath.CHARGE_METADATA_TYPE,
                        PSOutputType.COST_CURVE,
                    )
                ],
                derivation="Sienna variable_cost_type -> PS.jl CostCurve __metadata__",
            )
        )
