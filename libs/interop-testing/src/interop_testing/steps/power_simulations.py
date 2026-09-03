"""pytest-bdd vocabulary for a PowerSimulations.jl system a pipeline emitted.

PS.jl's ``to_json`` envelope is a different document from the SiennaSchemas
system in ``interop_testing.steps.sienna_system``: a flat ``data.components``
list, a ``__metadata__.type`` on each component, and ``{"value": "<uuid>"}``
references between them. Assertions here read that shape.

Nothing builds a PS.jl system as pipeline *input*, so there are no Given steps.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import h5py
from pytest_bdd import parsers, then


def read_power_simulations_system(path: str) -> dict[str, Any]:
    result: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
    return result


def power_simulations_components(system: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = system.get("data", {}).get("components", [])
    return result


def _findpower_simulations_components(
    system: dict[str, Any], sienna_type: str
) -> list[dict[str, Any]]:
    return [
        c
        for c in power_simulations_components(system)
        if isinstance(c, dict) and c.get("__metadata__", {}).get("type") == sienna_type
    ]


def find_power_simulations_component(
    system: dict[str, Any], sienna_type: str, name: str
) -> dict[str, Any]:
    matching = [
        c for c in _findpower_simulations_components(system, sienna_type) if c.get("name") == name
    ]
    assert len(matching) == 1, (
        f"expected 1 component type={sienna_type!r} name={name!r}, got {len(matching)}"
    )
    return matching[0]


def navigate_power_simulations_field(data: Any, key_path: str) -> Any:
    for key in key_path.split("."):
        assert isinstance(data, dict), f"expected dict, got {type(data).__name__} at {key_path}"
        assert key in data, f"missing key {key!r} in {list(data)}"
        data = data[key]
    return data


@then(
    parsers.re(
        r'the PS\.jl system "(?P<path>[^"]+)" contains (?P<count>\d+) '
        r'components? of type "(?P<sienna_type>[^"]+)"'
    )
)
def assert_psi_component_count(path: str, count: str, sienna_type: str) -> None:
    system = read_power_simulations_system(path)
    actual = _findpower_simulations_components(system, sienna_type)
    assert len(actual) == int(count), (
        f"expected {count} components of type {sienna_type!r} in {path}, "
        f"got {len(actual)}: {[c.get('name') for c in actual]}"
    )


@then(
    parsers.parse(
        'the PS.jl system "{path}" component "{sienna_type}" named "{name}" '
        'has "__metadata__.type" equal to "{expected}"'
    )
)
def assert_psi_metadata_type(path: str, sienna_type: str, name: str, expected: str) -> None:
    system = read_power_simulations_system(path)
    component = find_power_simulations_component(system, sienna_type, name)
    actual = component.get("__metadata__", {}).get("type")
    assert actual == expected, (
        f"expected __metadata__.type={expected!r} for {sienna_type}:{name}, got {actual!r}"
    )


@then(
    parsers.parse(
        'the PS.jl system "{path}" component "{sienna_type}" named "{name}" '
        'has field "{field}" equal to {value}'
    )
)
def assert_psi_component_field(
    path: str, sienna_type: str, name: str, field: str, value: str
) -> None:
    expected = json.loads(value)
    system = read_power_simulations_system(path)
    component = find_power_simulations_component(system, sienna_type, name)
    actual = component.get(field)
    assert actual == expected, (
        f"expected {sienna_type}:{name}.{field} = {expected!r}, got {actual!r}"
    )


@then(
    parsers.parse(
        'the PS.jl system "{path}" component "{sienna_type}" named "{name}" '
        'has "{field_path}" equal to "{expected}"'
    )
)
def assert_psi_nested_field_str(
    path: str, sienna_type: str, name: str, field_path: str, expected: str
) -> None:
    system = read_power_simulations_system(path)
    component = find_power_simulations_component(system, sienna_type, name)
    actual = navigate_power_simulations_field(component, field_path)
    assert str(actual) == expected, (
        f"expected {sienna_type}:{name}.{field_path} = {expected!r}, got {actual!r}"
    )


@then(
    parsers.parse(
        'the PS.jl system "{path}" component "{sienna_type}" named "{name}" has a non-empty uuid'
    )
)
def assert_psi_component_has_uuid(path: str, sienna_type: str, name: str) -> None:
    system = read_power_simulations_system(path)
    component = find_power_simulations_component(system, sienna_type, name)
    uuid_val = component.get("internal", {}).get("uuid", {}).get("value")
    assert uuid_val and isinstance(uuid_val, str) and len(uuid_val) > 0, (
        f"expected non-empty internal.uuid.value for {sienna_type}:{name}, got {uuid_val!r}"
    )


@then(
    parsers.parse(
        'the PS.jl system "{path}" component "{sienna_type}" named "{name}" '
        "has bus as a uuid reference"
    )
)
def assert_psi_component_bus_is_ref(path: str, sienna_type: str, name: str) -> None:
    system = read_power_simulations_system(path)
    component = find_power_simulations_component(system, sienna_type, name)
    bus = component.get("bus")
    assert isinstance(bus, dict) and "value" in bus and isinstance(bus["value"], str), (
        f'expected bus to be {{"value": "<uuid>"}} for {sienna_type}:{name}, got {bus!r}'
    )


@then(
    parsers.parse(
        'the PS.jl system "{path}" component "{sienna_type}" named "{name}" '
        "has arc as a uuid reference"
    )
)
def assert_psi_component_arc_is_ref(path: str, sienna_type: str, name: str) -> None:
    system = read_power_simulations_system(path)
    component = find_power_simulations_component(system, sienna_type, name)
    arc = component.get("arc")
    assert isinstance(arc, dict) and "value" in arc and isinstance(arc["value"], str), (
        f'expected arc to be {{"value": "<uuid>"}} for {sienna_type}:{name}, got {arc!r}'
    )


@then(
    parsers.parse(
        'the PS.jl system "{path}" component "{sienna_type}" named "{name}" '
        "has an area uuid reference"
    )
)
def assert_psi_component_area_is_ref(path: str, sienna_type: str, name: str) -> None:
    system = read_power_simulations_system(path)
    component = find_power_simulations_component(system, sienna_type, name)
    area = component.get("area")
    assert isinstance(area, dict) and "value" in area and isinstance(area["value"], str), (
        f'expected area to be {{"value": "<uuid>"}} for {sienna_type}:{name}, got {area!r}'
    )


@then(
    parsers.parse(
        'the PS.jl system "{path}" component "{sienna_type}" named "{name}" has null area'
    )
)
def assert_psi_component_area_is_null(path: str, sienna_type: str, name: str) -> None:
    system = read_power_simulations_system(path)
    component = find_power_simulations_component(system, sienna_type, name)
    area = component.get("area")
    assert area is None, f"expected null area for {sienna_type}:{name}, got {area!r}"


@then(
    parsers.parse(
        'the PS.jl system "{path}" component "{sienna_type}" named "{name}" has no field "{field}"'
    )
)
def assert_psi_component_no_field(path: str, sienna_type: str, name: str, field: str) -> None:
    system = read_power_simulations_system(path)
    component = find_power_simulations_component(system, sienna_type, name)
    present = component.get(field)
    assert field not in component, (
        f"expected no {field!r} field on {sienna_type}:{name}, but it was present: {present!r}"
    )


@then(
    parsers.parse(
        'the PS.jl system "{path}" has exactly 1 "Arc" component'
        " with from and to as uuid references"
    )
)
def assert_arc_has_uuid_refs(path: str) -> None:
    system = read_power_simulations_system(path)
    arcs = _findpower_simulations_components(system, "Arc")
    assert len(arcs) == 1, f"expected exactly 1 Arc component in {path}, got {len(arcs)}"
    arc = arcs[0]
    for field in ("from", "to"):
        val = arc.get(field)
        assert isinstance(val, dict) and "value" in val and isinstance(val["value"], str), (
            f'expected Arc.{field} to be {{"value": "<uuid>"}}, got {val!r}'
        )


# ---------- H5 sidecar assertions ----------


@then(
    parsers.parse(
        'the H5 sidecar "{h5_path}" with system "{json_path}" has a time series association for '
        '"{owner_type}" component "{component_name}"'
    )
)
def assert_h5_has_ts_association(
    h5_path: str, json_path: str, owner_type: str, component_name: str
) -> None:
    import os
    import tempfile

    system = read_power_simulations_system(json_path)
    component = find_power_simulations_component(system, owner_type, component_name)
    expected_uuid = component["internal"]["uuid"]["value"]

    with h5py.File(h5_path, "r") as h5:
        blob = bytes(h5["time_series_metadata"][:].tobytes())

    fd, db_path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    try:
        with open(db_path, "wb") as fh:
            fh.write(blob)
        conn = sqlite3.connect(db_path)
        try:
            cur = conn.execute(
                "SELECT owner_type, owner_uuid FROM time_series_associations "
                "WHERE time_series_type = 'SingleTimeSeries'"
            )
            rows = cur.fetchall()
        finally:
            conn.close()
    finally:
        Path(db_path).unlink(missing_ok=True)

    assert len(rows) > 0, f"no SingleTimeSeries associations in {h5_path}"
    matching = [(ot, uid) for ot, uid in rows if ot == owner_type and uid == expected_uuid]
    assert matching, (
        f"no SingleTimeSeries for owner_type={owner_type!r} uuid={expected_uuid!r} "
        f"({component_name!r}) in {h5_path}; "
        f"found associations: {rows}"
    )
