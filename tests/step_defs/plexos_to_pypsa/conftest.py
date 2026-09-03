"""Shared steps for the PLEXOS → PyPSA pipeline BDD scenarios.

Each ``test_<topic>.py`` here binds ``tests/features/plexos_to_pypsa/<topic>.feature``.
Model-building steps and the assertions on an emitted PyPSA network come from the
``interop_testing`` harness; this module holds the translate driver and the assertions
on the PLEXOS source's own resolved output.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import polars as pl
import pytest
from interop_testing import write_pipeline, write_project_plugin
from pytest_bdd import given, parsers, then, when

from tests.step_defs.conftest import invoke_translate


@when(
    parsers.re(
        r'I run translate against "(?P<xml_path>[^"]+)" pipeline "(?P<pipeline>[^"]+)" '
        r'sink output "(?P<sink_output>[^"]+)"$'
    )
)
def run_translate_plexos_to_pypsa(
    monkeypatch: pytest.MonkeyPatch,
    xml_path: str,
    pipeline: str,
    sink_output: str,
) -> None:
    invoke_translate(
        monkeypatch,
        "plexos",
        "pypsa",
        pipeline,
        source_path=str(Path(xml_path)),
        sink_0_output_path=sink_output,
    )


@when(
    parsers.parse(
        'I run translate against "{xml_path}" pipeline "{pipeline}" sink output dir "{output_dir}"'
    )
)
def run_translate_plexos_ensemble(
    monkeypatch: pytest.MonkeyPatch,
    xml_path: str,
    pipeline: str,
    output_dir: str,
) -> None:
    invoke_translate(
        monkeypatch,
        "plexos",
        "pypsa",
        pipeline,
        source_path=str(Path(xml_path)),
        sink_0_output_dir=output_dir,
    )


@when(
    parsers.re(
        r'I run translate against "(?P<xml_path>[^"]+)" pipeline "(?P<pipeline>[^"]+)" '
        r'for model "(?P<model>[^"]+)" sink output "(?P<sink_output>[^"]+)"$'
    )
)
def run_translate_plexos_to_pypsa_for_model(
    monkeypatch: pytest.MonkeyPatch,
    xml_path: str,
    pipeline: str,
    model: str,
    sink_output: str,
) -> None:
    invoke_translate(
        monkeypatch,
        "plexos",
        "pypsa",
        pipeline,
        source_path=str(Path(xml_path)),
        source_model=model,
        sink_0_output_path=sink_output,
    )


@when(
    parsers.re(
        r'I run translate against "(?P<xml_path>[^"]+)" pipeline "(?P<pipeline>[^"]+)" '
        r'for model "(?P<model>[^"]+)" year (?P<year>\d{4}) '
        r'sink output "(?P<sink_output>[^"]+)"$'
    )
)
def run_translate_plexos_to_pypsa_for_year(
    monkeypatch: pytest.MonkeyPatch,
    xml_path: str,
    pipeline: str,
    model: str,
    year: str,
    sink_output: str,
) -> None:
    invoke_translate(
        monkeypatch,
        "plexos",
        "pypsa",
        pipeline,
        source_path=str(Path(xml_path)),
        source_model=model,
        source_horizon_year=year,
        sink_0_output_path=sink_output,
    )


# A dump_table step reads one resolved source_topology table and writes it as
# {"table": ..., "rows": [...]} JSON, so scenarios can assert on the source's
# resolved output without importing interop into the step definitions.
_DUMP_TABLE_STEP_PY = """\
import json
from pathlib import Path
from typing import Any
from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep


class _DumpTableParams(BaseModel):
    table: str
    out: Path


class _DumpTable(TranslationStep):
    name: ClassVar[str] = "dump_table"
    params_schema: ClassVar[type[BaseModel] | None] = _DumpTableParams

    def run(self, state: State, params: BaseModel | None) -> State:
        assert isinstance(params, _DumpTableParams)
        rows = state.source_topology[params.table].collect().to_dicts()
        params.out.parent.mkdir(parents=True, exist_ok=True)
        dumped = json.dumps({"table": params.table, "rows": rows}, default=str)
        params.out.write_text(dumped, encoding="utf-8")
        return state
"""


_RESOLVE_PIPELINE_YAML = """\
source_framework: plexos
destination_framework: pypsa
source:
  name: stage_plexos_xml
steps:
  - name: dump_table
sinks:
  - name: emit_json
"""


_RESOLVE_MODEL_PIPELINE_YAML = """\
source_framework: plexos
destination_framework: pypsa
source:
  name: stage_plexos_xml
  params:
    model: {model}
steps:
  - name: dump_table
sinks:
  - name: emit_json
"""


# A dump_time_series step reads one staged source_time_series frame, keyed by
# (owner_type, series), and writes its (snapshot, component, value) rows as JSON.
_DUMP_TIME_SERIES_STEP_PY = """\
import json
from pathlib import Path
from typing import Any
from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep


class _DumpTimeSeriesParams(BaseModel):
    owner_type: str
    series: str
    out: Path


class _DumpTimeSeries(TranslationStep):
    name: ClassVar[str] = "dump_time_series"
    params_schema: ClassVar[type[BaseModel] | None] = _DumpTimeSeriesParams

    def run(self, state: State, params: BaseModel | None) -> State:
        assert isinstance(params, _DumpTimeSeriesParams)
        frame = state.source_time_series[(params.owner_type, params.series)]
        rows = frame.collect().to_dicts()
        params.out.parent.mkdir(parents=True, exist_ok=True)
        params.out.write_text(json.dumps({"rows": rows}, default=str), encoding="utf-8")
        return state
"""


_RESOLVE_TIME_SERIES_PIPELINE_YAML = """\
source_framework: plexos
destination_framework: pypsa
source:
  name: stage_plexos_xml
steps:
  - name: dump_time_series
sinks:
  - name: emit_json
"""


@given('a step plugin "dump_table" that writes a source_topology table to JSON')
def given_dump_table_step_plugin() -> None:
    write_project_plugin("steps", "dump_table", _DUMP_TABLE_STEP_PY)


@given(parsers.parse('a project-local pipeline "{name}" that stages plexos and dumps a table'))
def given_plexos_resolve_pipeline(name: str) -> None:
    write_pipeline(name, _RESOLVE_PIPELINE_YAML)


@given(
    parsers.parse(
        'a project-local pipeline "{name}" that stages plexos for model "{model}" and dumps a table'
    )
)
def given_plexos_resolve_model_pipeline(name: str, model: str) -> None:
    write_pipeline(name, _RESOLVE_MODEL_PIPELINE_YAML.format(model=model))


@given('a step plugin "dump_time_series" that writes a source_time_series frame to JSON')
def given_dump_time_series_step_plugin() -> None:
    write_project_plugin("steps", "dump_time_series", _DUMP_TIME_SERIES_STEP_PY)


@given(
    parsers.parse('a project-local pipeline "{name}" that stages plexos and dumps a time series')
)
def given_plexos_resolve_time_series_pipeline(name: str) -> None:
    write_pipeline(name, _RESOLVE_TIME_SERIES_PIPELINE_YAML)


@when(
    parsers.parse(
        'I stage "{xml_path}" through "{pipeline}" dumping series "{owner_type}"/"{series}" '
        'to "{out}" with system output "{system_output}"'
    )
)
def run_stage_and_dump_series(
    monkeypatch: pytest.MonkeyPatch,
    xml_path: str,
    pipeline: str,
    owner_type: str,
    series: str,
    out: str,
    system_output: str,
) -> None:
    invoke_translate(
        monkeypatch,
        "plexos",
        "pypsa",
        pipeline,
        source_path=str(Path(xml_path)),
        step_0_owner_type=owner_type,
        step_0_series=series,
        step_0_out=out,
        sink_0_output_path=system_output,
    )


@when(
    parsers.parse(
        'I stage "{xml_path}" through "{pipeline}" dumping table "{table}" to "{out}" '
        'with system output "{system_output}"'
    )
)
def run_stage_and_dump(
    monkeypatch: pytest.MonkeyPatch,
    xml_path: str,
    pipeline: str,
    table: str,
    out: str,
    system_output: str,
) -> None:
    invoke_translate(
        monkeypatch,
        "plexos",
        "pypsa",
        pipeline,
        source_path=str(Path(xml_path)),
        step_0_table=table,
        step_0_out=out,
        sink_0_output_path=system_output,
    )


def _dump_rows(path: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = json.loads(Path(path).read_text(encoding="utf-8"))["rows"]
    return rows


def _as_float(value: object) -> float:
    assert isinstance(value, (int, float, str)), f"expected a number, got {value!r}"
    return float(value)


@then(parsers.parse('the PyPSA generator "{name}" in "{path}" has bus "{bus}"'))
def assert_generator_bus(name: str, path: str, bus: str) -> None:
    import pypsa

    network = pypsa.Network(path)
    assert name in network.generators.index, f"no generator {name!r} in {path}"
    actual = network.generators.at[name, "bus"]
    assert actual == bus, f"expected generator {name!r} on bus {bus!r} in {path}; got {actual!r}"


@then(parsers.parse('the PyPSA generator "{name}" in "{path}" has carrier "{carrier}"'))
def assert_generator_carrier(name: str, path: str, carrier: str) -> None:
    import pypsa

    network = pypsa.Network(path)
    assert name in network.generators.index, f"no generator {name!r} in {path}"
    actual = network.generators.at[name, "carrier"]
    assert actual == carrier, (
        f"expected generator {name!r} carrier {carrier!r} in {path}; got {actual!r}"
    )


@then(parsers.parse('the PyPSA generator "{name}" in "{path}" has "{column}" equal to {value:g}'))
def assert_generator_column(name: str, path: str, column: str, value: float) -> None:
    import pypsa

    network = pypsa.Network(path)
    assert name in network.generators.index, f"no generator {name!r} in {path}"
    actual = float(network.generators.at[name, column])
    assert actual == pytest.approx(value), (
        f"expected generator {name!r} {column} = {value!r} in {path}; got {actual!r}"
    )


@then(parsers.parse('the PyPSA generator "{name}" in "{path}" has no "{column}"'))
def assert_generator_column_unset(name: str, path: str, column: str) -> None:
    import pypsa

    network = pypsa.Network(path)
    assert name in network.generators.index, f"no generator {name!r} in {path}"
    actual = float(network.generators.at[name, column])
    assert math.isnan(actual), (
        f"expected generator {name!r} {column} to be unset in {path}; got {actual!r}"
    )


@then(parsers.parse('the PyPSA generator "{name}" in "{path}" is committable'))
def assert_generator_committable(name: str, path: str) -> None:
    import pypsa

    network = pypsa.Network(path)
    assert name in network.generators.index, f"no generator {name!r} in {path}"
    assert bool(network.generators.at[name, "committable"]), (
        f"expected generator {name!r} to be committable in {path}"
    )


@then(parsers.parse('the PyPSA generator "{name}" in "{path}" is not committable'))
def assert_generator_not_committable(name: str, path: str) -> None:
    import pypsa

    network = pypsa.Network(path)
    assert name in network.generators.index, f"no generator {name!r} in {path}"
    assert not bool(network.generators.at[name, "committable"]), (
        f"expected generator {name!r} not to be committable in {path}"
    )


@then(parsers.parse('the PyPSA network "{path_a}" and "{path_b}" have the same snapshots'))
def assert_same_snapshots(path_a: str, path_b: str) -> None:
    import pypsa

    snapshots_a = list(pypsa.Network(path_a).snapshots)
    snapshots_b = list(pypsa.Network(path_b).snapshots)
    assert snapshots_a, f"expected non-empty snapshots in {path_a}"
    assert snapshots_a == snapshots_b, (
        f"snapshots differ: {path_a} has {snapshots_a}, {path_b} has {snapshots_b}"
    )


@then(
    parsers.parse(
        'the PyPSA network "{ensemble_path}" and "{reference_path}" have the same generator '
        '"{name}"'
    )
)
def assert_generator_matches_reference(ensemble_path: str, reference_path: str, name: str) -> None:
    """Compare one generator's static row, and its p_max_pu series if it has one, across two
    written networks.
    """
    import pypsa

    ensemble = pypsa.Network(ensemble_path)
    reference = pypsa.Network(reference_path)
    assert name in ensemble.generators.index, f"no generator {name!r} in {ensemble_path}"
    assert name in reference.generators.index, f"no generator {name!r} in {reference_path}"
    ensemble_row = ensemble.generators.loc[name]
    reference_row = reference.generators.loc[name]
    for column in reference_row.index:
        actual, expected = ensemble_row[column], reference_row[column]
        mismatch = f"generator {name!r} {column} differs: {actual!r} vs {expected!r}"
        if isinstance(expected, float):
            both_unset = math.isnan(actual) and math.isnan(expected)
            assert both_unset or math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-9), (
                mismatch
            )
        else:
            assert actual == expected, mismatch
    _assert_same_p_max_pu_series(ensemble, reference, name)


def _assert_same_p_max_pu_series(ensemble: Any, reference: Any, name: str) -> None:
    """A generator with a time-varying rating carries a p_max_pu_t column in both networks;
    one built with no such column (a purely static generator) is not asserted empty against
    the other, since neither ever carries the series.
    """
    ensemble_has_series = name in ensemble.generators_t.p_max_pu.columns
    reference_has_series = name in reference.generators_t.p_max_pu.columns
    assert ensemble_has_series == reference_has_series, (
        f"generator {name!r} has a p_max_pu series in one network but not the other: "
        f"ensemble={ensemble_has_series}, reference={reference_has_series}"
    )
    if not ensemble_has_series:
        return
    ensemble_series = ensemble.generators_t.p_max_pu[name].to_list()
    reference_series = reference.generators_t.p_max_pu[name].to_list()
    assert ensemble_series, f"empty p_max_pu series for generator {name!r} in the ensemble network"
    assert reference_series, (
        f"empty p_max_pu series for generator {name!r} in the reference network"
    )
    assert ensemble_series == pytest.approx(reference_series), (
        f"generator {name!r} p_max_pu series differs: {ensemble_series!r} vs {reference_series!r}"
    )


@then(parsers.parse('the PyPSA network "{path}" has no generator "{name}"'))
def assert_network_has_no_generator(path: str, name: str) -> None:
    import pypsa

    network = pypsa.Network(path)
    assert name not in network.generators.index, f"unexpected generator {name!r} in {path}"


@then(
    parsers.parse(
        'the PyPSA generator "{name}" in "{path}" has p_max_pu at hour {hour:d} equal to {value:g}'
    )
)
def assert_generator_p_max_pu(name: str, path: str, hour: int, value: float) -> None:
    import pypsa

    network = pypsa.Network(path)
    series = network.generators_t.p_max_pu
    assert name in series.columns, f"no p_max_pu time series for {name!r} in {path}"
    actual = float(series[name].iloc[hour - 1])
    assert actual == pytest.approx(value), (
        f"expected {name!r} p_max_pu hour {hour} = {value!r} in {path}; got {actual!r}"
    )


@then(
    parsers.parse(
        'the PyPSA storage unit "{name}" in "{path}" has p_max_pu '
        "at hour {hour:d} equal to {value:g}"
    )
)
def assert_storage_unit_p_max_pu(name: str, path: str, hour: int, value: float) -> None:
    import pypsa

    network = pypsa.Network(path)
    series = network.storage_units_t.p_max_pu
    assert name in series.columns, f"no p_max_pu time series for {name!r} in {path}"
    actual = float(series[name].iloc[hour - 1])
    assert actual == pytest.approx(value), (
        f"expected {name!r} p_max_pu hour {hour} = {value!r} in {path}; got {actual!r}"
    )


@then(
    parsers.parse(
        'the membership dump "{path}" links "{parent}" to "{child}" in collection "{collection}"'
    )
)
def assert_membership_dump_links(path: str, parent: str, child: str, collection: str) -> None:
    rows = _dump_rows(path)
    match = [
        row
        for row in rows
        if row.get("parent_object") == parent
        and row.get("child_object") == child
        and row.get("collection") == collection
    ]
    assert match, (
        f"expected a membership {parent!r} -> {child!r} in collection {collection!r} "
        f"in {path}; got rows {rows!r}"
    )


@then(parsers.parse('the membership dump "{path}" mentions no object "{name}"'))
def assert_membership_dump_omits_object(path: str, name: str) -> None:
    rows = _dump_rows(path)
    match = [row for row in rows if name in (row.get("parent_object"), row.get("child_object"))]
    assert not match, f"expected no membership mentioning {name!r} in {path}; got {match!r}"


@then(parsers.parse('the property dump "{path}" has "{obj}" "{property_name}" = {value:g}'))
def assert_property_dump_value(path: str, obj: str, property_name: str, value: float) -> None:
    rows = _dump_rows(path)
    match = [
        row
        for row in rows
        if row.get("child_object") == obj and row.get("property") == property_name
    ]
    assert match, f"expected a property {property_name!r} on {obj!r} in {path}; got rows {rows!r}"
    values = [row["value"] for row in match]
    assert any(_as_float(v) == value for v in values), (
        f"expected {obj!r} {property_name!r} = {value!r} in {path}; got {values!r}"
    )


@then(
    parsers.parse(
        'the property dump "{path}" has "{obj}" "{property_name}" = {value:g} in band {band:d}'
    )
)
def assert_property_dump_band(
    path: str, obj: str, property_name: str, value: float, band: int
) -> None:
    bands = {
        _as_float(row["band"]): _as_float(row["value"])
        for row in _dump_rows(path)
        if row.get("child_object") == obj and row.get("property") == property_name
    }
    assert bands.get(band) == value, (
        f"expected {obj!r} {property_name!r} = {value!r} in band {band} of {path}; got {bands!r}"
    )


@then(parsers.parse('the property dump "{path}" has no data file for "{obj}" "{property_name}"'))
def assert_property_dump_without_data_file(path: str, obj: str, property_name: str) -> None:
    data_files = [
        row["data_file"]
        for row in _dump_rows(path)
        if row.get("child_object") == obj and row.get("property") == property_name
    ]
    assert data_files and not any(data_files), (
        f"expected {obj!r} {property_name!r} in {path} to carry no data file; got {data_files!r}"
    )


@then(parsers.parse('the resolved property "{path}" for "{obj}" "{property_name}" is {value:g}'))
def assert_resolved_property(path: str, obj: str, property_name: str, value: float) -> None:
    rows = _dump_rows(path)
    values = [
        row["value"]
        for row in rows
        if row.get("child_object") == obj and row.get("property") == property_name
    ]
    assert len(values) == 1, (
        f"expected exactly one resolved {property_name!r} on {obj!r} in {path}; got {values!r}"
    )
    assert _as_float(values[0]) == value, (
        f"expected resolved {obj!r} {property_name!r} = {value!r} in {path}; got {values[0]!r}"
    )


def _sorted_series(path: str, component: str) -> list[dict[str, Any]]:
    return sorted(
        (row for row in _dump_rows(path) if row.get("component") == component),
        key=lambda row: str(row["snapshot"]),
    )


@then(
    parsers.parse(
        'the load time series "{path}" for "{component}" has snapshot {index:d} at "{timestamp}"'
    )
)
def assert_time_series_snapshot(path: str, component: str, index: int, timestamp: str) -> None:
    """The snapshot a row lands on, which is what an intra-day period column has to get right."""
    series = _sorted_series(path, component)
    assert len(series) >= index, (
        f"expected at least {index} snapshots for {component!r} in {path}; got {len(series)}"
    )
    actual = str(series[index - 1]["snapshot"])
    assert actual.startswith(timestamp), (
        f"expected {component!r} snapshot {index} at {timestamp!r} in {path}; got {actual!r}"
    )


@then(
    parsers.parse('the load time series "{path}" for "{component}" at hour {hour:d} is {value:g}')
)
def assert_time_series_value(path: str, component: str, hour: int, value: float) -> None:
    series = _sorted_series(path, component)
    assert len(series) >= hour, (
        f"expected at least {hour} snapshots for {component!r} in {path}; got {len(series)}"
    )
    actual = series[hour - 1]["value"]
    assert _as_float(actual) == value, (
        f"expected {component!r} hour {hour} = {value!r} in {path}; got {actual!r}"
    )


# ---------- Extensions sidecar assertions ----------


def _sidecar_record(path: str, kind: str, name: str) -> dict[str, Any]:
    document: Any = json.loads(Path(path).read_text(encoding="utf-8"))
    for record in document.get(kind, []):
        if record["name"] == name:
            return dict(record)
    raise AssertionError(f"{kind} {name!r} not carried in {path}; got {document}")


def _reserve_record(path: str, name: str) -> dict[str, Any]:
    return _sidecar_record(path, "reserve", name)


@then(parsers.parse('the extensions sidecar "{path}" carries reserve "{name}"'))
def assert_reserve_carried(path: str, name: str) -> None:
    _reserve_record(path, name)


@then(parsers.parse('the extensions sidecar "{path}" generator "{name}" has category "{category}"'))
def assert_generator_category(path: str, name: str, category: str) -> None:
    actual = _sidecar_record(path, "generator", name)["category"]
    assert actual == category, f"expected generator {name} category {category!r}, got {actual!r}"


@then(
    parsers.parse(
        'the extensions sidecar "{path}" reserve "{name}" lists contributor "{contributor}"'
    )
)
def assert_reserve_contributor(path: str, name: str, contributor: str) -> None:
    contributors = _reserve_record(path, name)["contributing_generators"]
    assert contributor in contributors, (
        f"expected {contributor!r} among {name!r} contributors, got {contributors}"
    )


@then(parsers.parse('the extensions sidecar "{path}" reserve "{name}" requires {megawatts:g} MW'))
def assert_reserve_megawatts(path: str, name: str, megawatts: float) -> None:
    record = _reserve_record(path, name)
    actual = record.get("requirement_mw")
    assert actual is not None, f"reserve {name!r} states no megawatts in {path}"
    assert math.isclose(float(actual), megawatts, rel_tol=1e-9, abs_tol=1e-9), (
        f"expected reserve {name} to require {megawatts} MW, got {actual}"
    )
    assert record.get("requirement_series") is None, (
        f"reserve {name!r} states a scalar and a series at once: {record}"
    )


@then(
    parsers.parse(
        'the extensions sidecar "{path}" reserve "{name}" reads its requirement from "{companion}"'
    )
)
def assert_reserve_requirement_series(path: str, name: str, companion: str) -> None:
    actual = _reserve_record(path, name).get("requirement_series")
    assert actual == companion, (
        f"expected reserve {name} to read its requirement from {companion!r}, got {actual!r}"
    )


@then(
    parsers.parse('the companion parquet "{path}" states reserve "{name}" requiring {megawatts} MW')
)
def assert_companion_requirements(path: str, name: str, megawatts: str) -> None:
    expected = [float(value) for value in megawatts.split()]
    frame = pl.read_parquet(path).filter(pl.col("name") == name).sort("snapshot")
    actual = frame["requirement_mw"].to_list()
    assert len(actual) == len(expected), f"expected {expected} MW for {name!r}, got {actual}"
    for got, want in zip(actual, expected, strict=True):
        assert math.isclose(got, want, rel_tol=1e-9, abs_tol=1e-9), (
            f"expected {expected} MW for {name!r}, got {actual}"
        )


@then(
    parsers.parse('the extensions sidecar "{path}" reserve "{name}" prices a shortage at {price:g}')
)
def assert_reserve_shortage_price(path: str, name: str, price: float) -> None:
    actual = _reserve_record(path, name).get("shortage_price")
    assert actual is not None and math.isclose(float(actual), price, rel_tol=1e-9, abs_tol=1e-9), (
        f"expected reserve {name} to price a shortage at {price}, got {actual}"
    )


@then(parsers.parse('the extensions sidecar "{path}" reserve "{name}" shares headroom'))
def assert_reserve_shares_headroom(path: str, name: str) -> None:
    record = _reserve_record(path, name)
    assert record.get("is_mutually_exclusive") is True, (
        f"expected reserve {name!r} to be mutually exclusive, got {record}"
    )


@then(parsers.parse('the extensions sidecar "{path}" reserve "{name}" keeps its own headroom'))
def assert_reserve_keeps_headroom(path: str, name: str) -> None:
    record = _reserve_record(path, name)
    assert record.get("is_mutually_exclusive") is False, (
        f"expected reserve {name!r} to keep its own headroom, got {record}"
    )


@then(
    parsers.parse(
        'the extensions sidecar "{path}" reserve "{name}" is a "{direction}" reserve'
        ' of kind "{kind}"'
    )
)
def assert_reserve_type(path: str, name: str, direction: str, kind: str) -> None:
    record = _reserve_record(path, name)
    assert record.get("direction") == direction, (
        f"expected reserve {name} direction {direction!r}, got {record.get('direction')!r}"
    )
    assert record.get("kind") == kind, (
        f"expected reserve {name} kind {kind!r}, got {record.get('kind')!r}"
    )


@then(parsers.parse('the extensions sidecar "{path}" reserve "{name}" states no requirement'))
def assert_reserve_without_requirement(path: str, name: str) -> None:
    record = _reserve_record(path, name)
    stated = {
        key: record[key]
        for key in ("requirement_mw", "requirement_series")
        if record.get(key) is not None
    }
    assert not stated, f"expected no requirement for reserve {name!r}, got {stated}"


# ---------- Demand-response generator assertions ----------


@then(
    parsers.parse(
        'the demand-response generator "{name}" in "{path}" is available only in "{fractions}"'
    )
)
def assert_demand_response_window(name: str, path: str, fractions: str) -> None:
    import pypsa

    network = pypsa.Network(path)
    expected = [float(part.strip()) for part in fractions.split(",")]
    actual = network.generators_t["p_max_pu"][name].to_list()
    assert len(actual) == len(expected), (
        f"expected {len(expected)} p_max_pu snapshots for {name!r}, got {len(actual)}: {actual}"
    )
    for step, (got, want) in enumerate(zip(actual, expected, strict=True)):
        assert math.isclose(got, want, rel_tol=1e-9, abs_tol=1e-9), (
            f"p_max_pu[{step}] for {name!r} = {got}, expected {want}"
        )
