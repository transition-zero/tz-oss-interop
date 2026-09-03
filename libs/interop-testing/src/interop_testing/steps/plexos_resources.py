"""pytest-bdd Given steps for the resources a PLEXOS model dispatches.

Batteries, storages, turbines, generators, lines, reserves and the objects that price
them. The topology a model hangs those off, and the data files they read, live in
``interop_testing.steps.plexos_model``; both operate on the same ``plexos_model_builder``
fixture that ``Given a Plexos model`` creates.
"""

from __future__ import annotations

from datetime import date

from pytest_bdd import given, parsers

from interop_testing.builders.plexos_generator_specs import (
    build_generator_spec,
    parse_generator_spec,
)
from interop_testing.builders.plexos_models import PlexosModelBuilder
from interop_testing.builders.plexos_tables import DateBand, LineEndpoints

# The generators table's header cell naming the generator itself, not one of its fields.
_NAME_FIELD = "name"


@given(
    parsers.parse(
        'the model contains battery "{name}" on node "{node}" with max_power {max_power:g} '
        "capacity {capacity:g} charge_efficiency {charge_efficiency:g} initial_soc {initial_soc:g}"
    )
)
def given_model_contains_battery(
    plexos_model_builder: PlexosModelBuilder,
    name: str,
    node: str,
    max_power: float,
    capacity: float,
    charge_efficiency: float,
    initial_soc: float,
) -> None:
    plexos_model_builder.add_battery(
        name=name,
        node=node,
        max_power=max_power,
        capacity=capacity,
        charge_efficiency=charge_efficiency,
        initial_soc=initial_soc,
    )


@given(
    parsers.parse(
        'the model contains pumped storage "{name}" on node "{node}" with '
        'max_capacity {max_capacity:g} pump_efficiency {pump_efficiency:g} head "{head}" '
        'tail "{tail}" max_volume {max_volume:g} initial_volume {initial_volume:g}'
    )
)
def given_model_contains_pumped_storage(
    plexos_model_builder: PlexosModelBuilder,
    name: str,
    node: str,
    max_capacity: float,
    pump_efficiency: float,
    head: str,
    tail: str,
    max_volume: float,
    initial_volume: float,
) -> None:
    plexos_model_builder.add_pumped_storage(
        name=name,
        node=node,
        max_capacity=max_capacity,
        pump_efficiency=pump_efficiency,
        head=head,
        tail=tail,
        max_volume=max_volume,
        initial_volume=initial_volume,
    )


@given(parsers.parse('generator "{name}" has property "{property_name}" {value:g}'))
def given_generator_has_property(
    plexos_model_builder: PlexosModelBuilder, name: str, property_name: str, value: float
) -> None:
    plexos_model_builder.add_generator_property(name, property_name, value)


@given(parsers.parse('battery "{name}" has property "{property_name}" {value:g}'))
def given_battery_has_property(
    plexos_model_builder: PlexosModelBuilder, name: str, property_name: str, value: float
) -> None:
    plexos_model_builder.add_battery_property(name, property_name, value)


@given(parsers.parse('storage "{name}" has property "{property_name}" {value:g}'))
def given_storage_has_property(
    plexos_model_builder: PlexosModelBuilder, name: str, property_name: str, value: float
) -> None:
    plexos_model_builder.add_storage_property(name, property_name, value)


@given(parsers.parse('the model contains battery "{name}" on node "{node}"'))
def given_model_contains_bare_battery(
    plexos_model_builder: PlexosModelBuilder, name: str, node: str
) -> None:
    plexos_model_builder.add_bare_battery(name, node)


@given(parsers.parse('the model contains battery "{name}" on no node'))
def given_model_contains_nodeless_battery(
    plexos_model_builder: PlexosModelBuilder, name: str
) -> None:
    plexos_model_builder.add_bare_battery(name)


@given(
    parsers.parse(
        'the model contains turbine "{name}" on node "{node}" with '
        'max_capacity {max_capacity:g} head "{head}"'
    )
)
def given_model_contains_bare_turbine(
    plexos_model_builder: PlexosModelBuilder,
    name: str,
    node: str,
    max_capacity: float,
    head: str,
) -> None:
    plexos_model_builder.add_bare_turbine(name, node, head, max_capacity)


@given(parsers.parse('the model contains turbine "{name}" on node "{node}" with head "{head}"'))
def given_model_contains_turbine_without_capacity(
    plexos_model_builder: PlexosModelBuilder, name: str, node: str, head: str
) -> None:
    plexos_model_builder.add_bare_turbine(name, node, head)


@given(
    parsers.parse(
        'the model contains turbine "{name}" on node "{node}" with '
        'max_capacity {max_capacity:g} head "{head}" tail "{tail}"'
    )
)
def given_model_contains_bare_pumped_storage(
    plexos_model_builder: PlexosModelBuilder,
    name: str,
    node: str,
    max_capacity: float,
    head: str,
    tail: str,
) -> None:
    plexos_model_builder.add_bare_pumped_storage(name, node, max_capacity, head, tail)


@given(
    parsers.parse(
        'the model contains turbine "{name}" on node "{node}" with '
        'max_capacity {max_capacity:g} tail "{tail}"'
    )
)
def given_model_contains_tail_only_turbine(
    plexos_model_builder: PlexosModelBuilder,
    name: str,
    node: str,
    max_capacity: float,
    tail: str,
) -> None:
    plexos_model_builder.add_tail_only_turbine(name, node, max_capacity, tail)


@given(
    parsers.parse(
        'the model contains reservoir hydro "{name}" on node "{node}" with '
        'max_capacity {max_capacity:g} head "{head}" max_volume {max_volume:g} '
        "initial_volume {initial_volume:g}"
    )
)
def given_model_contains_reservoir_hydro(
    plexos_model_builder: PlexosModelBuilder,
    name: str,
    node: str,
    max_capacity: float,
    head: str,
    max_volume: float,
    initial_volume: float,
) -> None:
    plexos_model_builder.add_reservoir_hydro(
        name=name,
        node=node,
        max_capacity=max_capacity,
        head=head,
        max_volume=max_volume,
        initial_volume=initial_volume,
    )


@given(
    parsers.parse(
        'the model contains storage "{name}" with max_volume {max_volume:g} '
        "initial_volume {initial_volume:g}"
    )
)
def given_model_contains_storage(
    plexos_model_builder: PlexosModelBuilder,
    name: str,
    max_volume: float,
    initial_volume: float,
) -> None:
    plexos_model_builder.add_orphan_storage(
        name, max_volume=max_volume, initial_volume=initial_volume
    )


@given(parsers.parse('the model contains storage "{name}" stating no volumes'))
def given_model_contains_bare_storage(plexos_model_builder: PlexosModelBuilder, name: str) -> None:
    plexos_model_builder.add_orphan_storage(name)


@given(
    parsers.parse('the model contains node "{name}" in region "{region}" with voltage {voltage:g}')
)
def given_model_contains_node_with_voltage(
    plexos_model_builder: PlexosModelBuilder, name: str, region: str, voltage: float
) -> None:
    plexos_model_builder.add_node(name, region=region, voltage=voltage)


@given(
    parsers.parse(
        'the model contains slack node "{name}" in region "{region}" with voltage {voltage:g}'
    )
)
def given_model_contains_slack_node(
    plexos_model_builder: PlexosModelBuilder, name: str, region: str, voltage: float
) -> None:
    plexos_model_builder.add_slack_node(name, region=region, voltage=voltage)


@given(
    parsers.parse(
        'the model contains non-slack node "{name}" in region "{region}" with voltage {voltage:g}'
    )
)
def given_model_contains_non_slack_node(
    plexos_model_builder: PlexosModelBuilder, name: str, region: str, voltage: float
) -> None:
    plexos_model_builder.add_non_slack_node(name, region=region, voltage=voltage)


@given(
    parsers.parse('the model contains property "{property_name}" of {value:g} on region "{region}"')
)
def given_model_contains_region_property(
    plexos_model_builder: PlexosModelBuilder, property_name: str, value: float, region: str
) -> None:
    plexos_model_builder.add_region_property(region, property_name, value)


@given(parsers.parse('the model contains property "{property_name}" of {value:g} on line "{name}"'))
def given_model_contains_line_property(
    plexos_model_builder: PlexosModelBuilder, property_name: str, value: float, name: str
) -> None:
    plexos_model_builder.add_line_property(name, property_name, value)


@given(
    parsers.parse(
        'the model contains transport line "{name}" from "{node_from}" to "{node_to}" '
        "with max flow {max_flow:g} min flow {min_flow:g}"
    )
)
def given_model_contains_transport_line(
    plexos_model_builder: PlexosModelBuilder,
    name: str,
    node_from: str,
    node_to: str,
    max_flow: float,
    min_flow: float,
) -> None:
    plexos_model_builder.add_transport_line(
        name, LineEndpoints(node_from, node_to), max_flow=max_flow, min_flow=min_flow
    )


@given(
    parsers.parse(
        'the model contains transport line "{name}" from "{node_from}" to "{node_to}" '
        'with max flow bands "{max_flow}" min flow bands "{min_flow}"'
    )
)
def given_model_contains_banded_transport_line(
    plexos_model_builder: PlexosModelBuilder,
    name: str,
    node_from: str,
    node_to: str,
    max_flow: str,
    min_flow: str,
) -> None:
    plexos_model_builder.add_banded_transport_line(
        name,
        LineEndpoints(node_from, node_to),
        _bands(max_flow),
        _bands(min_flow),
    )


def _bands(values: str) -> list[float]:
    return [float(value.strip()) for value in values.split(",")]


@given(
    parsers.parse(
        'the model contains electrical line "{name}" from "{node_from}" to "{node_to}" '
        "resistance {resistance:g} reactance {reactance:g} max rating {max_rating:g}"
    )
)
def given_model_contains_electrical_line(
    plexos_model_builder: PlexosModelBuilder,
    name: str,
    node_from: str,
    node_to: str,
    resistance: float,
    reactance: float,
    max_rating: float,
) -> None:
    plexos_model_builder.add_electrical_line(
        name,
        LineEndpoints(node_from, node_to),
        resistance=resistance,
        reactance=reactance,
        max_rating=max_rating,
    )


@given(
    parsers.parse(
        'the model contains transport line "{name}" from "{node_from}" to "{node_to}" '
        "with max flow {max_flow:g} and expansion type DC"
    )
)
def given_model_contains_dc_expansion_line(
    plexos_model_builder: PlexosModelBuilder,
    name: str,
    node_from: str,
    node_to: str,
    max_flow: float,
) -> None:
    plexos_model_builder.add_dc_expansion_line(
        name, LineEndpoints(node_from, node_to), max_flow=max_flow
    )


@given(
    parsers.parse(
        'the model contains HVDC line "{name}" from "{node_from}" to "{node_to}" '
        "with max flow {max_flow:g}"
    )
)
def given_model_contains_hvdc_line(
    plexos_model_builder: PlexosModelBuilder,
    name: str,
    node_from: str,
    node_to: str,
    max_flow: float,
) -> None:
    plexos_model_builder.add_dc_expansion_line(
        name, LineEndpoints(node_from, node_to), max_flow=max_flow
    )


@given(parsers.parse('the model contains line "{name}" from "{node_from}" with no Node To'))
def given_model_contains_endpointless_line(
    plexos_model_builder: PlexosModelBuilder, name: str, node_from: str
) -> None:
    plexos_model_builder.add_endpointless_line(name, node_from)


@given(
    parsers.parse(
        'the model contains line "{name}" from "{node_from}" to "{node_to}" with no flow limits'
    )
)
def given_model_contains_unrated_line(
    plexos_model_builder: PlexosModelBuilder, name: str, node_from: str, node_to: str
) -> None:
    plexos_model_builder.add_unrated_line(name, LineEndpoints(node_from, node_to))


@given(
    parsers.parse(
        'the model contains line "{name}" from "{node_from}" to "{node_to}" '
        "with min flow {min_flow:g} and no max flow"
    )
)
def given_model_contains_reverse_only_line(
    plexos_model_builder: PlexosModelBuilder,
    name: str,
    node_from: str,
    node_to: str,
    min_flow: float,
) -> None:
    plexos_model_builder.add_reverse_only_line(
        name, LineEndpoints(node_from, node_to), min_flow=min_flow
    )


@given(parsers.parse('the model contains region load "{region}" with peak {peak:g}'))
def given_model_contains_region_load(
    plexos_model_builder: PlexosModelBuilder, region: str, peak: float
) -> None:
    plexos_model_builder.add_region_load(region, peak=peak)


@given(
    parsers.parse(
        'the model contains region load "{region}" with peak {peak:g} from data file "{name}"'
    )
)
def given_model_contains_region_load_from_data_file(
    plexos_model_builder: PlexosModelBuilder, region: str, peak: float, name: str
) -> None:
    plexos_model_builder.add_region_load(region, peak=peak, data_file=name)


@given(parsers.parse('the model states line "{name}" property "{property_name}" as {value:g}'))
def given_line_has_property(
    plexos_model_builder: PlexosModelBuilder, name: str, property_name: str, value: float
) -> None:
    plexos_model_builder.add_line_property(name, property_name, value)


@given(
    parsers.parse('storage "{name}" has property "{property_name}" from data file "{data_file}"')
)
def given_storage_has_property_from_data_file(
    plexos_model_builder: PlexosModelBuilder, name: str, property_name: str, data_file: str
) -> None:
    plexos_model_builder.add_storage_property_from_data_file(name, property_name, data_file)


@given(parsers.parse('the model contains region "{name}" with VoLL {voll:g}'))
def given_model_contains_region_with_voll(
    plexos_model_builder: PlexosModelBuilder, name: str, voll: float
) -> None:
    plexos_model_builder.add_region(name)
    plexos_model_builder.add_region_voll(name, voll)


@given(
    parsers.parse(
        'the model contains data file "{name}" at "{path}" with hourly values "{values}" '
        'and text column "{column}" with values "{text_values}"'
    )
)
def given_model_contains_data_file_with_text_column(
    plexos_model_builder: PlexosModelBuilder,
    name: str,
    path: str,
    values: str,
    column: str,
    text_values: str,
) -> None:
    plexos_model_builder.add_data_file_with_text_column(
        name,
        path,
        [float(value.strip()) for value in values.split(",")],
        column,
        [text.strip() for text in text_values.split(",")],
    )


@given(
    parsers.parse(
        'the model contains sampled data file "{name}" at "{path}" with samples "{samples}"'
    )
)
def given_model_contains_sampled_data_file(
    plexos_model_builder: PlexosModelBuilder, name: str, path: str, samples: str
) -> None:
    columns = [
        [float(value.strip()) for value in column.split(",")] for column in samples.split(";")
    ]
    plexos_model_builder.add_sampled_data_file(name, path, columns)


@given(
    parsers.parse(
        'the model contains per-object data file "{name}" at "{path}" with values "{values}"'
    )
)
def given_model_contains_per_object_data_file(
    plexos_model_builder: PlexosModelBuilder, name: str, path: str, values: str
) -> None:
    values_by_object = {
        object_name.strip(): [float(value.strip()) for value in object_values.split(",")]
        for object_name, object_values in (entry.split(":", 1) for entry in values.split(";"))
    }
    plexos_model_builder.add_data_file_by_object(name, path, values_by_object)


@given(
    parsers.parse(
        'the model contains monthly data file "{name}" at "{path}" for "{component}" '
        'with monthly values "{values}"'
    )
)
def given_model_contains_monthly_data_file(
    plexos_model_builder: PlexosModelBuilder, name: str, path: str, component: str, values: str
) -> None:
    plexos_model_builder.add_monthly_data_file(
        name, path, component, [float(value.strip()) for value in values.split(",")]
    )


@given(parsers.parse('generator "{name}" states "{property_name}" of {value:g} from "{date_from}"'))
def given_generator_property_dated_from(
    plexos_model_builder: PlexosModelBuilder,
    name: str,
    property_name: str,
    value: float,
    date_from: str,
) -> None:
    plexos_model_builder.date_generator_property(
        name, property_name, value, DateBand(date.fromisoformat(date_from))
    )


@given(
    parsers.parse(
        'generator "{name}" states "{property_name}" of {value:g} from "{date_from}" to "{date_to}"'
    )
)
def given_generator_property_dated_band(
    plexos_model_builder: PlexosModelBuilder,
    name: str,
    property_name: str,
    value: float,
    date_from: str,
    date_to: str,
) -> None:
    plexos_model_builder.date_generator_property(
        name,
        property_name,
        value,
        DateBand(date.fromisoformat(date_from), date.fromisoformat(date_to)),
    )


@given(parsers.parse('fuel "{name}" costs {price:g} from "{date_from}"'))
def given_fuel_price_dated_from(
    plexos_model_builder: PlexosModelBuilder, name: str, price: float, date_from: str
) -> None:
    plexos_model_builder.date_fuel_price(name, price, DateBand(date.fromisoformat(date_from)))


@given(parsers.parse('the model contains market "{name}" trading at node "{node}"'))
def given_model_contains_market(
    plexos_model_builder: PlexosModelBuilder, name: str, node: str
) -> None:
    plexos_model_builder.add_market(name, node)


@given(parsers.parse('horizon "{name}" states "{attribute}" as "{value}"'))
def given_horizon_states_attribute(
    plexos_model_builder: PlexosModelBuilder, name: str, attribute: str, value: str
) -> None:
    plexos_model_builder.set_horizon_attribute(name, attribute, value)


@given(
    parsers.parse(
        'the model contains horizon "{name}" on model "{model}" starting "{start}" '
        "spanning {step_count:d} days at {periods_per_day:d} periods per day"
    )
)
def given_model_contains_horizon(
    plexos_model_builder: PlexosModelBuilder,
    name: str,
    model: str,
    start: str,
    step_count: int,
    periods_per_day: int,
) -> None:
    plexos_model_builder.add_horizon(
        model=model,
        name=name,
        start=date.fromisoformat(start),
        step_count=step_count,
        periods_per_day=periods_per_day,
    )


@given(
    parsers.parse(
        'the model contains variable "{name}" profiling "{path}" with hourly values "{values}"'
    )
)
def given_model_contains_variable(
    plexos_model_builder: PlexosModelBuilder, name: str, path: str, values: str
) -> None:
    plexos_model_builder.add_variable(
        name, path, [float(value.strip()) for value in values.split(",")]
    )


@given(parsers.parse('the model contains variable "{name}" with timeslice pattern "{pattern}"'))
def given_model_contains_timeslice_variable(
    plexos_model_builder: PlexosModelBuilder, name: str, pattern: str
) -> None:
    plexos_model_builder.add_timeslice_variable(name, pattern)


# --- generators ----------------------------------------------------------------


@given(parsers.parse('the model contains generator "{name}" with "{spec}"'))
def given_model_contains_generator(
    plexos_model_builder: PlexosModelBuilder, name: str, spec: str
) -> None:
    plexos_model_builder.add_generator(name, parse_generator_spec(spec))


@given("the model contains generators:")
def given_model_contains_generators(
    plexos_model_builder: PlexosModelBuilder, datatable: list[list[str]]
) -> None:
    """Several generators at once, one row each, under a header naming the spec fields.

    A header cell is ``name``, one of the membership keys (``node``, ``category``,
    ``fuel``) or a PLEXOS property name written verbatim; an empty cell states nothing.
    """
    header, *rows = datatable
    for row in rows:
        fields = {key: value for key, value in zip(header, row, strict=True) if value}
        name = fields.pop(_NAME_FIELD)
        plexos_model_builder.add_generator(name, build_generator_spec(fields))


@given(
    parsers.parse(
        'the model contains battery "{name}" on node "{node}" power {power:g} '
        'capacity {capacity:g} units {units:g} units out of variable "{variable}"'
    )
)
def given_model_contains_battery_with_units_out(
    plexos_model_builder: PlexosModelBuilder,
    name: str,
    node: str,
    power: float,
    capacity: float,
    units: float,
    variable: str,
) -> None:
    plexos_model_builder.add_bare_battery(name, node)
    plexos_model_builder.add_battery_property(name, "Max Power", power)
    plexos_model_builder.add_battery_property(name, "Capacity", capacity)
    plexos_model_builder.add_battery_property(name, "Units", units)
    plexos_model_builder.add_battery_property(name, "Units Out", 0, variable=variable)


@given(
    parsers.parse(
        'the model contains battery "{name}" on node "{node}" power {power:g} '
        "capacity {capacity:g} charge efficiency {efficiency:g} "
        "and no initial state of charge"
    )
)
def given_model_contains_battery_without_initial_soc(
    plexos_model_builder: PlexosModelBuilder,
    name: str,
    node: str,
    power: float,
    capacity: float,
    efficiency: float,
) -> None:
    plexos_model_builder.add_bare_battery(name, node)
    plexos_model_builder.add_battery_property(name, "Max Power", power)
    plexos_model_builder.add_battery_property(name, "Capacity", capacity)
    plexos_model_builder.add_battery_property(name, "Charge Efficiency", efficiency)


@given(
    parsers.parse(
        'the model contains battery "{name}" on node "{node}" power {power:g} '
        "capacity {capacity:g} initial soc {initial_soc:g} end effects {end_effects:g}"
    )
)
def given_model_contains_battery_with_end_effects(
    plexos_model_builder: PlexosModelBuilder,
    name: str,
    node: str,
    power: float,
    capacity: float,
    initial_soc: float,
    end_effects: float,
) -> None:
    plexos_model_builder.add_battery(
        name=name,
        node=node,
        max_power=power,
        capacity=capacity,
        charge_efficiency=90,
        initial_soc=initial_soc,
    )
    plexos_model_builder.add_battery_property(name, "End Effects Method", end_effects)
