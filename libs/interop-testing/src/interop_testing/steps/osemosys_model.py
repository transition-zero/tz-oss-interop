"""pytest-bdd Given steps for building an OSeMOSYS model fixture.

Every step operates on the ``osemosys_model_builder`` fixture that ``Given an OSeMOSYS
model`` creates. Nothing translates *to* OSeMOSYS yet, so there is no matching assertion
vocabulary.

A step states a parameter's rows as one string: a comma separates the values within a row and
a semicolon separates the rows, so ``"R1, COAL, 2030, 1500; R1, WIND, 2030, 900"`` is two
rows of four values.
"""

from __future__ import annotations

from pathlib import Path

from pytest_bdd import given, parsers

from interop_testing.builders.osemosys_models import OsemosysModelBuilder, ParameterSpec

_ROW_SEPARATOR = ";"
_VALUE_SEPARATOR = ","


@given("an OSeMOSYS model", target_fixture="osemosys_model_builder")
def given_osemosys_model() -> OsemosysModelBuilder:
    return OsemosysModelBuilder()


@given(parsers.parse('the model has set "{name}" with members "{members}"'))
def given_model_has_set(
    osemosys_model_builder: OsemosysModelBuilder, name: str, members: str
) -> None:
    osemosys_model_builder.add_set(name, _split_values(members))


@given(parsers.parse('the model has parameter "{name}" indexed by "{indices}" with rows "{rows}"'))
def given_model_has_parameter(
    osemosys_model_builder: OsemosysModelBuilder, name: str, indices: str, rows: str
) -> None:
    osemosys_model_builder.add_parameter(_spec(name, indices), _split_rows(rows))


@given(parsers.parse('the model has parameter "{name}" indexed by "{indices}" with no rows'))
def given_model_has_empty_parameter(
    osemosys_model_builder: OsemosysModelBuilder, name: str, indices: str
) -> None:
    osemosys_model_builder.add_parameter(_spec(name, indices), [])


@given(
    parsers.parse(
        'the model has parameter "{name}" indexed by "{indices}" '
        'defaulting to {default:g} with rows "{rows}"'
    )
)
def given_model_has_parameter_with_default(
    osemosys_model_builder: OsemosysModelBuilder,
    name: str,
    indices: str,
    default: float,
    rows: str,
) -> None:
    spec = _spec(name, indices, default=default)
    osemosys_model_builder.add_parameter(spec, _split_rows(rows))


@given(
    parsers.parse(
        'the model has parameter "{name}" short named "{short_name}" '
        'indexed by "{indices}" with rows "{rows}"'
    )
)
def given_model_has_short_named_parameter(
    osemosys_model_builder: OsemosysModelBuilder,
    name: str,
    short_name: str,
    indices: str,
    rows: str,
) -> None:
    spec = _spec(name, indices, short_name=short_name)
    osemosys_model_builder.add_parameter(spec, _split_rows(rows))


@given(parsers.parse('the model has result "{name}" indexed by "{indices}" with rows "{rows}"'))
def given_model_has_result(
    osemosys_model_builder: OsemosysModelBuilder, name: str, indices: str, rows: str
) -> None:
    osemosys_model_builder.add_result(_spec(name, indices), _split_rows(rows))


@given(parsers.parse('the folder omits the file for parameter "{name}"'))
def given_folder_omits_parameter_file(
    osemosys_model_builder: OsemosysModelBuilder, name: str
) -> None:
    osemosys_model_builder.omit_parameter_file(name)


@given(parsers.parse('the file for parameter "{name}" is named by its short name'))
def given_parameter_file_uses_short_name(
    osemosys_model_builder: OsemosysModelBuilder, name: str
) -> None:
    osemosys_model_builder.file_parameter_under_short_name(name)


@given(parsers.parse('the model is saved in "{directory}"'))
def given_model_is_saved_in(osemosys_model_builder: OsemosysModelBuilder, directory: str) -> None:
    osemosys_model_builder.save(Path(directory))


def _spec(
    name: str, indices: str, default: float = 0.0, short_name: str | None = None
) -> ParameterSpec:
    return ParameterSpec(
        name=name,
        indices=tuple(_split_values(indices)),
        default=default,
        short_name=short_name,
    )


def _split_values(text: str) -> list[str]:
    return [value.strip() for value in text.split(_VALUE_SEPARATOR)]


def _split_rows(text: str) -> list[list[str]]:
    return [_split_values(row) for row in text.split(_ROW_SEPARATOR)]
