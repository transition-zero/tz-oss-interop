"""The emission penalty that a line or a conversion record leaves out of its cost.

OSeMOSYS charges `emission_penalty` for each tonne that the operations mode of a technology
emits. The cost of a line, and of a conversion record, is the variable cost of that mode for each
MWh that the technology takes in, with no penalty. So each pollutant that the region charges a
penalty for is recorded as not mapped, and a warning names the technologies.
"""

from __future__ import annotations

from typing import Any

import polars as pl

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import UNIT_DOLLARS_PER_MWH, UNIT_DOLLARS_PER_TONNE
from interop.plugins.shared.osemosys_canonical.constants import (
    OPERATING_MODE,
    OSEMOSYS_FRAMEWORK,
    POLLUTANT,
    REGION,
    TECHNOLOGY,
)
from interop.plugins.shared.osemosys_sienna_constants import (
    NO_COST,
    OSEMOSYS_TO_SIENNA_PIPELINE,
    TECHNOLOGIES_LABEL,
    SupplyParameter,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_emissions import (
    ACTIVITY_RATE_T_PER_MWH,
    PENALTY_PER_TONNE,
    RATE_T_PER_MWH,
    STATED_RATE,
    read_emission_rates,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_penalties import (
    PENALTY_COST_MWH,
    build_penalty_terms,
)
from interop.plugins.shared.osemosys_sienna_translations._operations import OperationsYear
from interop.plugins.shared.osemosys_sienna_translations._technology_columns import TECHNOLOGY_NAME
from interop.plugins.shared.osemosys_sienna_translations._transport_columns import INPUT_RATIO
from interop.plugins.shared.translation_runner import (
    SkippedNames,
    SkipReport,
    report_not_mapped,
)

_MODE_KEYS = [REGION, TECHNOLOGY, OPERATING_MODE]
_REASON = "add to the cost of each MWh that it {verb} in OSeMOSYS"
_IS_FREE = pl.col(PENALTY_COST_MWH) == NO_COST


def _note_penalty(row: dict[str, Any]) -> str:
    return (
        f"the technology emits {row[POLLUTANT]} at the operations mode, and the region charges "
        f"emission_penalty {row[PENALTY_PER_TONNE]:g} {UNIT_DOLLARS_PER_TONNE}, which adds "
        f"{row[PENALTY_COST_MWH]:g} {UNIT_DOLLARS_PER_MWH} to the cost of each MWh that the "
        "technology takes in; the cost of its record leaves it out"
    )


def _build_penalty_report(component: str, verb: str) -> SkipReport:
    return SkipReport(
        pipeline=OSEMOSYS_TO_SIENNA_PIPELINE,
        framework=OSEMOSYS_FRAMEWORK,
        component=SupplyParameter.EMISSION_RATE,
        name_col=TECHNOLOGY_NAME,
        reason=_REASON.format(verb=verb),
        counted_noun=f"emission penalty(ies) of a {component}",
        note=_note_penalty,
        listed=SkippedNames(column=TECHNOLOGY_NAME, label=TECHNOLOGIES_LABEL),
        attribute_col=STATED_RATE,
        attribute_name="the operations mode",
    )


_LINE_PENALTY_REPORT = _build_penalty_report("line", "sends")
_CONVERSION_PENALTY_REPORT = _build_penalty_report("conversion", "takes in")


def report_line_penalties(
    state: State, operations: OperationsYear, lines: pl.DataFrame, recorder: ScopedRecorder
) -> None:
    """Record each pollutant whose penalty the cost of a line leaves out, and warn.

    `lines` holds the keys, the name and the electricity input ratio of each line.
    """
    penalised = _build_penalised_emissions(state, operations, lines)
    report_not_mapped(penalised, _IS_FREE, _LINE_PENALTY_REPORT, recorder)


def report_conversion_penalties(
    state: State, operations: OperationsYear, conversions: pl.DataFrame, recorder: ScopedRecorder
) -> None:
    """Record each pollutant whose penalty the cost of a conversion record leaves out, and warn.

    `conversions` holds the keys, the name and the electricity input ratio of each technology.
    """
    penalised = _build_penalised_emissions(state, operations, conversions)
    report_not_mapped(penalised, _IS_FREE, _CONVERSION_PENALTY_REPORT, recorder)


def _build_penalised_emissions(
    state: State, operations: OperationsYear, members: pl.DataFrame
) -> pl.DataFrame:
    """Each pollutant that a member emits at the operations mode and that its region penalises,
    with the penalty for each MWh that the member takes in."""
    held = members.select(
        REGION,
        TECHNOLOGY,
        TECHNOLOGY_NAME,
        INPUT_RATIO,
        pl.lit(operations.mode).alias(OPERATING_MODE),
    )
    rates = read_emission_rates(state, operations, held).join(held, on=_MODE_KEYS)
    per_input = pl.col(ACTIVITY_RATE_T_PER_MWH) / pl.col(INPUT_RATIO)
    return build_penalty_terms(
        state,
        operations,
        rates.select(
            REGION, TECHNOLOGY_NAME, POLLUTANT, STATED_RATE, per_input.alias(RATE_T_PER_MWH)
        ),
    )
