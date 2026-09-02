"""pytest-bdd Given steps for building a PLEXOS model fixture.

Every step operates on the ``plexos_model_builder`` fixture that ``Given a Plexos
model`` creates. Nothing translates *to* PLEXOS, so there is no matching
assertion vocabulary.
"""

from __future__ import annotations

from pathlib import Path

from pytest_bdd import given, parsers

from interop_testing.builders.plexos_models import (
    PlexosModelBuilder,
)

# The generators table's header cell naming the generator itself, not one of its fields.
_NAME_FIELD = "name"


@given("a Plexos model", target_fixture="plexos_model_builder")
def given_plexos_model() -> PlexosModelBuilder:
    return PlexosModelBuilder()


@given(parsers.parse('the model contains region "{name}"'))
def given_model_contains_region(plexos_model_builder: PlexosModelBuilder, name: str) -> None:
    plexos_model_builder.add_region(name)


@given(parsers.parse('the model contains node "{name}" in region "{region}"'))
def given_model_contains_node(
    plexos_model_builder: PlexosModelBuilder, name: str, region: str
) -> None:
    plexos_model_builder.add_node(name, region=region)


@given(parsers.parse('the model contains load "{node}" with peak {peak:g}'))
def given_model_contains_load(
    plexos_model_builder: PlexosModelBuilder, node: str, peak: float
) -> None:
    plexos_model_builder.add_load(node, peak=peak)


@given(
    parsers.parse('the model contains load "{node}" with peak {peak:g} in scenario "{scenario}"')
)
def given_model_contains_load_in_scenario(
    plexos_model_builder: PlexosModelBuilder, node: str, peak: float, scenario: str
) -> None:
    plexos_model_builder.add_load(node, peak=peak, scenarios=[scenario])


@given(
    parsers.parse('the model contains load "{node}" with peak {peak:g} in scenarios "{scenarios}"')
)
def given_model_contains_load_in_scenarios(
    plexos_model_builder: PlexosModelBuilder, node: str, peak: float, scenarios: str
) -> None:
    plexos_model_builder.add_load(
        node, peak=peak, scenarios=[name.strip() for name in scenarios.split(",")]
    )


@given(parsers.parse('the model states "{property_name}" in "{unit}"'))
def given_model_states_property_unit(
    plexos_model_builder: PlexosModelBuilder, property_name: str, unit: str
) -> None:
    plexos_model_builder.state_property_unit(property_name, unit)


@given(parsers.parse('the model measures in "{units_setting}"'))
def given_model_measures_in(plexos_model_builder: PlexosModelBuilder, units_setting: str) -> None:
    plexos_model_builder.measure_in(units_setting)


@given(
    parsers.parse(
        'the model contains "{property_name}" {value:g} in band {band:d} for generator "{name}"'
    )
)
def given_model_contains_property_band(
    plexos_model_builder: PlexosModelBuilder,
    property_name: str,
    value: float,
    band: int,
    name: str,
) -> None:
    plexos_model_builder.add_generator_property_band(name, property_name, band=band, value=value)


@given(parsers.parse('the export omits the {class_name} object "{name}"'))
def given_export_omits_object(
    plexos_model_builder: PlexosModelBuilder, class_name: str, name: str
) -> None:
    plexos_model_builder.omit_object_row(class_name, name)


@given(
    parsers.parse(
        'the model contains data file "{name}" at "{path}" with {periods:d} period '
        'columns per day over {days:d} days "{values}"'
    )
)
def given_model_contains_period_column_data_file(
    plexos_model_builder: PlexosModelBuilder,
    name: str,
    path: str,
    periods: int,
    days: int,
    values: str,
) -> None:
    parsed = [float(value) for value in values.split(",")]
    expected = periods * days
    if len(parsed) != expected:
        raise ValueError(f"expected {expected} values for {days} days of {periods}, got {parsed}")
    plexos_model_builder.add_period_column_data_file(name, path, periods, parsed)


@given(
    parsers.parse(
        'the model contains data file "{name}" at "{path}" with {periods:d} period '
        "columns per day over {days:d} days counting from {start:d}"
    )
)
def given_model_contains_counted_period_column_data_file(
    plexos_model_builder: PlexosModelBuilder,
    name: str,
    path: str,
    periods: int,
    days: int,
    start: int,
) -> None:
    """Values count up from ``start``, so a scenario can use 48 columns without listing them."""
    counted = [float(value) for value in range(start, start + periods * days)]
    plexos_model_builder.add_period_column_data_file(name, path, periods, counted)


@given(
    parsers.parse(
        'the model contains data file "{name}" at "{path}" with {periods:d} period '
        "columns, whole numbers for {days:d} days then {value:g}"
    )
)
def given_model_contains_late_fraction_period_column_data_file(
    plexos_model_builder: PlexosModelBuilder,
    name: str,
    path: str,
    periods: int,
    days: int,
    value: float,
) -> None:
    """A column that only turns fractional deep into the file, past any bounded schema window."""
    whole = [1.0] * (periods * days)
    plexos_model_builder.add_period_column_data_file(
        name, path, periods, [*whole, *[value] * periods]
    )


@given(
    parsers.parse(
        'the model contains data file "{name}" at "{path}" with daily column '
        '"{column}" values "{values}"'
    )
)
def given_model_contains_daily_data_file(
    plexos_model_builder: PlexosModelBuilder,
    name: str,
    path: str,
    column: str,
    values: str,
) -> None:
    plexos_model_builder.add_daily_data_file(
        name, path, column, [float(value) for value in values.split(",")]
    )


@given(parsers.parse('the model names data file "{name}" at "{path}" but the package omits it'))
def given_model_names_missing_data_file(
    plexos_model_builder: PlexosModelBuilder, name: str, path: str
) -> None:
    plexos_model_builder.add_missing_data_file(name, path)


@given(parsers.parse('the export omits the filename text of data file "{name}"'))
def given_export_omits_data_file_text(plexos_model_builder: PlexosModelBuilder, name: str) -> None:
    plexos_model_builder.omit_data_file_text(name)


@given(
    parsers.parse('the model contains data file "{name}" at "{path}" with hourly values "{values}"')
)
def given_model_contains_data_file(
    plexos_model_builder: PlexosModelBuilder, name: str, path: str, values: str
) -> None:
    plexos_model_builder.add_data_file(
        name, path, [float(value.strip()) for value in values.split(",")]
    )


@given(parsers.parse('the model contains load "{node}" with peak {peak:g} from data file "{name}"'))
def given_model_contains_load_from_data_file(
    plexos_model_builder: PlexosModelBuilder, node: str, peak: float, name: str
) -> None:
    plexos_model_builder.add_load(node, peak=peak, data_file=name)


@given(parsers.parse('the model contains fuel "{name}" with price {price:g}'))
def given_model_contains_fuel(
    plexos_model_builder: PlexosModelBuilder, name: str, price: float
) -> None:
    plexos_model_builder.add_fuel(name, price)


@given(
    parsers.parse(
        'the model contains emission "{name}" with price {price:g} '
        'on fuel "{fuel}" production rate {rate:g}'
    )
)
def given_model_contains_emission(
    plexos_model_builder: PlexosModelBuilder, name: str, price: float, fuel: str, rate: float
) -> None:
    plexos_model_builder.add_emission(name=name, price=price, fuel=fuel, production_rate=rate)


@given(
    parsers.parse(
        'the model contains reserve "{name}" of type {reserve_type:g} requiring '
        '{requirement:g} from generators "{generators}"'
    )
)
def given_model_contains_reserve(
    plexos_model_builder: PlexosModelBuilder,
    name: str,
    reserve_type: float,
    requirement: float,
    generators: str,
) -> None:
    plexos_model_builder.add_reserve(
        name,
        generators=[generator.strip() for generator in generators.split(",")],
        reserve_type=reserve_type,
        requirement=requirement,
    )


@given(
    parsers.parse(
        'the model contains reserve "{name}" of type {reserve_type:g} taking share '
        '{share:g} of variable "{variable}" from generators "{generators}"'
    )
)
def given_model_contains_reserve_sharing_variable(
    plexos_model_builder: PlexosModelBuilder,
    name: str,
    reserve_type: float,
    share: float,
    variable: str,
    generators: str,
) -> None:
    plexos_model_builder.add_reserve(
        name,
        generators=[generator.strip() for generator in generators.split(",")],
        reserve_type=reserve_type,
        requirement=share,
        variable=variable,
    )


@given(parsers.parse('the model contains variable "{name}" profiling data file "{data_file}"'))
def given_model_contains_variable_on_data_file(
    plexos_model_builder: PlexosModelBuilder, name: str, data_file: str
) -> None:
    plexos_model_builder.add_variable_on_data_file(name, data_file)


@given(parsers.parse('reserve "{name}" prices a shortage at {price:g}'))
def given_reserve_prices_shortage(
    plexos_model_builder: PlexosModelBuilder, name: str, price: float
) -> None:
    plexos_model_builder.price_reserve_shortage(name, price)


@given(parsers.parse('reserve "{name}" is mutually exclusive'))
def given_reserve_is_mutually_exclusive(
    plexos_model_builder: PlexosModelBuilder, name: str
) -> None:
    plexos_model_builder.mark_reserve_mutually_exclusive(name)


@given(
    parsers.parse(
        'the model contains reserve "{name}" of type {reserve_type:g} reading its requirement '
        'from data file "{data_file}" from generators "{generators}"'
    )
)
def given_model_contains_file_backed_reserve(
    plexos_model_builder: PlexosModelBuilder,
    name: str,
    reserve_type: float,
    data_file: str,
    generators: str,
) -> None:
    plexos_model_builder.add_reserve(
        name,
        generators=[generator.strip() for generator in generators.split(",")],
        reserve_type=reserve_type,
        requirement=0,
        data_file=data_file,
    )


@given(parsers.parse('reserve "{name}" is not mutually exclusive'))
def given_reserve_is_not_mutually_exclusive(
    plexos_model_builder: PlexosModelBuilder, name: str
) -> None:
    plexos_model_builder.mark_reserve_not_mutually_exclusive(name)


@given(parsers.parse('the model contains scenario "{name}"'))
def given_model_contains_scenario(plexos_model_builder: PlexosModelBuilder, name: str) -> None:
    plexos_model_builder.add_scenario(name)


@given(parsers.parse('the model contains scenario "{name}" with read order {read_order:d}'))
def given_model_contains_scenario_with_read_order(
    plexos_model_builder: PlexosModelBuilder, name: str, read_order: int
) -> None:
    plexos_model_builder.add_scenario(name, read_order=read_order)


@given(parsers.parse('the model contains model "{name}"'))
def given_model_contains_model(plexos_model_builder: PlexosModelBuilder, name: str) -> None:
    plexos_model_builder.add_model(name)


@given(parsers.parse('the model contains model "{name}" with scenarios "{scenarios}"'))
def given_model_contains_model_with_scenarios(
    plexos_model_builder: PlexosModelBuilder, name: str, scenarios: str
) -> None:
    plexos_model_builder.add_model(name, scenarios=[s.strip() for s in scenarios.split(",")])


@given(parsers.parse('the model is saved as "{xml_path}"'))
def given_model_is_saved_as(plexos_model_builder: PlexosModelBuilder, xml_path: str) -> None:
    plexos_model_builder.save(Path(xml_path))


@given(parsers.parse('generator "{name}" burns {offtake:g} GJ of fuel "{fuel}" to start'))
def given_generator_burns_start_fuel(
    plexos_model_builder: PlexosModelBuilder, name: str, offtake: float, fuel: str
) -> None:
    plexos_model_builder.add_start_fuel(name, fuel, offtake)


@given(
    parsers.parse(
        'generator "{name}" burns {offtake:g} GJ of fuel "{fuel}" to start in band {band:d}'
    )
)
def given_generator_burns_start_fuel_in_band(
    plexos_model_builder: PlexosModelBuilder, name: str, offtake: float, fuel: str, band: int
) -> None:
    plexos_model_builder.add_start_fuel(name, fuel, offtake, band=band)
