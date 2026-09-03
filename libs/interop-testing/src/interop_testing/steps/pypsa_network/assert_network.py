"""The Then steps that read a written PyPSA network back off disk.

Each step names a component and an attribute; ``_written_network`` owns the
lookup and the failure message. The Given steps that build the network live in
``build_network``.
"""

from __future__ import annotations

from pytest_bdd import parsers, then

from interop_testing.builders.pypsa_networks import read_network
from interop_testing.steps.pypsa_network._written_network import (
    BUS,
    COMPONENTS,
    GENERATOR,
    LINE,
    LINK,
    LOAD,
    PLURAL_FRAMES,
    STORAGE_UNIT,
    STORE,
    WrittenComponent,
    assert_component_count,
    assert_no_components,
)

_EMPTY = ""


# ---------- Buses ----------


@then(parsers.parse('the PyPSA network "{path}" has {count:d} bus'))
@then(parsers.parse('the PyPSA network "{path}" has {count:d} buses'))
def assert_bus_count(path: str, count: int) -> None:
    assert_component_count(path, BUS, count)


# Spelled out rather than left open, so this cannot also match the steps naming one
# component ("has no generator \"OldPlant\"").
_PLURAL_COMPONENT = "(?P<component>{})".format("|".join(PLURAL_FRAMES))


@then(parsers.re(f'the PyPSA network "(?P<path>[^"]+)" has no {_PLURAL_COMPONENT}$'))
def assert_network_has_no_components(path: str, component: str) -> None:
    """Zero of one component, spelled in the plural: "has no lines"."""
    assert_no_components(path, component)


@then(parsers.parse('the PyPSA network "{path}" has no bus "{name}"'))
def assert_network_has_no_bus(path: str, name: str) -> None:
    WrittenComponent(path, BUS, name).assert_absent()


@then(parsers.parse('the PyPSA network "{path}" bus "{name}" attribute "{attr}" is {value:g}'))
def assert_bus_attribute(path: str, name: str, attr: str, value: float) -> None:
    WrittenComponent(path, BUS, name).assert_close(attr, value)


@then(parsers.parse('the PyPSA network "{path}" bus "{name}" has carrier "{carrier}"'))
def assert_bus_carrier(path: str, name: str, carrier: str) -> None:
    WrittenComponent(path, BUS, name).assert_label("carrier", carrier)


@then(parsers.parse('the PyPSA network "{path}" bus "{name}" has control "{control}"'))
def assert_bus_control(path: str, name: str, control: str) -> None:
    WrittenComponent(path, BUS, name).assert_label("control", control)


@then(parsers.parse('the PyPSA network "{path}" bus "{name}" has location "{location}"'))
def assert_bus_location(path: str, name: str, location: str) -> None:
    WrittenComponent(path, BUS, name).assert_label("location", location)


@then(parsers.parse('the PyPSA network "{path}" bus "{name}" has empty location'))
def assert_bus_location_empty(path: str, name: str) -> None:
    WrittenComponent(path, BUS, name).assert_label("location", _EMPTY)


# ---------- Generators ----------


@then(parsers.parse('the PyPSA network "{path}" has {count:d} generator'))
@then(parsers.parse('the PyPSA network "{path}" has {count:d} generators'))
def assert_generator_count(path: str, count: int) -> None:
    assert_component_count(path, GENERATOR, count)


@then(parsers.parse('the PyPSA network "{path}" has no generator "{name}"'))
def assert_network_has_no_generator(path: str, name: str) -> None:
    WrittenComponent(path, GENERATOR, name).assert_absent()


@then(parsers.parse('the PyPSA network "{path}" generator "{name}" has bus "{bus}"'))
def assert_generator_bus(path: str, name: str, bus: str) -> None:
    WrittenComponent(path, GENERATOR, name).assert_label("bus", bus)


@then(parsers.parse('the PyPSA network "{path}" generator "{name}" has carrier "{carrier}"'))
def assert_generator_carrier(path: str, name: str, carrier: str) -> None:
    WrittenComponent(path, GENERATOR, name).assert_label("carrier", carrier)


@then(
    parsers.parse('the PyPSA network "{path}" generator "{name}" attribute "{attr}" is {value:g}')
)
def assert_generator_attribute(path: str, name: str, attr: str, value: float) -> None:
    WrittenComponent(path, GENERATOR, name).assert_close(attr, value)


@then(parsers.parse('the PyPSA network "{path}" generator "{name}" is committable'))
def assert_generator_committable(path: str, name: str) -> None:
    WrittenComponent(path, GENERATOR, name).assert_flag_set("committable")


@then(parsers.parse('the PyPSA network "{path}" generator "{name}" is not committable'))
def assert_generator_not_committable(path: str, name: str) -> None:
    WrittenComponent(path, GENERATOR, name).assert_flag_clear("committable")


@then(parsers.parse('the PyPSA network "{path}" generator "{name}" is extendable'))
def assert_generator_extendable(path: str, name: str) -> None:
    WrittenComponent(path, GENERATOR, name).assert_flag_set("p_nom_extendable")


@then(parsers.parse('the PyPSA network "{path}" generator "{name}" is not extendable'))
def assert_generator_not_extendable(path: str, name: str) -> None:
    WrittenComponent(path, GENERATOR, name).assert_flag_clear("p_nom_extendable")


@then(parsers.parse('the PyPSA network "{path}" generator "{name}" is not active'))
def assert_generator_not_active(path: str, name: str) -> None:
    WrittenComponent(path, GENERATOR, name).assert_flag_clear("active")


@then(
    parsers.parse(
        'the PyPSA network "{path}" generator "{name}" has a p_max_pu time series {series}'
    )
)
def assert_generator_p_max_pu_series(path: str, name: str, series: str) -> None:
    WrittenComponent(path, GENERATOR, name).assert_series("p_max_pu", series)


@then(
    parsers.parse(
        'the PyPSA network "{path}" generator "{name}" has a marginal_cost time series {series}'
    )
)
def assert_generator_marginal_cost_series(path: str, name: str, series: str) -> None:
    WrittenComponent(path, GENERATOR, name).assert_series("marginal_cost", series)


@then(parsers.parse('the PyPSA network "{path}" generator "{name}" has no p_max_pu time series'))
def assert_generator_has_no_p_max_pu_series(path: str, name: str) -> None:
    WrittenComponent(path, GENERATOR, name).assert_no_series("p_max_pu")


# ---------- Loads ----------


@then(parsers.parse('the PyPSA network "{path}" has {count:d} load'))
@then(parsers.parse('the PyPSA network "{path}" has {count:d} loads'))
def assert_load_count(path: str, count: int) -> None:
    assert_component_count(path, LOAD, count)


@then(parsers.parse('the PyPSA network "{path}" load "{name}" has bus "{bus}"'))
def assert_load_bus(path: str, name: str, bus: str) -> None:
    WrittenComponent(path, LOAD, name).assert_label("bus", bus)


@then(parsers.parse('the PyPSA network "{path}" load "{name}" has carrier "{carrier}"'))
def assert_load_carrier(path: str, name: str, carrier: str) -> None:
    WrittenComponent(path, LOAD, name).assert_label("carrier", carrier)


@then(parsers.parse('the PyPSA network "{path}" load "{name}" has type "{load_type}"'))
def assert_load_type(path: str, name: str, load_type: str) -> None:
    WrittenComponent(path, LOAD, name).assert_label("type", load_type)


@then(parsers.parse('the PyPSA network "{path}" load "{name}" attribute "{attr}" is {value:g}'))
def assert_load_attribute(path: str, name: str, attr: str, value: float) -> None:
    WrittenComponent(path, LOAD, name).assert_close(attr, value)


@then(parsers.parse('the PyPSA network "{path}" load "{name}" has a p_set time series {series}'))
def assert_load_p_set_series(path: str, name: str, series: str) -> None:
    WrittenComponent(path, LOAD, name).assert_series("p_set", series)


# ---------- Lines ----------


@then(parsers.parse('the PyPSA network "{path}" has {count:d} line'))
@then(parsers.parse('the PyPSA network "{path}" has {count:d} lines'))
def assert_line_count(path: str, count: int) -> None:
    assert_component_count(path, LINE, count)


@then(parsers.parse('the PyPSA network "{path}" line "{name}" has bus0 "{bus}"'))
def assert_line_bus0(path: str, name: str, bus: str) -> None:
    WrittenComponent(path, LINE, name).assert_label("bus0", bus)


@then(parsers.parse('the PyPSA network "{path}" line "{name}" has bus1 "{bus}"'))
def assert_line_bus1(path: str, name: str, bus: str) -> None:
    WrittenComponent(path, LINE, name).assert_label("bus1", bus)


@then(parsers.parse('the PyPSA network "{path}" line "{name}" has carrier "{carrier}"'))
def assert_line_carrier(path: str, name: str, carrier: str) -> None:
    WrittenComponent(path, LINE, name).assert_label("carrier", carrier)


@then(parsers.parse('the PyPSA network "{path}" line "{name}" attribute "{attr}" is {value:g}'))
def assert_line_attribute(path: str, name: str, attr: str, value: float) -> None:
    WrittenComponent(path, LINE, name).assert_close(attr, value)


@then(parsers.parse('the PyPSA network "{path}" line "{name}" is not active'))
def assert_line_not_active(path: str, name: str) -> None:
    WrittenComponent(path, LINE, name).assert_flag_clear("active")


@then(parsers.parse('the PyPSA network "{path}" line "{name}" is extendable'))
def assert_line_extendable(path: str, name: str) -> None:
    WrittenComponent(path, LINE, name).assert_flag_set("s_nom_extendable")


# ---------- Links ----------


@then(parsers.parse('the PyPSA network "{path}" has {count:d} link'))
@then(parsers.parse('the PyPSA network "{path}" has {count:d} links'))
def assert_link_count(path: str, count: int) -> None:
    assert_component_count(path, LINK, count)


@then(parsers.parse('the PyPSA network "{path}" link "{name}" has bus0 "{bus}"'))
def assert_link_bus0(path: str, name: str, bus: str) -> None:
    WrittenComponent(path, LINK, name).assert_label("bus0", bus)


@then(parsers.parse('the PyPSA network "{path}" link "{name}" has bus1 "{bus}"'))
def assert_link_bus1(path: str, name: str, bus: str) -> None:
    WrittenComponent(path, LINK, name).assert_label("bus1", bus)


@then(parsers.parse('the PyPSA network "{path}" link "{name}" has carrier "{carrier}"'))
def assert_link_carrier(path: str, name: str, carrier: str) -> None:
    WrittenComponent(path, LINK, name).assert_label("carrier", carrier)


@then(parsers.parse('the PyPSA network "{path}" link "{name}" attribute "{attr}" is {value:g}'))
def assert_link_attribute(path: str, name: str, attr: str, value: float) -> None:
    WrittenComponent(path, LINK, name).assert_close(attr, value)


@then(parsers.parse('the PyPSA network "{path}" link "{name}" is not active'))
def assert_link_not_active(path: str, name: str) -> None:
    WrittenComponent(path, LINK, name).assert_flag_clear("active")


@then(parsers.parse('the PyPSA network "{path}" link "{name}" is extendable'))
def assert_link_extendable(path: str, name: str) -> None:
    WrittenComponent(path, LINK, name).assert_flag_set("p_nom_extendable")


# ---------- Storage units ----------


@then(parsers.parse('the PyPSA network "{path}" has {count:d} storage unit'))
@then(parsers.parse('the PyPSA network "{path}" has {count:d} storage units'))
def assert_storage_unit_count(path: str, count: int) -> None:
    assert_component_count(path, STORAGE_UNIT, count)


@then(parsers.parse('the PyPSA network "{path}" storage unit "{name}" has bus "{bus}"'))
def assert_storage_unit_bus(path: str, name: str, bus: str) -> None:
    WrittenComponent(path, STORAGE_UNIT, name).assert_label("bus", bus)


@then(parsers.parse('the PyPSA network "{path}" storage unit "{name}" has carrier "{carrier}"'))
def assert_storage_unit_carrier(path: str, name: str, carrier: str) -> None:
    WrittenComponent(path, STORAGE_UNIT, name).assert_label("carrier", carrier)


@then(
    parsers.parse(
        'the PyPSA network "{path}" storage unit "{name}" attribute "{attr}" is {value:g}'
    )
)
def assert_storage_unit_attribute(path: str, name: str, attr: str, value: float) -> None:
    WrittenComponent(path, STORAGE_UNIT, name).assert_close(attr, value)


@then(parsers.parse('the PyPSA network "{path}" storage unit "{name}" is extendable'))
def assert_storage_unit_extendable(path: str, name: str) -> None:
    WrittenComponent(path, STORAGE_UNIT, name).assert_flag_set("p_nom_extendable")


@then(parsers.parse('the PyPSA network "{path}" storage unit "{name}" is not extendable'))
def assert_storage_unit_not_extendable(path: str, name: str) -> None:
    WrittenComponent(path, STORAGE_UNIT, name).assert_flag_clear("p_nom_extendable")


@then(parsers.parse('the PyPSA network "{path}" storage unit "{name}" is cyclic'))
def assert_storage_unit_cyclic(path: str, name: str) -> None:
    WrittenComponent(path, STORAGE_UNIT, name).assert_flag_set("cyclic_state_of_charge")


@then(parsers.parse('the PyPSA network "{path}" storage unit "{name}" is not cyclic'))
def assert_storage_unit_not_cyclic(path: str, name: str) -> None:
    WrittenComponent(path, STORAGE_UNIT, name).assert_flag_clear("cyclic_state_of_charge")


@then(
    parsers.parse(
        'the PyPSA network "{path}" storage unit "{name}" has an inflow time series {series}'
    )
)
def assert_storage_unit_inflow_series(path: str, name: str, series: str) -> None:
    WrittenComponent(path, STORAGE_UNIT, name).assert_series("inflow", series)


# ---------- Stores ----------


@then(parsers.parse('the PyPSA network "{path}" store "{name}" has carrier "{carrier}"'))
def assert_store_carrier(path: str, name: str, carrier: str) -> None:
    WrittenComponent(path, STORE, name).assert_label("carrier", carrier)


@then(parsers.parse('the PyPSA network "{path}" store "{name}" has empty carrier'))
def assert_store_carrier_empty(path: str, name: str) -> None:
    WrittenComponent(path, STORE, name).assert_label("carrier", _EMPTY)


# ---------- The network as a whole ----------


@then(parsers.parse('the PyPSA network "{path}" has {count:d} snapshots'))
def assert_network_snapshot_count(path: str, count: int) -> None:
    network = read_network(path)
    assert len(network.snapshots) == count, (
        f"expected {count} snapshots in {path}, found {len(network.snapshots)}"
    )


@then(parsers.parse('the PyPSA network "{path}" is empty'))
def assert_pypsa_network_empty(path: str) -> None:
    network = read_network(path)
    frames = {
        component.plural: getattr(network, component.frame) for component in COMPONENTS.values()
    }
    populated = {plural: list(frame.index) for plural, frame in frames.items() if not frame.empty}
    assert not populated, f"expected an empty network at {path}, got {populated}"
