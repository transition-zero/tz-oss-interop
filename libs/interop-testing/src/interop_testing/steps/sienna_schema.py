"""pytest-bdd vocabulary for the SiennaSchemas 0.2 contract of a written document.

The SDK ``power-openapi-models`` states the contract. Its document classes check the
envelope and leave each component as a plain mapping, so this module also validates every
row with the SDK class of its type. The SDK ignores a key that no class names, so it also
compares each row with the fields of its class.

"The written Sienna system" is ``outputs/system.json`` and "the written Sienna portfolio"
is ``outputs/portfolio.json``, the paths every pipeline writes by default.
"""

from __future__ import annotations

import json
from collections import defaultdict
from functools import cache
from importlib.resources import files
from types import ModuleType
from typing import Any

from power_openapi_models.core import models as core_models
from power_openapi_models.document import PortfolioDocument, SystemDocument
from power_openapi_models.infrastructure_core import models as infrastructure_core_models
from power_openapi_models.investments import models as investments_models
from power_openapi_models.operations import models as operations_models
from power_openapi_models.timeseries import models as timeseries_models
from pydantic import BaseModel, TypeAdapter, ValidationError
from pytest_bdd import parsers, then

from interop_testing.files import read_json

SYSTEM_PATH = "outputs/system.json"
PORTFOLIO_PATH = "outputs/portfolio.json"
SCHEMA_VERSION = "0.2.0"

_SDK_MODULES: tuple[ModuleType, ...] = (
    core_models,
    operations_models,
    investments_models,
    timeseries_models,
    infrastructure_core_models,
)


@cache
def list_component_keys(document_class: type[SystemDocument | PortfolioDocument]) -> list[str]:
    """Every key the SDK schema of ``document_class`` allows under ``components``."""
    schema_path = files("power_openapi_models").joinpath(
        "bundles", SCHEMA_VERSION, f"{document_class.__name__}.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return list(schema["properties"]["components"]["properties"])


def find_sdk_class(type_name: str) -> type[BaseModel] | None:
    """The SDK class named ``type_name``, or None when SiennaSchemas 0.2 has no such type."""
    for module in _SDK_MODULES:
        model: type[BaseModel] | None = getattr(module, type_name, None)
        if model is not None:
            return model
    return None


def list_allowed_keys(model: type[BaseModel]) -> set[str]:
    """Every key a row of ``model`` may state: each field name and each alias."""
    allowed: set[str] = set()
    for name, field in model.model_fields.items():
        allowed.add(name)
        allowed.add(field.alias or name)
    return allowed


def name_row(row: dict[str, Any]) -> str:
    return str(row.get("name", row.get("id")))


def list_type_problems(type_name: str, rows: list[dict[str, Any]]) -> list[str]:
    """What is wrong with the rows of one component type, one line for each problem."""
    model = find_sdk_class(type_name)
    if model is None:
        return [f"{type_name}: SiennaSchemas 0.2 has no such component type"]
    problems: list[str] = []
    allowed = list_allowed_keys(model)
    for row in rows:
        unknown = sorted(set(row) - allowed)
        if unknown:
            problems.append(f"{type_name} {name_row(row)}: unknown keys {', '.join(unknown)}")
    adapter: TypeAdapter[list[BaseModel]] = TypeAdapter(list[model])  # type: ignore[valid-type]
    try:
        adapter.validate_python(rows)
    except ValidationError as error:
        for detail in error.errors():
            index, *path = detail["loc"]
            field = ".".join(str(part) for part in path)
            problems.append(f"{type_name} {name_row(rows[int(index)])}: {field}: {detail['msg']}")
    return problems


def list_component_problems(
    type_name: str,
    rows: list[dict[str, Any]],
    document_class: type[SystemDocument | PortfolioDocument],
) -> list[str]:
    """What is wrong with the rows under one component key of ``document_class``.

    The SDK modules also name enums and shared models, so a key must be a component key of
    the document schema before its rows are checked.
    """
    if type_name not in list_component_keys(document_class):
        return [f"{type_name}: SiennaSchemas 0.2 has no such component type"]
    return list_type_problems(type_name, rows)


def list_envelope_problems(
    document: dict[str, Any], document_class: type[SystemDocument | PortfolioDocument]
) -> list[str]:
    """What is wrong with the document apart from its component rows."""
    problems: list[str] = []
    if document.get("schema_version") != SCHEMA_VERSION:
        problems.append(
            f"envelope: schema_version is {document.get('schema_version')!r}, "
            f"expected {SCHEMA_VERSION!r}"
        )
    components = document.get("components", {})
    if isinstance(components, dict) and list(components) != sorted(components):
        problems.append("envelope: components keys are not sorted")
    try:
        document_class.model_validate(document)
    except ValidationError as error:
        for detail in error.errors():
            path = ".".join(str(part) for part in detail["loc"])
            problems.append(f"envelope: {path}: {detail['msg']}")
    return problems


def list_id_problems(document: dict[str, Any]) -> list[str]:
    """Each component id that more than one component states."""
    owners: dict[Any, list[str]] = defaultdict(list)
    for type_name, rows in document.get("components", {}).items():
        for row in rows:
            owners[row.get("id")].append(f"{type_name} {name_row(row)}")
    return [
        f"component id {component_id} is used by {', '.join(users)}"
        for component_id, users in owners.items()
        if len(users) > 1
    ]


def list_document_problems(
    document: dict[str, Any], document_class: type[SystemDocument | PortfolioDocument]
) -> list[str]:
    problems = list_envelope_problems(document, document_class)
    components = document.get("components", {})
    if not isinstance(components, dict):
        return problems
    for type_name, rows in components.items():
        problems.extend(list_component_problems(type_name, rows, document_class))
    problems.extend(list_id_problems(document))
    return problems


def assert_no_problems(problems: list[str], path: str) -> None:
    assert not problems, f"{path} is not valid SiennaSchemas 0.2:\n" + "\n".join(problems)


@then("the written Sienna system has a valid SiennaSchemas 0.2 envelope")
def assert_system_envelope() -> None:
    document = read_json(SYSTEM_PATH)
    assert_no_problems(list_envelope_problems(document, SystemDocument), SYSTEM_PATH)


@then(
    parsers.parse(
        'every "{sienna_type}" component in the written Sienna system is valid SiennaSchemas 0.2'
    )
)
def assert_system_type(sienna_type: str) -> None:
    rows = read_json(SYSTEM_PATH).get("components", {}).get(sienna_type, [])
    assert rows, f"{SYSTEM_PATH} holds no {sienna_type!r} component"
    assert_no_problems(list_component_problems(sienna_type, rows, SystemDocument), SYSTEM_PATH)


@then("the written Sienna system is a valid SiennaSchemas 0.2 document")
def assert_system_document() -> None:
    assert_no_problems(list_document_problems(read_json(SYSTEM_PATH), SystemDocument), SYSTEM_PATH)


@then("the component ids in the written Sienna system are unique")
def assert_system_ids_unique() -> None:
    assert_no_problems(list_id_problems(read_json(SYSTEM_PATH)), SYSTEM_PATH)


@then("the written Sienna portfolio is a valid SiennaSchemas 0.2 document")
def assert_portfolio_document() -> None:
    assert_no_problems(
        list_document_problems(read_json(PORTFOLIO_PATH), PortfolioDocument), PORTFOLIO_PATH
    )


@then(
    parsers.parse(
        'validating the written Sienna system against SiennaSchemas 0.2 reports "{expected}"'
    )
)
def assert_system_reports(expected: str) -> None:
    problems = list_document_problems(read_json(SYSTEM_PATH), SystemDocument)
    assert any(expected in problem for problem in problems), (
        f"expected a problem containing {expected!r}, got {problems!r}"
    )
