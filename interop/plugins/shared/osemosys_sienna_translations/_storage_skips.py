"""Each reason that the operations system leaves a storage out, as the report states it."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from interop.plugins.shared.osemosys_canonical.constants import (
    OSEMOSYS_FRAMEWORK,
    REGION,
    STORAGE,
    AnnotationColumn,
    FlowParameter,
)
from interop.plugins.shared.osemosys_sienna_constants import (
    OSEMOSYS_TO_SIENNA_PIPELINE,
    StorageParameter,
    SupplyParameter,
)
from interop.plugins.shared.osemosys_sienna_translations._storage_columns import (
    CHARGE_SIDE,
    DISCHARGE_SIDE,
    ENERGY,
    STORAGE_REPORT_NAME,
    STORAGE_SIDES,
)
from interop.plugins.shared.osemosys_sienna_translations._technologies import (
    build_no_carriers_row_note,
)
from interop.plugins.shared.osemosys_sienna_translations._technology_columns import SIENNA_TYPE
from interop.plugins.shared.translation_runner import SkippedNames, SkipReport

_COUNTED_NOUN = "storage(s)"
_LISTED = SkippedNames(column=STORAGE_REPORT_NAME, label="Storages")


def _build_skip(
    reason: str,
    note: str | Callable[[dict[str, Any]], str],
    attribute_col: str | None = None,
    attribute_name: str | None = None,
) -> SkipReport:
    return SkipReport(
        pipeline=OSEMOSYS_TO_SIENNA_PIPELINE,
        framework=OSEMOSYS_FRAMEWORK,
        component=STORAGE,
        name_col=STORAGE_REPORT_NAME,
        reason=reason,
        counted_noun=_COUNTED_NOUN,
        note=note,
        listed=_LISTED,
        attribute_col=attribute_col,
        attribute_name=attribute_name,
    )


def _build_no_link_note(row: dict[str, Any]) -> str:
    missing = [
        f"no technology names the storage in {side.link_parameter}, so nothing {side.direction}s it"
        for side in STORAGE_SIDES
        if not row[side.links]
    ]
    return "; ".join(missing)


NO_LINK_SKIP = _build_skip(
    "lack a technology that charges them or a technology that discharges them",
    _build_no_link_note,
)
SEVERAL_LINKS_SKIP = _build_skip(
    "have more than one technology or mode that charges or discharges them",
    lambda row: (
        f"{row[CHARGE_SIDE.links]} rows of technology_to_storage and {row[DISCHARGE_SIDE.links]} "
        "rows of technology_from_storage name the storage, and a Sienna storage takes its power "
        "from one of each"
    ),
)
SHARED_TECHNOLOGY_SKIP = _build_skip(
    "share a technology that charges or discharges another storage",
    lambda row: (
        f"{row[REGION]}/{row[DISCHARGE_SIDE.technology]} or "
        f"{row[REGION]}/{row[CHARGE_SIDE.technology]} charges or discharges another storage too, "
        "and each Sienna storage would take the whole power of that technology"
    ),
)
NO_ENERGY_SKIP = _build_skip(
    "have no residual storage capacity in the operations year",
    "the energy of the storage in the operations year is its residual_storage_capacity, "
    "which holds none",
    ENERGY,
    StorageParameter.RESIDUAL_STORAGE_CAPACITY,
)
NO_DISCHARGE_POWER_SKIP = _build_skip(
    "have a discharging technology with no residual capacity in the operations year",
    lambda row: (
        f"the residual_capacity of {row[DISCHARGE_SIDE.technology_name]}, which discharges the "
        "storage, holds none, so the storage cannot discharge"
    ),
    DISCHARGE_SIDE.capacity,
    SupplyParameter.RESIDUAL_CAPACITY,
)
NO_CHARGE_POWER_SKIP = _build_skip(
    "have a charging technology with no residual capacity in the operations year",
    lambda row: (
        f"the residual_capacity of {row[CHARGE_SIDE.technology_name]}, which charges the "
        "storage, holds none, so the storage cannot charge"
    ),
    CHARGE_SIDE.capacity,
    SupplyParameter.RESIDUAL_CAPACITY,
)
NO_CARRIERS_ROW_SKIP = _build_skip(
    "have a discharging technology whose category no carriers: row of the user mappings file names",
    lambda row: (
        f"the discharging technology {row[DISCHARGE_SIDE.technology_name]}: "
        f"{build_no_carriers_row_note(row[AnnotationColumn.CATEGORY])}"
    ),
    AnnotationColumn.CATEGORY,
)
NOT_A_STORAGE_SKIP = _build_skip(
    "have a discharging technology whose carriers: row names a type that is not a storage",
    lambda row: (
        f"the carriers: row of the category names {row[SIENNA_TYPE]}, which a storage cannot become"
    ),
    AnnotationColumn.CATEGORY,
)
NO_BUS_SKIP = _build_skip(
    "have a discharging technology that puts out electricity only to fuels with no location",
    "no electricity fuel that the discharging technology puts out has a location, so no bus can "
    "hold the storage",
)
NO_OUTPUT_SKIP = _build_skip(
    "put out no electricity at the discharge mode",
    "the discharging technology puts out no electricity at the mode that discharges the storage",
    DISCHARGE_SIDE.ratio,
    FlowParameter.OUTPUT_ACTIVITY_RATIO,
)
NO_INPUT_SKIP = _build_skip(
    "take in no electricity at the charge mode",
    "the charging technology takes in no electricity at the mode that charges the storage",
    CHARGE_SIDE.ratio,
    FlowParameter.INPUT_ACTIVITY_RATIO,
)
