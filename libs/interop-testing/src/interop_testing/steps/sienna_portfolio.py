"""pytest-bdd vocabulary for a Sienna investments portfolio a pipeline wrote.

A portfolio groups its components by type name the way a system does, but it also carries a
flat array of supplemental attributes linked to those components by an association table.
"""

from __future__ import annotations

import json

from pytest_bdd import parsers, then

from interop_testing.builders.sienna_documents import (
    find_sienna_component,
    portfolio_attributes_for,
    sienna_components_of_type,
)
from interop_testing.files import navigate_json, read_json


@then(
    parsers.parse(
        'the file "{path}" parses as a portfolio with no component "{sienna_type}" named "{name}"'
    )
)
def assert_portfolio_component_absent(path: str, sienna_type: str, name: str) -> None:
    components = sienna_components_of_type(read_json(path), sienna_type)
    matching = [c for c in components if c.get("name") == name]
    assert not matching, (
        f"expected no portfolio component type={sienna_type!r} name={name!r} in {path}, "
        f"got {matching!r}"
    )


@then(
    parsers.parse(
        'the file "{path}" parses as a portfolio where the "{attribute_type}" of'
        ' "{component_type}" "{component_name}" has "{field_path}" set to {value}'
    )
)
def assert_portfolio_attribute_field(
    path: str,
    attribute_type: str,
    component_type: str,
    component_name: str,
    field_path: str,
    value: str,
) -> None:
    expected = json.loads(value)
    attributes = _one_attribute(path, attribute_type, component_type, component_name)
    context = f"{path}[{attribute_type} of {component_type}:{component_name}]"
    actual = navigate_json(attributes, field_path, context)
    assert actual == expected, f"expected {context}.{field_path!r} = {expected!r}, got {actual!r}"


@then(
    parsers.parse(
        'the file "{path}" parses as a portfolio where the "{attribute_type}" of base system'
        ' "{component_type}" {component_id:d} has "{field_path}" set to {value}'
    )
)
def assert_base_system_attribute_field(
    path: str,
    attribute_type: str,
    component_type: str,
    component_id: int,
    field_path: str,
    value: str,
) -> None:
    """An attribute describing a component of the base system, which the portfolio names by id."""
    expected = json.loads(value)
    matching = portfolio_attributes_for(
        read_json(path), attribute_type, component_type, component_id
    )
    context = f"{path}[{attribute_type} of {component_type} {component_id}]"
    assert len(matching) == 1, f"expected 1 {context}, got {len(matching)}: {matching!r}"
    actual = navigate_json(matching[0], field_path, context)
    assert actual == expected, f"expected {context}.{field_path!r} = {expected!r}, got {actual!r}"


def _one_attribute(
    path: str, attribute_type: str, component_type: str, component_name: str
) -> dict[str, object]:
    data = read_json(path)
    component_id = find_sienna_component(data, component_type, component_name)["id"]
    matching = portfolio_attributes_for(data, attribute_type, component_type, component_id)
    assert len(matching) == 1, (
        f"expected 1 {attribute_type} for {component_type} {component_name!r} in {path}, "
        f"got {len(matching)}: {matching!r}"
    )
    return matching[0]
