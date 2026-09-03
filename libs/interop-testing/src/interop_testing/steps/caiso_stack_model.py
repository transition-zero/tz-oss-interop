"""pytest-bdd Given steps for building a CAISO stack-model fixture.

Every step operates on the ``caiso_stack_model_builder`` fixture that ``Given a CAISO
stack model`` creates.
"""

from __future__ import annotations

from pathlib import Path

from pytest_bdd import given, parsers

from interop_testing.builders.caiso_stack_models import CaisoStackModelBuilder


@given("a CAISO stack model", target_fixture="caiso_stack_model_builder")
def given_caiso_stack_model() -> CaisoStackModelBuilder:
    return CaisoStackModelBuilder()


@given(
    parsers.parse(
        "the stack model covers month {month:d} day {day:d} hour ending {hour_ending:d} "
        "with load {load:g} and surplus {surplus:g}"
    )
)
def given_stack_model_hour(
    caiso_stack_model_builder: CaisoStackModelBuilder,
    month: int,
    day: int,
    hour_ending: int,
    load: float,
    surplus: float,
) -> None:
    caiso_stack_model_builder.add_hour(
        month=month, day=day, hour_ending=hour_ending, load=load, surplus=surplus
    )


@given(parsers.parse('that hour has "{category}" capacity {value:g}'))
def given_stack_model_capacity(
    caiso_stack_model_builder: CaisoStackModelBuilder, category: str, value: float
) -> None:
    caiso_stack_model_builder.set_capacity(category, value)


@given(parsers.parse('that hour has "{category}" dispatch {value:g}'))
def given_stack_model_dispatch(
    caiso_stack_model_builder: CaisoStackModelBuilder, category: str, value: float
) -> None:
    caiso_stack_model_builder.set_dispatch(category, value)


@given(parsers.parse('the appendix gives "{fuel_type}" {value:g} in {month_header}'))
def given_appendix_fuel(
    caiso_stack_model_builder: CaisoStackModelBuilder,
    fuel_type: str,
    value: float,
    month_header: str,
) -> None:
    caiso_stack_model_builder.add_appendix_fuel(fuel_type, {month_header: value})


@given(
    parsers.parse('the stack model is saved as "{stack_model}" and the appendix as "{appendix}"')
)
def given_stack_model_saved(
    caiso_stack_model_builder: CaisoStackModelBuilder, stack_model: str, appendix: str
) -> None:
    caiso_stack_model_builder.save(Path(stack_model), Path(appendix))
