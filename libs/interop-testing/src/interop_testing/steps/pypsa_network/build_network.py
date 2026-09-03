"""The Given steps that grow a PyPSA network before a pipeline runs.

Every step here adds to the ``pypsa_network_builder`` fixture that
``Given a PyPSA network`` creates, then writes the network out on request. The
Then steps that read a written network back live in ``assert_network``.
"""

from __future__ import annotations

import re
from pathlib import Path

from pytest_bdd import given, parsers

from interop_testing.builders.pypsa_networks import PyPSANetworkBuilder


@given("a PyPSA network", target_fixture="pypsa_network_builder")
def given_pypsa_network() -> PyPSANetworkBuilder:
    return PyPSANetworkBuilder()


@given(
    parsers.re(
        r'the network contains bus "(?P<name>[^"]+)" carrier "(?P<carrier>[^"]+)" '
        r"v_nom (?P<v_nom>[\d.]+)(?P<rest>.*)"
    )
)
def given_network_contains_bus(
    pypsa_network_builder: PyPSANetworkBuilder,
    name: str,
    carrier: str,
    v_nom: str,
    rest: str,
) -> None:
    location_m = re.search(r'location "([^"]+)"', rest)
    control_m = re.search(r'control "([^"]+)"', rest)
    v_mag_pu_set_m = re.search(r"v_mag_pu_set ([\d.]+)", rest)
    v_mag_pu_min_m = re.search(r"v_mag_pu_min ([\d.]+)", rest)
    v_mag_pu_max_m = re.search(r"v_mag_pu_max ([\d.]+)", rest)
    pypsa_network_builder.add_bus(
        name=name,
        carrier=carrier,
        v_nom=float(v_nom),
        location=location_m.group(1) if location_m else None,
        control=control_m.group(1) if control_m else None,
        v_mag_pu_set=float(v_mag_pu_set_m.group(1)) if v_mag_pu_set_m else None,
        v_mag_pu_min=float(v_mag_pu_min_m.group(1)) if v_mag_pu_min_m else None,
        v_mag_pu_max=float(v_mag_pu_max_m.group(1)) if v_mag_pu_max_m else None,
    )


@given(parsers.parse("the network has {periods:d} snapshots at {minutes:d} minute intervals"))
def given_network_has_snapshots(
    pypsa_network_builder: PyPSANetworkBuilder,
    periods: int,
    minutes: int,
) -> None:
    pypsa_network_builder.set_snapshots(periods=periods, interval_minutes=minutes)


@given(
    parsers.parse(
        "the network has {periods:d} snapshots starting {start} at {minutes:d} minute intervals"
    )
)
def given_network_has_snapshots_starting(
    pypsa_network_builder: PyPSANetworkBuilder,
    periods: int,
    start: str,
    minutes: int,
) -> None:
    pypsa_network_builder.set_snapshots(periods=periods, interval_minutes=minutes, start=start)


@given(parsers.parse('the network contains load "{name}" on "{bus}" with static p_set {p_set:g}'))
def given_network_contains_load_static(
    pypsa_network_builder: PyPSANetworkBuilder,
    name: str,
    bus: str,
    p_set: float,
) -> None:
    pypsa_network_builder.add_load(name=name, bus=bus, p_set=p_set)


@given(
    parsers.parse(
        'the network contains load "{name}" on "{bus}" with static p_set {p_set:g} '
        'carrier "{carrier}" type "{load_type}"'
    )
)
def given_network_contains_labelled_load(
    pypsa_network_builder: PyPSANetworkBuilder,
    name: str,
    bus: str,
    p_set: float,
    carrier: str,
    load_type: str,
) -> None:
    pypsa_network_builder.add_load(
        name=name, bus=bus, p_set=p_set, carrier=carrier, load_type=load_type
    )


@given(
    parsers.re(
        r'the network contains load "(?P<name>[^"]+)" on "(?P<bus>[^"]+)" '
        r"with p_set (?P<p_set_values>[-\d. ]+)"
    )
)
def given_network_contains_load_ts(
    pypsa_network_builder: PyPSANetworkBuilder,
    name: str,
    bus: str,
    p_set_values: str,
) -> None:
    pypsa_network_builder.add_load(
        name=name, bus=bus, p_set=[float(v) for v in p_set_values.split()]
    )


@given(parsers.parse('the network is saved as "{nc_path}"'))
def given_network_is_saved_as(
    pypsa_network_builder: PyPSANetworkBuilder,
    nc_path: str,
) -> None:
    pypsa_network_builder.save(Path(nc_path))


@given(parsers.parse('the network is saved as classic netCDF "{nc_path}"'))
def given_network_is_saved_as_classic_netcdf(
    pypsa_network_builder: PyPSANetworkBuilder,
    nc_path: str,
) -> None:
    pypsa_network_builder.save_classic_netcdf(Path(nc_path))


@given(
    parsers.re(
        r'the network contains generator "(?P<name>[^"]+)" on "(?P<bus>[^"]+)" '
        r'carrier "(?P<carrier>[^"]+)" p_nom (?P<p_nom>[\d.]+)(?P<rest>.*)'
    )
)
def given_network_contains_generator(
    pypsa_network_builder: PyPSANetworkBuilder,
    name: str,
    bus: str,
    carrier: str,
    p_nom: str,
    rest: str,
) -> None:
    p_min_pu_m = re.search(r"p_min_pu ([\d.]+)", rest)
    p_max_pu_m = re.search(r"p_max_pu ([\d.]+)", rest)
    marginal_cost_m = re.search(r"marginal_cost ([\d.]+)", rest)
    ramp_up_m = re.search(r"ramp_limit_up ([\d.]+)", rest)
    ramp_down_m = re.search(r"ramp_limit_down ([\d.]+)", rest)
    p_max_pu_series_m = re.search(r"p_max_pu_series ([\d. ]+)", rest)
    committable_m = re.search(r"committable (True|False)", rest)
    min_up_time_m = re.search(r"min_up_time ([\d.]+)", rest)
    min_down_time_m = re.search(r"min_down_time ([\d.]+)", rest)
    up_time_before_m = re.search(r"up_time_before ([\d.]+)", rest)
    start_up_cost_m = re.search(r"start_up_cost ([\d.]+)", rest)
    shut_down_cost_m = re.search(r"shut_down_cost ([\d.]+)", rest)
    p_nom_extendable_m = re.search(r"p_nom_extendable (True|False)", rest)
    pypsa_network_builder.add_generator(
        name=name,
        bus=bus,
        carrier=carrier,
        p_nom=float(p_nom),
        p_min_pu=float(p_min_pu_m.group(1)) if p_min_pu_m else 0.0,
        p_max_pu=float(p_max_pu_m.group(1)) if p_max_pu_m else 1.0,
        marginal_cost=float(marginal_cost_m.group(1)) if marginal_cost_m else 0.0,
        ramp_limit_up=float(ramp_up_m.group(1)) if ramp_up_m else None,
        ramp_limit_down=float(ramp_down_m.group(1)) if ramp_down_m else None,
        p_max_pu_series=[float(v) for v in p_max_pu_series_m.group(1).split()]
        if p_max_pu_series_m
        else None,
        committable=committable_m.group(1) == "True" if committable_m else None,
        min_up_time=float(min_up_time_m.group(1)) if min_up_time_m else None,
        min_down_time=float(min_down_time_m.group(1)) if min_down_time_m else None,
        up_time_before=float(up_time_before_m.group(1)) if up_time_before_m else None,
        start_up_cost=float(start_up_cost_m.group(1)) if start_up_cost_m else None,
        shut_down_cost=float(shut_down_cost_m.group(1)) if shut_down_cost_m else None,
        p_nom_extendable=p_nom_extendable_m.group(1) == "True" if p_nom_extendable_m else None,
    )


@given(parsers.parse('the network contains generator "{name}" on "{bus}" carrier "{carrier}"'))
def given_network_contains_generator_minimal(
    pypsa_network_builder: PyPSANetworkBuilder,
    name: str,
    bus: str,
    carrier: str,
) -> None:
    pypsa_network_builder.add_generator(name=name, bus=bus, carrier=carrier)


@given(parsers.parse('generator "{name}" has {attribute} {value:g}'))
def given_generator_has_attribute(
    pypsa_network_builder: PyPSANetworkBuilder,
    name: str,
    attribute: str,
    value: float,
) -> None:
    pypsa_network_builder.set_generator_attribute(name, attribute, value)


@given(
    parsers.re(
        r'the network contains storage unit "(?P<name>[^"]+)" on "(?P<bus>[^"]+)" '
        r'carrier "(?P<carrier>[^"]+)" p_nom (?P<p_nom>[\d.]+)(?P<rest>.*)'
    )
)
def given_network_contains_storage_unit(
    pypsa_network_builder: PyPSANetworkBuilder,
    name: str,
    bus: str,
    carrier: str,
    p_nom: str,
    rest: str,
) -> None:
    p_min_pu_m = re.search(r"p_min_pu (-?[\d.]+)", rest)
    p_max_pu_m = re.search(r"p_max_pu ([\d.]+)", rest)
    marginal_cost_m = re.search(r"marginal_cost ([\d.]+)", rest)
    max_hours_m = re.search(r"max_hours ([\d.]+)", rest)
    eff_store_m = re.search(r"efficiency_store ([\d.]+)", rest)
    eff_dispatch_m = re.search(r"efficiency_dispatch ([\d.]+)", rest)
    soc_initial_m = re.search(r"state_of_charge_initial ([\d.]+)", rest)
    cyclic_m = re.search(r"cyclic_state_of_charge (True|False)", rest)
    inflow_m = re.search(r"inflow ([\d. ]+)", rest)
    p_nom_extendable_m = re.search(r"p_nom_extendable (True|False)", rest)
    pypsa_network_builder.add_storage_unit(
        name=name,
        bus=bus,
        carrier=carrier,
        p_nom=float(p_nom),
        p_min_pu=float(p_min_pu_m.group(1)) if p_min_pu_m else 0.0,
        p_max_pu=float(p_max_pu_m.group(1)) if p_max_pu_m else 1.0,
        marginal_cost=float(marginal_cost_m.group(1)) if marginal_cost_m else 0.0,
        max_hours=float(max_hours_m.group(1)) if max_hours_m else 0.0,
        efficiency_store=float(eff_store_m.group(1)) if eff_store_m else 1.0,
        efficiency_dispatch=float(eff_dispatch_m.group(1)) if eff_dispatch_m else 1.0,
        state_of_charge_initial=float(soc_initial_m.group(1)) if soc_initial_m else 0.0,
        cyclic_state_of_charge=cyclic_m.group(1) == "True" if cyclic_m else None,
        inflow_series=[float(v) for v in inflow_m.group(1).split()] if inflow_m else None,
        p_nom_extendable=p_nom_extendable_m.group(1) == "True" if p_nom_extendable_m else None,
    )


@given(parsers.parse('the network contains storage unit "{name}" on "{bus}" carrier "{carrier}"'))
def given_network_contains_storage_unit_minimal(
    pypsa_network_builder: PyPSANetworkBuilder,
    name: str,
    bus: str,
    carrier: str,
) -> None:
    pypsa_network_builder.add_storage_unit(name=name, bus=bus, carrier=carrier)


@given(parsers.parse('storage unit "{name}" has {attribute} {value:g}'))
def given_storage_unit_has_attribute(
    pypsa_network_builder: PyPSANetworkBuilder,
    name: str,
    attribute: str,
    value: float,
) -> None:
    pypsa_network_builder.set_storage_unit_attribute(name, attribute, value)


@given(
    parsers.re(
        r'the network contains line "(?P<name>[^"]+)" from "(?P<bus0>[^"]+)" '
        r'to "(?P<bus1>[^"]+)"(?P<rest>.*)'
    )
)
def given_network_contains_line(
    pypsa_network_builder: PyPSANetworkBuilder,
    name: str,
    bus0: str,
    bus1: str,
    rest: str,
) -> None:
    resistance_m = re.search(r"resistance ([\d.]+) ohms", rest)
    reactance_m = re.search(r"reactance ([\d.]+) ohms", rest)
    susceptance_m = re.search(r"susceptance ([\d.]+) siemens", rest)
    conductance_m = re.search(r"conductance ([\d.]+) siemens", rest)
    rating_m = re.search(r"rating ([\d.]+) MVA", rest)
    optimised_m = re.search(r"optimised capacity ([\d.]+) MVA", rest)
    length_m = re.search(r"length ([\d.]+) km", rest)
    num_parallel_m = re.search(r"([\d.]+) parallel circuits", rest)
    carrier_m = re.search(r'carrier "([^"]+)"', rest)
    series_m = re.search(r"time-varying rating fraction ([\d. ]+)", rest)
    rating_fraction_m = re.search(r"(?<!time-varying )rating fraction ([\d.]+)", rest)
    is_extendable = re.search(r"\bextendable\b", rest) is not None
    pypsa_network_builder.add_line(
        name=name,
        bus0=bus0,
        bus1=bus1,
        r=float(resistance_m.group(1)) if resistance_m else 0.0,
        x=float(reactance_m.group(1)) if reactance_m else 0.0,
        b=float(susceptance_m.group(1)) if susceptance_m else 0.0,
        g=float(conductance_m.group(1)) if conductance_m else 0.0,
        s_nom=float(rating_m.group(1)) if rating_m else 0.0,
        s_max_pu=float(rating_fraction_m.group(1)) if rating_fraction_m else 1.0,
        s_nom_extendable=True if is_extendable else None,
        s_nom_opt=float(optimised_m.group(1)) if optimised_m else None,
        length=float(length_m.group(1)) if length_m else None,
        num_parallel=float(num_parallel_m.group(1)) if num_parallel_m else None,
        carrier=carrier_m.group(1) if carrier_m else None,
        s_max_pu_series=[float(v) for v in series_m.group(1).split()] if series_m else None,
    )


@given(
    parsers.re(
        r'the network contains link "(?P<name>[^"]+)" from "(?P<bus0>[^"]+)" '
        r'to "(?P<bus1>[^"]+)"(?P<rest>.*)'
    )
)
def given_network_contains_link(
    pypsa_network_builder: PyPSANetworkBuilder,
    name: str,
    bus0: str,
    bus1: str,
    rest: str,
) -> None:
    capacity_m = re.search(r"capacity ([\d.]+) MW", rest)
    optimised_m = re.search(r"optimised capacity ([\d.]+) MW", rest)
    efficiency_m = re.search(r"(?<!time-varying )efficiency ([\d.]+)", rest)
    min_fraction_m = re.search(r"min dispatch fraction (-?[\d.]+)", rest)
    max_fraction_m = re.search(r"max dispatch fraction ([\d.]+)", rest)
    carrier_m = re.search(r'carrier "([^"]+)"', rest)
    multiport_m = re.search(r'multi-port to "([^"]+)"', rest)
    efficiency_series_m = re.search(r"time-varying efficiency ([\d. ]+)", rest)
    is_extendable = re.search(r"\bextendable\b", rest) is not None
    pypsa_network_builder.add_link(
        name=name,
        bus0=bus0,
        bus1=bus1,
        p_nom=float(capacity_m.group(1)) if capacity_m else 0.0,
        p_min_pu=float(min_fraction_m.group(1)) if min_fraction_m else 0.0,
        p_max_pu=float(max_fraction_m.group(1)) if max_fraction_m else 1.0,
        efficiency=float(efficiency_m.group(1)) if efficiency_m else 1.0,
        p_nom_extendable=True if is_extendable else None,
        p_nom_opt=float(optimised_m.group(1)) if optimised_m else None,
        carrier=carrier_m.group(1) if carrier_m else None,
        bus2=multiport_m.group(1) if multiport_m else None,
        efficiency_series=[float(v) for v in efficiency_series_m.group(1).split()]
        if efficiency_series_m
        else None,
    )


@given(parsers.parse('the generator "{name}" dispatches {values}'))
def given_generator_dispatches(
    pypsa_network_builder: PyPSANetworkBuilder,
    name: str,
    values: str,
) -> None:
    pypsa_network_builder.set_generator_dispatch(name, [float(v) for v in values.split()])


@given(parsers.parse('the storage unit "{name}" dispatches {values}'))
def given_storage_unit_dispatches(
    pypsa_network_builder: PyPSANetworkBuilder,
    name: str,
    values: str,
) -> None:
    pypsa_network_builder.set_storage_dispatch(name, [float(v) for v in values.split()])


@given(parsers.parse('the line "{name}" carries flow {values}'))
def given_line_carries_flow(
    pypsa_network_builder: PyPSANetworkBuilder,
    name: str,
    values: str,
) -> None:
    pypsa_network_builder.set_line_flow(name, [float(v) for v in values.split()])


@given(parsers.parse('the link "{name}" carries flow {values}'))
def given_link_carries_flow(
    pypsa_network_builder: PyPSANetworkBuilder,
    name: str,
    values: str,
) -> None:
    pypsa_network_builder.set_link_flow(name, [float(v) for v in values.split()])


@given(parsers.parse('the bus "{name}" has marginal price {values}'))
def given_bus_has_marginal_price(
    pypsa_network_builder: PyPSANetworkBuilder,
    name: str,
    values: str,
) -> None:
    pypsa_network_builder.set_bus_marginal_price(name, [float(v) for v in values.split()])


@given(parsers.parse("the snapshot weightings are {values}"))
def given_snapshot_weightings(
    pypsa_network_builder: PyPSANetworkBuilder,
    values: str,
) -> None:
    pypsa_network_builder.set_snapshot_weightings([float(v) for v in values.split()])


@given(parsers.parse("the network objective is {value:g}"))
def given_network_objective(
    pypsa_network_builder: PyPSANetworkBuilder,
    value: float,
) -> None:
    pypsa_network_builder.set_objective(value)


@given(parsers.parse("the network was written by PyPSA {version}"))
def given_network_pypsa_version(
    pypsa_network_builder: PyPSANetworkBuilder,
    version: str,
) -> None:
    pypsa_network_builder.set_pypsa_version(version)


@given(parsers.re(r'the network contains carrier "(?P<name>[^"]+)"(?P<rest>.*)'))
def given_network_contains_carrier(
    pypsa_network_builder: PyPSANetworkBuilder,
    name: str,
    rest: str,
) -> None:
    co2_emissions_m = re.search(r"co2_emissions ([\d.]+)", rest)
    pypsa_network_builder.add_carrier(
        name=name,
        co2_emissions=float(co2_emissions_m.group(1)) if co2_emissions_m else None,
    )


@given(parsers.parse('line "{name}" has {attribute} {value:g}'))
def given_line_has_attribute(
    pypsa_network_builder: PyPSANetworkBuilder,
    name: str,
    attribute: str,
    value: float,
) -> None:
    pypsa_network_builder.set_line_attribute(name, attribute, value)


@given(parsers.parse('link "{name}" has {attribute} {value:g}'))
def given_link_has_attribute(
    pypsa_network_builder: PyPSANetworkBuilder,
    name: str,
    attribute: str,
    value: float,
) -> None:
    pypsa_network_builder.set_link_attribute(name, attribute, value)


@given(
    parsers.re(
        r'the network contains store "(?P<name>[^"]+)" on "(?P<bus>[^"]+)"'
        r'(?: carrier "(?P<carrier>[^"]+)")?$'
    )
)
def given_network_contains_store(
    pypsa_network_builder: PyPSANetworkBuilder,
    name: str,
    bus: str,
    carrier: str | None,
) -> None:
    """Add a Store, naming a carrier or leaving it at PyPSA's empty-string default.

    A regex rather than a parsed sentence: `{bus}` would match `north" carrier "hydrogen`
    just as happily, so the carrier-less form would swallow the carrier clause and drop it
    silently.
    """
    attributes = {"carrier": carrier} if carrier else {}
    pypsa_network_builder.add_raw_component("Store", name, bus=bus, **attributes)


@given(parsers.parse('the {component} "{name}" is not active'))
def given_component_is_not_active(
    pypsa_network_builder: PyPSANetworkBuilder,
    component: str,
    name: str,
) -> None:
    pypsa_network_builder.deactivate_component(component, name)


@given(parsers.parse('the network contains transformer "{name}" from "{bus0}" to "{bus1}"'))
def given_network_contains_transformer(
    pypsa_network_builder: PyPSANetworkBuilder,
    name: str,
    bus0: str,
    bus1: str,
) -> None:
    pypsa_network_builder.add_raw_component("Transformer", name, bus0=bus0, bus1=bus1)


@given(parsers.parse('the network contains shunt impedance "{name}" on "{bus}"'))
def given_network_contains_shunt_impedance(
    pypsa_network_builder: PyPSANetworkBuilder,
    name: str,
    bus: str,
) -> None:
    pypsa_network_builder.add_raw_component("ShuntImpedance", name, bus=bus)


@given(parsers.parse('{component} "{name}" is duplicated within its class'))
def given_component_is_duplicated(
    pypsa_network_builder: PyPSANetworkBuilder,
    component: str,
    name: str,
) -> None:
    pypsa_network_builder.duplicate_component(component, name)


@given(
    parsers.parse('a PyPSA network with {hours:d} hourly snapshots saved as "{path}"'),
    target_fixture="pypsa_network_path",
)
def given_solvable_pypsa_network(hours: int, path: str) -> str:
    import pandas as pd
    import pypsa

    network = pypsa.Network()
    network.set_snapshots(list(pd.date_range("2026-09-01", periods=hours, freq="h")))
    network.add("Bus", "bus")
    network.add("Generator", "gen", bus="bus", p_nom=100.0, marginal_cost=10.0)
    network.add("Load", "load", bus="bus", p_set=50.0)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    network.export_to_netcdf(str(target))
    return str(target)
