"""pytest-bdd vocabulary for a Sienna investments portfolio a pipeline wrote.

A portfolio groups its components by type name the way a system does, but it also carries a
flat array of supplemental attributes linked to those components by an association table.
The steps here read a written portfolio back: its components, and the attributes describing
each of them.
"""

from __future__ import annotations

import json

from pytest_bdd import parsers, then

from interop_testing.builders.sienna_documents import (
    find_portfolio_attributes,
    find_portfolio_component,
    portfolio_attributes_for,
    portfolio_components_of_type,
)
from interop_testing.files import navigate_json, read_json


@then(
    parsers.re(
        r'the file "(?P<path>[^"]+)" parses as a portfolio with '
        r'(?P<count>\d+) components? of type "(?P<sienna_type>[^"]+)"'
    )
)
def assert_portfolio_component_count(path: str, count: str, sienna_type: str) -> None:
    actual = portfolio_components_of_type(read_json(path), sienna_type)
    assert len(actual) == int(count), (
        f"expected {count} portfolio components of type {sienna_type!r} in {path}, "
        f"got {len(actual)}: {[c.get('name') for c in actual]}"
    )


@then(
    parsers.parse(
        'the file "{path}" parses as a portfolio with component "{sienna_type}" named "{name}"'
        ' having "{field_path}" set to {value}'
    )
)
def assert_portfolio_component_field(
    path: str, sienna_type: str, name: str, field_path: str, value: str
) -> None:
    expected = json.loads(value)
    component = find_portfolio_component(read_json(path), sienna_type, name)
    actual = navigate_json(component, field_path, f"{path}[{sienna_type}:{name}]")
    assert actual == expected, (
        f"expected [{sienna_type}:{name}].{field_path!r} = {expected!r} in {path}, got {actual!r}"
    )


@then(
    parsers.parse(
        'the file "{path}" parses as a portfolio with component "{sienna_type}" named "{name}"'
        ' without field "{field}"'
    )
)
def assert_portfolio_component_field_absent(
    path: str, sienna_type: str, name: str, field: str
) -> None:
    component = find_portfolio_component(read_json(path), sienna_type, name)
    assert field not in component, (
        f"expected field {field!r} absent from [{sienna_type}:{name}] in {path}, got {component!r}"
    )


@then(
    parsers.parse(
        'the file "{path}" parses as a portfolio with no component "{sienna_type}" named "{name}"'
    )
)
def assert_portfolio_component_absent(path: str, sienna_type: str, name: str) -> None:
    components = portfolio_components_of_type(read_json(path), sienna_type)
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
        'the file "{path}" parses as a portfolio with no "{attribute_type}" for'
        ' "{component_type}" "{component_name}"'
    )
)
def assert_portfolio_attribute_absent(
    path: str, attribute_type: str, component_type: str, component_name: str
) -> None:
    matching = find_portfolio_attributes(
        read_json(path), attribute_type, component_type, component_name
    )
    assert not matching, (
        f"expected no {attribute_type} for {component_type} {component_name!r} in {path}, "
        f"got {matching!r}"
    )


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
    matching = find_portfolio_attributes(
        read_json(path), attribute_type, component_type, component_name
    )
    assert len(matching) == 1, (
        f"expected 1 {attribute_type} for {component_type} {component_name!r} in {path}, "
        f"got {len(matching)}: {matching!r}"
    )
    return matching[0]
