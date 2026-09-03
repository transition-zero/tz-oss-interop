"""pytest-bdd vocabulary for Sienna systems, as a pipeline's input and its output.

The Given steps build a system through the ``sienna_system_builder`` fixture that
``Given a Sienna system`` creates. The Then steps read a written system back: the
SiennaSchemas JSON document, its HDF5 time-series companion, and its
``extensions.json`` sidecar.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import h5py
from pytest_bdd import given, parsers, then

from interop_testing.builders.sienna_documents import (
    find_sienna_component,
    sienna_components_of_type,
    sienna_time_series_uuid,
)
from interop_testing.builders.sienna_systems import SiennaSystemBuilder
from interop_testing.files import navigate_json, read_json


@given("a Sienna system", target_fixture="sienna_system_builder")
def given_sienna_system() -> SiennaSystemBuilder:
    return SiennaSystemBuilder()


@given(parsers.parse('the system contains an area "{name}"'))
def given_system_contains_area(sienna_system_builder: SiennaSystemBuilder, name: str) -> None:
    sienna_system_builder.add_area(name)


@given(parsers.parse('the system contains a bus "{name}"'))
def given_system_contains_bus(sienna_system_builder: SiennaSystemBuilder, name: str) -> None:
    sienna_system_builder.add_bus(name)


@given(parsers.parse('the system contains a bus "{name}" in area "{area}"'))
def given_system_contains_bus_in_area(
    sienna_system_builder: SiennaSystemBuilder, name: str, area: str
) -> None:
    sienna_system_builder.add_bus(name, area=area)


@given(
    parsers.parse(
        'the system contains a ThermalStandard "{name}" on bus "{bus}" '
        "with base_power {base_power:g} rating {rating:g} "
        "active_power_min {active_power_min:g} active_power_max {active_power_max:g} "
        'marginal_cost {marginal_cost:g} prime_mover "{prime_mover}" fuel "{fuel}"'
    )
)
def given_system_contains_thermal_standard(
    sienna_system_builder: SiennaSystemBuilder,
    name: str,
    bus: str,
    base_power: float,
    rating: float,
    active_power_min: float,
    active_power_max: float,
    marginal_cost: float,
    prime_mover: str,
    fuel: str,
) -> None:
    sienna_system_builder.add_thermal_standard(
        name,
        bus,
        base_power,
        rating,
        active_power_min,
        active_power_max,
        marginal_cost,
        prime_mover,
        fuel,
    )


@given(
    parsers.parse(
        'the system contains a RenewableDispatch "{name}" on bus "{bus}" '
        "with base_power {base_power:g} rating {rating:g} active_power {active_power:g} "
        'marginal_cost {marginal_cost:g} prime_mover "{prime_mover}"'
    )
)
def given_system_contains_renewable_dispatch(
    sienna_system_builder: SiennaSystemBuilder,
    name: str,
    bus: str,
    base_power: float,
    rating: float,
    active_power: float,
    marginal_cost: float,
    prime_mover: str,
) -> None:
    sienna_system_builder.add_renewable_dispatch(
        name, bus, base_power, rating, active_power, marginal_cost, prime_mover
    )


@given(
    parsers.parse(
        'the system contains a RenewableNonDispatch "{name}" on bus "{bus}" '
        "with base_power {base_power:g} rating {rating:g} active_power {active_power:g} "
        'prime_mover "{prime_mover}"'
    )
)
def given_system_contains_renewable_non_dispatch(
    sienna_system_builder: SiennaSystemBuilder,
    name: str,
    bus: str,
    base_power: float,
    rating: float,
    active_power: float,
    prime_mover: str,
) -> None:
    sienna_system_builder.add_renewable_non_dispatch(
        name, bus, base_power, rating, active_power, prime_mover
    )


@given(
    parsers.parse(
        'the system contains a HydroDispatch "{name}" on bus "{bus}" '
        "with base_power {base_power:g} rating {rating:g} "
        "active_power_min {active_power_min:g} active_power_max {active_power_max:g} "
        "marginal_cost {marginal_cost:g}"
    )
)
def given_system_contains_hydro_dispatch(
    sienna_system_builder: SiennaSystemBuilder,
    name: str,
    bus: str,
    base_power: float,
    rating: float,
    active_power_min: float,
    active_power_max: float,
    marginal_cost: float,
) -> None:
    sienna_system_builder.add_hydro_dispatch(
        name, bus, base_power, rating, active_power_min, active_power_max, marginal_cost
    )


@given(
    parsers.parse(
        'the system contains an EnergyReservoirStorage "{name}" on bus "{bus}" '
        "with base_power {base_power:g} storage_capacity {storage_capacity:g} "
        "initial_level {initial_level:g} rating {rating:g} "
        "input_max {input_max:g} output_max {output_max:g} "
        "efficiency_in {efficiency_in:g} efficiency_out {efficiency_out:g} "
        "discharge_cost {discharge_cost:g}"
    )
)
def given_system_contains_energy_reservoir_storage(
    sienna_system_builder: SiennaSystemBuilder,
    name: str,
    bus: str,
    base_power: float,
    storage_capacity: float,
    initial_level: float,
    rating: float,
    input_max: float,
    output_max: float,
    efficiency_in: float,
    efficiency_out: float,
    discharge_cost: float,
) -> None:
    sienna_system_builder.add_energy_reservoir_storage(
        name,
        bus,
        base_power,
        storage_capacity,
        initial_level,
        rating,
        input_max,
        output_max,
        efficiency_in,
        efficiency_out,
        discharge_cost,
    )


@given(parsers.parse('the RenewableDispatch "{name}" has a max_active_power series {series}'))
def given_renewable_dispatch_max_active_power_series(
    sienna_system_builder: SiennaSystemBuilder, name: str, series: str
) -> None:
    values = [float(v) for v in series.split()]
    sienna_system_builder.add_time_series("RenewableDispatch", name, "max_active_power", values)


@given(parsers.parse('the ThermalStandard "{name}" has a max_active_power series {series}'))
def given_thermal_standard_max_active_power_series(
    sienna_system_builder: SiennaSystemBuilder, name: str, series: str
) -> None:
    values = [float(v) for v in series.split()]
    sienna_system_builder.add_time_series("ThermalStandard", name, "max_active_power", values)


@given(
    parsers.parse(
        'the system contains a Line "{name}" from "{from_bus}" to "{to_bus}" with rating {rating:g}'
    )
)
def given_system_contains_line(
    sienna_system_builder: SiennaSystemBuilder,
    name: str,
    from_bus: str,
    to_bus: str,
    rating: float,
) -> None:
    sienna_system_builder.add_line(name, from_bus, to_bus, rating)


@given(
    parsers.parse(
        'the system contains a Line "{name}" from "{from_bus}" to "{to_bus}" '
        "with rating {rating:g} r {r:g} x {x:g}"
    )
)
def given_system_contains_line_with_impedance(
    sienna_system_builder: SiennaSystemBuilder,
    name: str,
    from_bus: str,
    to_bus: str,
    rating: float,
    r: float,
    x: float,
) -> None:
    sienna_system_builder.add_line(name, from_bus, to_bus, rating, r, x)


@given(
    parsers.parse(
        'the system contains a Line "{name}" from "{from_bus}" to "{to_bus}" '
        "with rating {rating:g} r {r:g} x {x:g} b {b:g} g {g:g}"
    )
)
def given_system_contains_line_with_shunt(
    sienna_system_builder: SiennaSystemBuilder,
    name: str,
    from_bus: str,
    to_bus: str,
    rating: float,
    r: float,
    x: float,
    b: float,
    g: float,
) -> None:
    sienna_system_builder.add_line(name, from_bus, to_bus, rating, r, x, b, g)


@given(
    parsers.parse('the Line "{name}" has ext length {length:g} and num_parallel {num_parallel:g}')
)
def given_line_has_ext(
    sienna_system_builder: SiennaSystemBuilder, name: str, length: float, num_parallel: float
) -> None:
    sienna_system_builder.add_ext("Line", name, {"length": length, "num_parallel": num_parallel})


@given(parsers.parse('the Line "{name}" is unavailable'))
def given_line_unavailable(sienna_system_builder: SiennaSystemBuilder, name: str) -> None:
    sienna_system_builder.set_line_available(name, available=False)


@given(parsers.parse('the Line "{name}" has angle_limits min {min_rad:g} max {max_rad:g}'))
def given_line_angle_limits(
    sienna_system_builder: SiennaSystemBuilder, name: str, min_rad: float, max_rad: float
) -> None:
    sienna_system_builder.set_line_angle_limits(name, min_rad, max_rad)


@given(parsers.parse('the Line "{name}" is extendable in ext'))
def given_line_extendable_in_ext(sienna_system_builder: SiennaSystemBuilder, name: str) -> None:
    sienna_system_builder.add_ext("Line", name, {"s_nom_extendable": True})


@given(parsers.parse('the HVDC line "{name}" is unavailable'))
def given_hvdc_line_unavailable(sienna_system_builder: SiennaSystemBuilder, name: str) -> None:
    sienna_system_builder.set_link_available(name, available=False)


@given(parsers.parse('the HVDC line "{name}" is extendable in ext'))
def given_hvdc_line_extendable_in_ext(
    sienna_system_builder: SiennaSystemBuilder, name: str
) -> None:
    sienna_system_builder.add_ext("TwoTerminalGenericHVDCLine", name, {"p_nom_extendable": True})


@given(parsers.parse('the HVDC line "{name}" has ext p_max_pu {value:g}'))
def given_hvdc_line_ext_p_max_pu(
    sienna_system_builder: SiennaSystemBuilder, name: str, value: float
) -> None:
    sienna_system_builder.add_ext("TwoTerminalGenericHVDCLine", name, {"p_max_pu": value})


@given(parsers.parse('the HVDC line "{name}" has ext p_min_pu {value:g}'))
def given_hvdc_line_ext_p_min_pu(
    sienna_system_builder: SiennaSystemBuilder, name: str, value: float
) -> None:
    sienna_system_builder.add_ext("TwoTerminalGenericHVDCLine", name, {"p_min_pu": value})


@given(
    parsers.parse(
        'the system contains an HVDC line "{name}" from "{from_bus}" to "{to_bus}" '
        "with p_nom {p_nom:g} efficiency {efficiency:g}"
    )
)
def given_system_contains_hvdc_line(
    sienna_system_builder: SiennaSystemBuilder,
    name: str,
    from_bus: str,
    to_bus: str,
    p_nom: float,
    efficiency: float,
) -> None:
    sienna_system_builder.add_link(name, from_bus, to_bus, p_nom, efficiency)


@given(parsers.parse('the PowerLoad "{name}" has a max_active_power series {series}'))
def given_power_load_max_active_power_series(
    sienna_system_builder: SiennaSystemBuilder, name: str, series: str
) -> None:
    values = [float(v) for v in series.split()]
    sienna_system_builder.add_time_series("PowerLoad", name, "max_active_power", values)


@given(parsers.parse('the HydroDispatch "{name}" has a hydro_budget series {series}'))
def given_hydro_dispatch_budget_series(
    sienna_system_builder: SiennaSystemBuilder, name: str, series: str
) -> None:
    values = [float(v) for v in series.split()]
    sienna_system_builder.add_time_series("HydroDispatch", name, "hydro_budget", values)


@given(
    parsers.parse(
        'the system contains a PowerLoad "{name}" on bus "{bus}" '
        "with max_active_power {max_active_power:g}"
    )
)
def given_system_contains_power_load(
    sienna_system_builder: SiennaSystemBuilder, name: str, bus: str, max_active_power: float
) -> None:
    sienna_system_builder.add_power_load(name, bus, max_active_power)


@given(parsers.parse('the {sienna_type} "{name}" has ext carrier "{carrier}"'))
def given_component_has_ext_carrier(
    sienna_system_builder: SiennaSystemBuilder, sienna_type: str, name: str, carrier: str
) -> None:
    sienna_system_builder.add_ext(sienna_type, name, {"carrier": carrier})


@given(parsers.parse('the {sienna_type} "{name}" is committable in ext'))
def given_component_committable_in_ext(
    sienna_system_builder: SiennaSystemBuilder, sienna_type: str, name: str
) -> None:
    sienna_system_builder.add_ext(sienna_type, name, {"committable": True})


@given(parsers.parse('the {sienna_type} "{name}" is p_nom_extendable in ext'))
def given_component_p_nom_extendable_in_ext(
    sienna_system_builder: SiennaSystemBuilder, sienna_type: str, name: str
) -> None:
    sienna_system_builder.add_ext(sienna_type, name, {"p_nom_extendable": True})


@given(parsers.parse('the ThermalStandard "{name}" has ramp_limits up {up:g} down {down:g}'))
def given_thermal_ramp_limits(
    sienna_system_builder: SiennaSystemBuilder, name: str, up: float, down: float
) -> None:
    sienna_system_builder.set_thermal_ramp_limits(name, up, down)


@given(parsers.parse('the ThermalStandard "{name}" has time_limits up {up:g} down {down:g}'))
def given_thermal_time_limits(
    sienna_system_builder: SiennaSystemBuilder, name: str, up: float, down: float
) -> None:
    sienna_system_builder.set_thermal_time_limits(name, up, down)


@given(parsers.parse('the ThermalStandard "{name}" has time_at_status {hours:g}'))
def given_thermal_time_at_status(
    sienna_system_builder: SiennaSystemBuilder, name: str, hours: float
) -> None:
    sienna_system_builder.set_thermal_time_at_status(name, hours)


@given(
    parsers.parse(
        'the ThermalStandard "{name}" has start_up_cost {start_up:g} shut_down_cost {shut_down:g}'
    )
)
def given_thermal_start_stop_costs(
    sienna_system_builder: SiennaSystemBuilder, name: str, start_up: float, shut_down: float
) -> None:
    sienna_system_builder.set_thermal_start_stop_costs(name, start_up, shut_down)


@given(parsers.parse('the system is saved as "{json_path}"'))
def given_system_is_saved_as(sienna_system_builder: SiennaSystemBuilder, json_path: str) -> None:
    sienna_system_builder.save(Path(json_path))


# ---------- Assertions on a written system ----------


@then(
    parsers.re(
        r'the file "(?P<path>[^"]+)" parses as JSON with '
        r'(?P<count>\d+) components? of type "(?P<sienna_type>[^"]+)"'
    )
)
def assert_sienna_component_count(path: str, count: str, sienna_type: str) -> None:
    data = read_json(path)
    actual = sienna_components_of_type(data, sienna_type)
    assert len(actual) == int(count), (
        f"expected {count} components of type {sienna_type!r} in {path}, "
        f"got {len(actual)}: {[c.get('name') for c in actual]}"
    )


@then(
    parsers.parse(
        'the file "{path}" parses as JSON with component "{sienna_type}" named "{name}"'
        ' having "{field_path}" set to {value}'
    )
)
def assert_sienna_component_field(
    path: str, sienna_type: str, name: str, field_path: str, value: str
) -> None:
    expected = json.loads(value)
    data = read_json(path)
    component = find_sienna_component(data, sienna_type, name)
    actual = navigate_json(component, field_path, f"{path}[{sienna_type}:{name}]")
    assert actual == expected, (
        f"expected [{sienna_type}:{name}].{field_path!r} = {expected!r} in {path}, got {actual!r}"
    )


@then(
    parsers.parse(
        'the file "{path}" parses as JSON with component "{sienna_type}" named "{name}"'
        ' without field "{field}"'
    )
)
def assert_sienna_component_field_absent(
    path: str, sienna_type: str, name: str, field: str
) -> None:
    data = read_json(path)
    component = find_sienna_component(data, sienna_type, name)
    assert field not in component, (
        f"expected field {field!r} absent from [{sienna_type}:{name}] in {path}, got {component!r}"
    )


@then(
    parsers.parse(
        'the h5 file "{path}" has a time series for component "{sienna_type}" named "{name}"'
        ' attribute "{attribute}" with length {length:d}'
    )
)
def assert_h5_ts_length(
    path: str, sienna_type: str, name: str, attribute: str, length: int
) -> None:
    uid = sienna_time_series_uuid(sienna_type, name, attribute)
    with h5py.File(path, "r") as hf:
        dataset_path = f"time_series/{uid}/data"
        assert dataset_path in hf, (
            f"expected dataset {dataset_path!r} in {path}, "
            f"got keys: {list(hf.get('time_series', {}).keys())}"
        )
        actual = len(hf[dataset_path])
        assert actual == length, f"expected length {length}, got {actual}"


@then(
    parsers.parse(
        'the h5 file "{path}" has a time series for component "{sienna_type}" named "{name}"'
        ' attribute "{attribute}" with values {values}'
    )
)
def assert_h5_ts_values(
    path: str, sienna_type: str, name: str, attribute: str, values: str
) -> None:
    expected = [float(v) for v in values.split()]
    uid = sienna_time_series_uuid(sienna_type, name, attribute)
    with h5py.File(path, "r") as hf:
        dataset_path = f"time_series/{uid}/data"
        assert dataset_path in hf, (
            f"expected dataset {dataset_path!r} in {path}, "
            f"got keys: {list(hf.get('time_series', {}).keys())}"
        )
        actual = list(hf[dataset_path][:])
    assert len(actual) == len(expected), f"expected {expected}, got {actual}"
    for actual_value, expected_value in zip(actual, expected, strict=True):
        assert math.isclose(actual_value, expected_value, rel_tol=1e-9, abs_tol=1e-9), (
            f"expected values {expected}, got {actual}"
        )


@then(parsers.parse('the Sienna systems "{first}" and "{second}" state the same components'))
def assert_same_components(first: str, second: str) -> None:
    """An ensemble states one set of components, so two replications must not disagree."""
    expected = read_json(first)["components"]
    assert expected, f"expected {first} to state components"
    assert read_json(second)["components"] == expected, (
        f"expected {first} and {second} to state the same components"
    )


@then(
    parsers.parse(
        'the Sienna systems "{first}" and "{second}" state the same time series associations'
    )
)
def assert_same_time_series_associations(first: str, second: str) -> None:
    """One association table serves every companion, so the rows must be identical."""
    key = "time_series_associations"
    expected = read_json(first)[key]
    assert expected, f"expected {first} to state {key}"
    assert read_json(second)[key] == expected, (
        f"expected {first} and {second} to state the same {key}"
    )


def _find_extension_records(path: str, kind: str, name: str) -> list[Any]:
    document: dict[str, Any] = read_json(path)
    return [r for r in document.get(kind, []) if r["name"] == name]


@then(
    parsers.parse(
        'the file "{path}" parses as JSON {kind} extension record for "{name}"'
        ' having "{field}" set to {value}'
    )
)
def assert_extension_record_field(path: str, kind: str, name: str, field: str, value: str) -> None:
    expected = json.loads(value)
    matching = _find_extension_records(path, kind, name)
    assert len(matching) == 1, (
        f"expected 1 {kind} record for {name!r} in {path}, got {len(matching)}"
    )
    record = matching[0]
    assert field in record, f"field {field!r} not in record: {record!r}"
    assert record[field] == expected, f"expected {field}={expected!r}, got {record[field]!r}"


@then(
    parsers.parse('the file "{path}" parses as JSON with no {kind} extension record for "{name}"')
)
def assert_no_extension_record(path: str, kind: str, name: str) -> None:
    matching = _find_extension_records(path, kind, name)
    assert len(matching) == 0, f"expected no {kind} record for {name!r} in {path}, got {matching!r}"


@then(
    parsers.parse(
        'the file "{path}" parses as JSON {kind} extension record for "{name}"'
        ' without field "{field}"'
    )
)
def assert_extension_record_without_field(path: str, kind: str, name: str, field: str) -> None:
    matching = _find_extension_records(path, kind, name)
    assert len(matching) == 1, (
        f"expected 1 {kind} record for {name!r} in {path}, got {len(matching)}"
    )
    record = matching[0]
    assert field not in record, f"expected {field!r} absent from record, got {record!r}"


@then(
    parsers.parse(
        'the file "{path}" parses as JSON where TimeSeriesAssociation for component'
        ' "{owner_type}" owner id {owner_id:d} has resolution "{expected_resolution}"'
    )
)
def assert_ts_association_resolution(
    path: str, owner_type: str, owner_id: int, expected_resolution: str
) -> None:
    actual = _find_ts_association(path, owner_type, owner_id).get("resolution")
    assert actual == expected_resolution, (
        f"expected resolution {expected_resolution!r}, got {actual!r}"
    )


@then(
    parsers.parse(
        'the file "{path}" parses as JSON where TimeSeriesAssociation for component'
        ' "{owner_type}" owner id {owner_id:d} is named "{expected_name}"'
    )
)
def assert_ts_association_name(
    path: str, owner_type: str, owner_id: int, expected_name: str
) -> None:
    actual = _find_ts_association(path, owner_type, owner_id).get("name")
    assert actual == expected_name, f"expected series name {expected_name!r}, got {actual!r}"


def _find_ts_association(path: str, owner_type: str, owner_id: int) -> dict[str, Any]:
    associations: list[dict[str, Any]] = read_json(path).get("time_series_associations", [])
    matching = [
        a
        for a in associations
        if a.get("owner_type") == owner_type and a.get("owner_id") == owner_id
    ]
    assert matching, (
        f"no TimeSeriesAssociation for owner_type={owner_type!r} owner_id={owner_id} in {path}"
    )
    return matching[0]
