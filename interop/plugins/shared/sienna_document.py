"""Read a SiennaSchemas system document, and leave out the rows that do not validate.

The ``power_openapi_models`` SDK states the contract. A file that cannot be read at all
raises. A bad row never stops a translation: the reader leaves it out and warns.
"""

from __future__ import annotations

import json
import logging
from importlib.resources import files
from types import ModuleType
from typing import IO, Any

import power_openapi_models
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
    SiennaArcCol,
    SiennaComponent,
    SiennaGeneratorCol,
    SiennaLineCol,
    SiennaSchemasSystem,
    TimeSeriesAssociationCol,
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
# Each field that staging and the map steps look an id up by, and the type that holds the id.
_REFERENCE_TARGETS: dict[str, str] = {
    SiennaGeneratorCol.BUS: SiennaComponent.AC_BUS,
    SiennaLineCol.ARC: SiennaComponent.ARC,
    SiennaArcCol.FROM: SiennaComponent.AC_BUS,
    SiennaArcCol.TO: SiennaComponent.AC_BUS,
}
_OWNER_TYPE = TimeSeriesAssociationCol.OWNER_TYPE
_OWNER_ID = TimeSeriesAssociationCol.OWNER_ID


def _read_component_types() -> frozenset[str]:
    """Every key that the SystemDocument schema of the SDK allows under ``components``."""
    version = power_openapi_models.__schema_version__.removeprefix("v")
    bundle = files(power_openapi_models).joinpath("bundles", version, "SystemDocument.json")
    schema = json.loads(bundle.read_text(encoding="utf-8"))
    return frozenset(schema["properties"][SiennaSchemasSystem.COMPONENTS]["properties"])


_COMPONENT_TYPES = _read_component_types()


def find_component_model(type_name: str) -> type[BaseModel] | None:
    """The SDK model of the component type ``type_name``, or None when it is no component type.

    An SDK module also holds enums and nested structs, such as ``UnitSystem``, so a name that
    the SDK knows can still be no component type.
    """
    if type_name not in _COMPONENT_TYPES:
        return None
    return find_sdk_model(type_name)


def find_sdk_model(type_name: str) -> type[BaseModel] | None:
    """The SDK model named ``type_name``, or None when the SDK has no model of that name."""
    for module in _SDK_MODULES:
        model = getattr(module, type_name, None)
        if isinstance(model, type) and issubclass(model, BaseModel):
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
        model = find_component_model(type_name)
        if model is None:
            left_out.append(f"{type_name} (type unknown to SiennaSchemas)")
            continue
        kept_components[type_name] = _keep_valid_rows(type_name, model, rows, left_out)
    _drop_rows_that_refer_to_no_kept_row(kept_components, left_out)
    associations = _keep_valid_rows(
        SiennaComponent.TIME_SERIES_ASSOCIATION,
        TimeSeriesAssociation,
        raw[SiennaSchemasSystem.TIME_SERIES_ASSOCIATIONS],
        left_out,
    )
    document = dict(raw)
    document[SiennaSchemasSystem.COMPONENTS] = kept_components
    document[SiennaSchemasSystem.TIME_SERIES_ASSOCIATIONS] = _drop_associations_of_no_kept_owner(
        associations, kept_components, left_out
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
            validated = model.model_validate(row)
        except ValidationError as error:
            field = ".".join(str(part) for part in error.errors()[0]["loc"])
            identity = _name_row(row) if isinstance(row, dict) else row
            left_out.append(f"{type_name} {identity} (field {field or 'row'})")
        else:
            # The validated values, because staging reads them: a raw "1" is no Arc id.
            kept.append(validated.model_dump(mode="json", by_alias=True, exclude_unset=True))
    return kept


def _drop_rows_that_refer_to_no_kept_row(
    components: dict[str, list[dict[str, Any]]], left_out: list[str]
) -> None:
    """Leave out each row whose bus, arc or Arc end names no row that is kept.

    Leaving out a bus can leave an Arc with no end, and then a Line with no Arc, so the pass
    repeats until it leaves out nothing.
    """
    while True:
        kept_ids = {
            target: {row[SiennaACBusCol.ID] for row in components.get(target, [])}
            for target in set(_REFERENCE_TARGETS.values())
        }
        dropped = [
            _drop_rows_of_type(type_name, components, kept_ids, left_out)
            for type_name in components
        ]
        if not any(dropped):
            return


def _drop_rows_of_type(
    type_name: str,
    components: dict[str, list[dict[str, Any]]],
    kept_ids: dict[str, set[Any]],
    left_out: list[str],
) -> bool:
    """Leave out the rows of one type that refer to no kept row, and say if any went."""
    kept: list[dict[str, Any]] = []
    for row in components[type_name]:
        field = _find_reference_to_no_kept_row(row, kept_ids)
        if field is None:
            kept.append(row)
        else:
            left_out.append(
                f"{type_name} {_name_row(row)} (refers to no row that is kept: {field})"
            )
    has_dropped = len(kept) < len(components[type_name])
    components[type_name] = kept
    return has_dropped


def _find_reference_to_no_kept_row(
    row: dict[str, Any], kept_ids: dict[str, set[Any]]
) -> str | None:
    """The first reference field of ``row`` whose id no kept row of its type states, or None."""
    for field, target in _REFERENCE_TARGETS.items():
        value = row.get(field)
        if isinstance(value, int) and value not in kept_ids[target]:
            return field
    return None


def _drop_associations_of_no_kept_owner(
    associations: list[dict[str, Any]],
    components: dict[str, list[dict[str, Any]]],
    left_out: list[str],
) -> list[dict[str, Any]]:
    """Leave out each association whose owner is no row that is kept."""
    owners = {
        (type_name, row[SiennaACBusCol.ID])
        for type_name, rows in components.items()
        for row in rows
    }
    kept: list[dict[str, Any]] = []
    for association in associations:
        owner = (association[_OWNER_TYPE], association[_OWNER_ID])
        if owner in owners:
            kept.append(association)
        else:
            left_out.append(
                f"{SiennaComponent.TIME_SERIES_ASSOCIATION} {_name_row(association)} "
                f"(refers to no row that is kept: {_OWNER_ID})"
            )
    return kept


def _name_row(row: dict[str, Any]) -> Any:
    return row.get(SiennaACBusCol.NAME, row.get(SiennaACBusCol.ID))
