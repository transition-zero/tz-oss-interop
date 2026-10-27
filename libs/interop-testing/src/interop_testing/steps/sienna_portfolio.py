"""pytest-bdd vocabulary for a Sienna investments portfolio a pipeline wrote.

A portfolio groups its components by type name the way a system does, but it also carries a
flat array of supplemental attributes linked to those components by an association table.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import h5py
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
    component_id = find_sienna_component(read_json(path), component_type, component_name)["id"]
    assert_base_system_attribute_field(
        path, attribute_type, component_type, component_id, field_path, value
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


@then(
    parsers.parse(
        'the portfolio "{path}" has a series of "{component_type}" "{name}" for the year'
        ' "{year}" with {length:d} values that peak at {peak:g}'
    )
)
def assert_portfolio_series(
    path: str, component_type: str, name: str, year: str, length: int, peak: float
) -> None:
    """A series of the portfolio, found by its feature `year` in the HDF5 companion it names."""
    values = _read_portfolio_series(path, component_type, name, year)
    assert len(values) == length, f"expected {length} values, got {len(values)}"
    assert math.isclose(max(values), peak, rel_tol=1e-9), f"expected peak {peak}, got {max(values)}"


@then(
    parsers.parse(
        'the portfolio "{path}" has a series of "{component_type}" "{name}" for the year'
        ' "{year}" with {length:d} values from {low:g} to {peak:g}'
    )
)
def assert_portfolio_series_range(
    path: str, component_type: str, name: str, year: str, length: int, low: float, peak: float
) -> None:
    """The lowest and the highest value of a series of the portfolio."""
    values = _read_portfolio_series(path, component_type, name, year)
    assert len(values) == length, f"expected {length} values, got {len(values)}"
    assert math.isclose(min(values), low, rel_tol=1e-9), f"expected low {low}, got {min(values)}"
    assert math.isclose(max(values), peak, rel_tol=1e-9), f"expected peak {peak}, got {max(values)}"


@then(
    parsers.parse(
        'the portfolio "{path}" has a series of "{component_type}" "{name}" for the year'
        ' "{year}" that starts at "{timestamp}"'
    )
)
def assert_portfolio_series_start(
    path: str, component_type: str, name: str, year: str, timestamp: str
) -> None:
    """The first timestamp of a series of the portfolio, as its association states it."""
    association = _find_series_association(read_json(path), component_type, name, year)
    actual = association["initial_timestamp"]
    assert actual == timestamp, f"expected the series to start at {timestamp!r}, got {actual!r}"


def _read_portfolio_series(path: str, component_type: str, name: str, year: str) -> list[float]:
    document = read_json(path)
    association = _find_series_association(document, component_type, name, year)
    storage = Path(path).parent / document["time_series_storage_file"]
    with h5py.File(storage, "r") as hf:
        return list(hf[f"time_series/{association['time_series_uuid']}/data"][:])


def _find_series_association(
    document: dict[str, Any], component_type: str, name: str, year: str
) -> dict[str, Any]:
    owner_id = find_sienna_component(document, component_type, name)["id"]
    matching = [
        association
        for association in document["time_series_associations"]
        if association["owner_type"] == component_type
        and association["owner_id"] == owner_id
        and association["features"].get("year") == year
    ]
    assert len(matching) == 1, f"expected 1 series of {name!r} for {year}, got {matching!r}"
    return matching[0]


@then(
    parsers.parse(
        'the file "{path}" parses as a portfolio where "{component_type}" "{component_name}"'
        ' has no "{attribute_type}"'
    )
)
def assert_portfolio_attribute_absent(
    path: str, component_type: str, component_name: str, attribute_type: str
) -> None:
    document = read_json(path)
    component_id = find_sienna_component(document, component_type, component_name)["id"]
    matching = portfolio_attributes_for(document, attribute_type, component_type, component_id)
    assert not matching, f"expected no {attribute_type} of {component_name!r}, got {matching!r}"


@then(
    parsers.parse(
        'the file "{path}" parses as a portfolio where no device is in two "{attribute_type}" lists'
    )
)
def assert_devices_listed_once(path: str, attribute_type: str) -> None:
    """Each device of the base system belongs to one technology at most."""
    document = read_json(path)
    attribute_ids = {
        row["attribute_id"]
        for row in document["supplemental_attribute_associations"]
        if row["attribute_type"] == attribute_type
    }
    devices = [
        device
        for attribute in document["supplemental_attributes"]
        if attribute["id"] in attribute_ids
        for device in attribute["existing_devices"]
    ]
    assert devices, f"expected some {attribute_type} in {path}"
    repeated = sorted({device for device in devices if devices.count(device) > 1})
    assert not repeated, f"expected each device in one {attribute_type} list, got {repeated!r}"
