"""Read a SiennaSchemas system document, and leave out the rows that do not validate.

The ``power_openapi_models`` SDK states the contract. A file that cannot be read at all
raises. A bad row never stops a translation: the reader leaves it out and warns.
"""

from __future__ import annotations

import json
import logging
from types import ModuleType
from typing import IO, Any

from power_openapi_models import check_schema_version
from power_openapi_models.core import models as core_models
from power_openapi_models.document import SystemDocument
from power_openapi_models.infrastructure_core import models as infrastructure_core_models
from power_openapi_models.investments import models as investments_models
from power_openapi_models.operations import models as operations_models
from power_openapi_models.timeseries import models as timeseries_models
from power_openapi_models.timeseries.models import TimeSeriesAssociation
from pydantic import BaseModel, ValidationError

from interop.plugins.shared.sienna_constants import (
    SiennaACBusCol,
    SiennaComponent,
    SiennaSchemasSystem,
)
from interop.plugins.shared.warning_text import name_a_few
from interop.ports.errors import UserInputError

log = logging.getLogger(__name__)

_SDK_MODULES: tuple[ModuleType, ...] = (
    core_models,
    operations_models,
    investments_models,
    timeseries_models,
    infrastructure_core_models,
)

_READABLE_OUTCOMES = ("current", "upgradable")


def find_sdk_model(type_name: str) -> type[BaseModel] | None:
    """The SDK class named ``type_name``, or None when SiennaSchemas has no such type."""
    for module in _SDK_MODULES:
        model: type[BaseModel] | None = getattr(module, type_name, None)
        if model is not None:
            return model
    return None


def read_system_document(stream: IO[bytes]) -> dict[str, Any]:
    """Parse a system document and keep the rows that the SDK accepts, as raw dicts."""
    raw = json.load(stream)
    if not isinstance(raw, dict):
        raise UserInputError(
            f"The system document root must be an object, got {type(raw).__name__}."
        )
    outcome = check_schema_version(raw)
    if outcome not in _READABLE_OUTCOMES:
        raise UserInputError(
            "Cannot read the system document: schema_version "
            f"{raw.get(SiennaSchemasSystem.SCHEMA_VERSION)!r} is {outcome}."
        )
    _reject_bad_envelope(raw)

    left_out: list[str] = []
    components = raw[SiennaSchemasSystem.COMPONENTS]
    kept_components: dict[str, list[dict[str, Any]]] = {}
    for type_name, rows in components.items():
        model = find_sdk_model(type_name)
        if model is None:
            left_out.append(f"{type_name} (type unknown to SiennaSchemas)")
            continue
        kept_components[type_name] = _keep_valid_rows(type_name, model, rows, left_out)
    document = dict(raw)
    document[SiennaSchemasSystem.COMPONENTS] = kept_components
    document[SiennaSchemasSystem.TIME_SERIES_ASSOCIATIONS] = _keep_valid_rows(
        SiennaComponent.TIME_SERIES_ASSOCIATION,
        TimeSeriesAssociation,
        raw[SiennaSchemasSystem.TIME_SERIES_ASSOCIATIONS],
        left_out,
    )
    if left_out:
        log.warning(
            "%d row(s) of the system document do not follow SiennaSchemas, so each is left out: %s",
            len(left_out),
            name_a_few(left_out),
        )
    return document


def _reject_bad_envelope(raw: dict[str, Any]) -> None:
    structure: dict[str, Any] = {}
    for key, value in raw.items():
        if key == SiennaSchemasSystem.COMPONENTS and isinstance(value, dict):
            structure[key] = {}
        elif isinstance(value, list):
            structure[key] = []
        else:
            structure[key] = value
    try:
        SystemDocument.model_validate(structure)
    except ValidationError as error:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in detail['loc'])}: {detail['msg']}"
            for detail in error.errors()
        )
        raise UserInputError(
            f"The system document does not follow SiennaSchemas: {problems}"
        ) from error


def _keep_valid_rows(
    type_name: str, model: type[BaseModel], rows: Any, left_out: list[str]
) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        left_out.append(f"{type_name} (not a list of rows)")
        return []
    kept: list[dict[str, Any]] = []
    for row in rows:
        try:
            model.model_validate(row)
        except ValidationError as error:
            field = ".".join(str(part) for part in error.errors()[0]["loc"])
            identity = (
                row.get(SiennaACBusCol.NAME, row.get(SiennaACBusCol.ID))
                if isinstance(row, dict)
                else row
            )
            left_out.append(f"{type_name} {identity} (field {field or 'row'})")
        else:
            kept.append(row)
    return kept
