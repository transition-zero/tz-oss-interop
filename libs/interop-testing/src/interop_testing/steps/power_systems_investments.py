"""pytest-bdd vocabulary for a PowerSystemsInvestments portfolio a pipeline emitted.

The portfolio envelope is a different document from the SiennaSchemas portfolio in
``interop_testing.steps.sienna_portfolio``: one flat ``data.components`` list with a
``__metadata__.type`` on each component, which is the shape
``interop_testing.steps.power_simulations`` already reads. Assertions here read that shape,
plus the series companion the envelope cannot carry.

Nothing builds a portfolio as pipeline *input*, so there are no Given steps.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from pytest_bdd import parsers, then

from interop_testing.steps.power_simulations import (
    find_power_simulations_component,
    navigate_power_simulations_field,
    read_power_simulations_system,
)

_TIME_SERIES_STORAGE_FILE = "time_series_storage_file"
# A weight is the days of a year divided by the share of one day, so it is rarely a round number.
_WEIGHT_TOLERANCE = 1e-5


def read_series_document(path: str) -> dict[str, Any]:
    result: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
    return result


def get_series_record(document: dict[str, Any], component: str, name: str) -> dict[str, Any]:
    matching: list[dict[str, Any]] = [
        record
        for record in document.get("records", [])
        if record.get("component_type") == component and record.get("component_name") == name
    ]
    assert len(matching) == 1, (
        f"expected 1 series record for {component!r} named {name!r}, got {len(matching)}"
    )
    return matching[0]


@then(
    parsers.re(
        r'the portfolio "(?P<path>[^"]+)" contains (?P<count>\d+) '
        r'components? of type "(?P<psip_type>[^"]+)"'
    )
)
def assert_portfolio_component_count(path: str, count: str, psip_type: str) -> None:
    components = read_power_simulations_system(path).get("data", {}).get("components", [])
    actual = [c for c in components if c.get("__metadata__", {}).get("type") == psip_type]
    assert len(actual) == int(count), (
        f"expected {count} components of type {psip_type!r} in {path}, "
        f"got {len(actual)}: {[c.get('name') for c in actual]}"
    )


@then(
    parsers.parse(
        'the portfolio "{path}" component "{psip_type}" named "{name}" '
        'has field "{field}" equal to {value}'
    )
)
def assert_portfolio_field(path: str, psip_type: str, name: str, field: str, value: str) -> None:
    expected = json.loads(value)
    component = find_power_simulations_component(
        read_power_simulations_system(path), psip_type, name
    )
    actual = component.get(field)
    assert actual == expected, f"expected {psip_type}:{name}.{field} = {expected!r}, got {actual!r}"


@then(
    parsers.parse(
        'the portfolio "{path}" component "{psip_type}" named "{name}" '
        'has "{field_path}" equal to "{expected}"'
    )
)
def assert_portfolio_nested_field(
    path: str, psip_type: str, name: str, field_path: str, expected: str
) -> None:
    component = find_power_simulations_component(
        read_power_simulations_system(path), psip_type, name
    )
    actual = navigate_power_simulations_field(component, field_path)
    assert str(actual) == expected, (
        f"expected {psip_type}:{name}.{field_path} = {expected!r}, got {actual!r}"
    )


@then(
    parsers.parse(
        'the portfolio "{path}" component "{psip_type}" named "{name}" has no field "{field}"'
    )
)
def assert_portfolio_no_field(path: str, psip_type: str, name: str, field: str) -> None:
    component = find_power_simulations_component(
        read_power_simulations_system(path), psip_type, name
    )
    assert field not in component, (
        f"expected {psip_type}:{name} to state no {field!r}, got {component[field]!r}"
    )


@then(parsers.parse('the portfolio "{path}" states no time series storage file'))
def assert_portfolio_states_no_store(path: str) -> None:
    data = read_power_simulations_system(path).get("data", {})
    assert _TIME_SERIES_STORAGE_FILE not in data, (
        f"expected {path} to name no time series store, got {data[_TIME_SERIES_STORAGE_FILE]!r}"
    )


@then(parsers.re(r'the series document "(?P<path>[^"]+)" holds (?P<count>\d+) records?'))
def assert_series_record_count(path: str, count: str) -> None:
    records = read_series_document(path).get("records", [])
    assert len(records) == int(count), (
        f"expected {count} series records in {path}, got {len(records)}: "
        f"{[r.get('component_name') for r in records]}"
    )


@then(
    parsers.parse(
        'the series document "{path}" record for "{component}" named "{name}" '
        'holds series "{series_name}" for year "{year}" representative day {rep_day:d}'
    )
)
def assert_series_record_features(
    path: str, component: str, name: str, series_name: str, year: str, rep_day: int
) -> None:
    record = get_series_record(read_series_document(path), component, name)
    actual = (record.get("series_name"), record.get("year"), record.get("rep_day"))
    assert actual == (series_name, year, rep_day), (
        f"expected {component}:{name} series {series_name!r} year {year!r} "
        f"representative day {rep_day}, got {actual!r}"
    )


@then(
    parsers.parse(
        'the series document "{path}" record for "{component}" named "{name}" '
        'has field "{field}" equal to {value}'
    )
)
def assert_series_record_field(
    path: str, component: str, name: str, field: str, value: str
) -> None:
    expected = json.loads(value)
    record = get_series_record(read_series_document(path), component, name)
    assert record.get(field) == expected, (
        f"expected {component}:{name}.{field} = {expected!r}, got {record.get(field)!r}"
    )


@then(parsers.parse('the series document "{path}" states one period from "{start}" to "{end}"'))
def assert_series_period(path: str, start: str, end: str) -> None:
    periods = read_series_document(path).get("periods", [])
    assert periods == [{"start": start, "end": end}], (
        f"expected one period {start} to {end} in {path}, got {periods!r}"
    )


@then(
    parsers.parse(
        'the series document "{path}" record for "{component}" named "{name}" in the '
        'representative day {rep_day:d} of the year "{year}" starts at "{first_hour}" with '
        "weight {weight:g} and holds {count:d} values that peak at {peak:g}"
    )
)
def assert_series_day_record(
    path: str,
    component: str,
    name: str,
    rep_day: int,
    year: str,
    first_hour: str,
    weight: float,
    count: int,
    peak: float,
) -> None:
    matching = [
        record
        for record in read_series_document(path).get("records", [])
        if (record.get("component_type"), record.get("component_name")) == (component, name)
        and (record.get("year"), record.get("rep_day")) == (year, rep_day)
    ]
    assert len(matching) == 1, (
        f"expected 1 record for {component}:{name} day {rep_day} of {year}, got {len(matching)}"
    )
    record = matching[0]
    values = record.get("values", [])
    actual = (record.get("initial_timestamp"), len(values), max(values, default=None))
    assert actual == (first_hour, count, peak), (
        f"expected start {first_hour}, {count} values, peak {peak}; got {actual!r}"
    )
    assert math.isclose(record.get("weight", 0.0), weight, rel_tol=_WEIGHT_TOLERANCE), (
        f"expected weight {weight}, got {record.get('weight')!r}"
    )


@then(
    parsers.parse('the series document "{path}" states one period for each of the years "{years}"')
)
def assert_series_periods(path: str, years: str) -> None:
    periods = read_series_document(path).get("periods", [])
    expected = [{"start": f"{year}-01-01", "end": f"{year}-12-31"} for year in years.split()]
    assert periods == expected, f"expected periods {expected!r} in {path}, got {periods!r}"
