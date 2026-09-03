from pathlib import Path
from typing import Any

import pytest
import yaml
from interop_testing import write_pipeline, write_project_plugin
from pytest_bdd import given, parsers, scenarios, then, when

from tests.step_defs.conftest import invoke_main, invoke_translate

scenarios("../features/composed_pipeline.feature")


# ---------- manifests ----------

_FRAMEWORKS_BY_PIPELINE = {
    "alpha-to-beta": ("alpha", "beta"),
    "url-alpha-to-beta": ("alpha", "beta"),
    "beta-to-gamma": ("beta", "gamma"),
    "url-beta-to-gamma": ("beta", "gamma"),
    "delta-to-gamma": ("delta", "gamma"),
    "gamma-to-epsilon": ("gamma", "epsilon"),
}

_Params = dict[str, Any]
_Entry = tuple[str, _Params]


def _write_leg(
    name: str,
    output_path: str | None,
    *,
    source_params: _Params | None = None,
    steps: tuple[str, ...] = (),
    sinks: int = 1,
    notes: bool = False,
) -> None:
    """A leg with no `source_params` takes its input path from the composed manifest,
    which is how every leg after the first is wired. An `output_path` of None leaves the
    sink's path for the composed manifest to name.
    """
    source_framework, destination_framework = _FRAMEWORKS_BY_PIPELINE[name]
    document: dict[str, Any] = {
        "source_framework": source_framework,
        "destination_framework": destination_framework,
        "source": {"name": "read_payload", **({"params": source_params} if source_params else {})},
    }
    if steps:
        document["steps"] = [{"name": step} for step in steps]
    emit_json = {"name": "emit_json"}
    if output_path is not None:
        emit_json["params"] = {"output_path": output_path}  # type: ignore[assignment]
    document["sinks"] = [dict(emit_json) for _ in range(sinks)]
    if notes:
        document["sinks"].append({"name": "emit_note"})
    write_pipeline(name, yaml.safe_dump(document, sort_keys=False))


def _write_pipeline_in_subdir(subdir: str, name: str, yaml_body: str) -> None:
    pipelines_dir = Path.cwd() / "pipelines" / subdir
    pipelines_dir.mkdir(parents=True, exist_ok=True)
    (pipelines_dir / f"{name}.yaml").write_text(yaml_body, encoding="utf-8")


def _write_composed(
    name: str,
    legs: list[_Entry],
    mappings: list[_Entry] | None = None,
    destination: str = "gamma",
) -> None:
    document: dict[str, Any] = {
        "source_framework": "alpha",
        "destination_framework": destination,
    }
    if mappings:
        document["mappings"] = [_entry(pipeline, params) for pipeline, params in mappings]
    document["compose"] = [_entry(pipeline, params) for pipeline, params in legs]
    write_pipeline(name, yaml.safe_dump(document, sort_keys=False))


def _entry(pipeline: str, params: _Params) -> dict[str, Any]:
    return {"pipeline": pipeline, "params": params} if params else {"pipeline": pipeline}


def _wiring(upstream: str) -> _Params:
    return {"read_payload.path": f"${upstream}.emit_json.output_path"}


# ---------- plugin fixtures ----------

_READ_PAYLOAD_SOURCE_PY = """\
import json
from pathlib import Path
from typing import ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import StagedSource, State
from interop.ports.outbound.filesystem import FilesystemPort, Location


class _ReadPayloadParams(BaseModel):
    path: Location


class _ReadPayload(StagedSource):
    name: ClassVar[str] = "read_payload"
    params_schema: ClassVar[type[BaseModel] | None] = _ReadPayloadParams
    prefix: ClassVar[str] = "readpayload"

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def load_into_state(self, params: BaseModel | None, staging_dir: Path) -> State:
        assert isinstance(params, _ReadPayloadParams)
        payload = json.loads(self._fs.read_bytes(params.path).decode())["payload"]
        return State(
            staging_dir=staging_dir,
            destination_tables={"payload": pl.DataFrame(payload)},
        )
"""


_NOTE_DECISION_STEP_PY = """\
from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.ports.outbound.reporting import (
    DestinationField,
    EventKind,
    SourceField,
    TranslationEvent,
)


class _NoteDecision(TranslationStep):
    name: ClassVar[str] = "note_decision"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def run(self, state: State, params: BaseModel | None) -> State:
        self._recorder.append(
            TranslationEvent(
                kind=EventKind.VALUE_DERIVED,
                sources=[SourceField(framework="alpha", component="payload", name="value")],
                destinations=[
                    DestinationField(framework="gamma", component="payload", name="value")
                ],
                derivation="carried through unchanged",
            )
        )
        return state
"""


_EMIT_NOTE_SINK_PY = """\
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import Sink, State
from interop.ports.outbound.filesystem import FilesystemPort, Location


class _EmitNoteParams(BaseModel):
    output_path: Location = Path("outputs/note.json")


class _EmitNote(Sink):
    name: ClassVar[str] = "emit_note"
    params_schema: ClassVar[type[BaseModel] | None] = _EmitNoteParams

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def write(self, state: State, params: BaseModel | None) -> None:
        assert isinstance(params, _EmitNoteParams)
        self._fs.write_bytes(params.output_path, b'{"note": "written"}')
"""


_OBJECT_MAPPINGS_SOURCE_PY = """\
from pathlib import Path
from typing import ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import StagedSource, State
from interop.core.user_mappings import UserMappings
from interop.ports.outbound.filesystem import FilesystemPort, Location


class ObjectMappings(UserMappings):
    objects: list[dict[str, str]] = []


class _StageObjectMappingsParams(BaseModel):
    # Set only when the composed manifest points this at the model the first leg reads.
    model_path: Location | None = None


class _StageObjectMappings(StagedSource):
    name: ClassVar[str] = "stage_object_mappings"
    params_schema: ClassVar[type[BaseModel] | None] = _StageObjectMappingsParams
    prefix: ClassVar[str] = "objectmappings"

    def __init__(self, fs: FilesystemPort, object_mappings: ObjectMappings) -> None:
        self._fs = fs
        self._object_mappings = object_mappings

    def load_into_state(self, params: BaseModel | None, staging_dir: Path) -> State:
        assert isinstance(params, _StageObjectMappingsParams)
        if params.model_path is not None:
            self._fs.read_bytes(params.model_path)
        return State(
            staging_dir=staging_dir,
            destination_tables={"objects": pl.DataFrame(self._object_mappings.objects)},
        )
"""


_EMIT_CARRIER_MAPPINGS_SINK_PY = """\
from typing import ClassVar

import yaml
from pydantic import BaseModel

from interop.core.pipeline import Sink, State
from interop.core.user_mappings import UserMappingsOutput
from interop.plugins.shared.pypsa_sienna_user_mappings import CarrierMappings
from interop.ports.outbound.filesystem import FilesystemPort, Location


class _EmitCarrierMappingsParams(BaseModel):
    output_path: Location


class _EmitCarrierMappings(Sink):
    name: ClassVar[str] = "emit_fixture_carriers"
    params_schema: ClassVar[type[BaseModel] | None] = _EmitCarrierMappingsParams
    writes_user_mappings: ClassVar[UserMappingsOutput | None] = UserMappingsOutput(
        schema=CarrierMappings, path_param="output_path"
    )

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def write(self, state: State, params: BaseModel | None) -> None:
        assert isinstance(params, _EmitCarrierMappingsParams)
        carriers = [
            {
                "pypsa_carrier": row["carrier"],
                "sienna_component_type": "ThermalStandard",
                "sienna_fuel_type": "NATURAL_GAS",
                "sienna_prime_mover_type": "CC",
            }
            for row in state.destination_tables["objects"].to_dicts()
        ]
        document = yaml.safe_dump({"carriers": carriers}, sort_keys=False)
        self._fs.write_bytes(params.output_path, document.encode())
"""


_REPORT_CARRIERS_STEP_PY = """\
from typing import ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep
from interop.plugins.shared.pypsa_sienna_user_mappings import CarrierMappings


class _ReportCarriers(TranslationStep):
    name: ClassVar[str] = "report_carriers"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, carrier_mappings: CarrierMappings) -> None:
        self._carrier_mappings = carrier_mappings

    def run(self, state: State, params: BaseModel | None) -> State:
        state.destination_tables["carriers"] = pl.DataFrame(
            {"carrier": sorted(self._carrier_mappings.get_carriers())}
        )
        return state
"""


_NEEDS_CARRIERS_SOURCE_PY = """\
import json
from pathlib import Path
from typing import ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import StagedSource, State
from interop.plugins.shared.pypsa_sienna_user_mappings import CarrierMappings
from interop.ports.outbound.filesystem import FilesystemPort, Location


class _NeedsCarriersParams(BaseModel):
    path: Location


class _NeedsCarriers(StagedSource):
    name: ClassVar[str] = "needs_carriers_source"
    params_schema: ClassVar[type[BaseModel] | None] = _NeedsCarriersParams
    prefix: ClassVar[str] = "needscarriers"

    def __init__(self, fs: FilesystemPort, carrier_mappings: CarrierMappings) -> None:
        self._fs = fs
        self._carrier_mappings = carrier_mappings

    def load_into_state(self, params: BaseModel | None, staging_dir: Path) -> State:
        assert isinstance(params, _NeedsCarriersParams)
        payload = json.loads(self._fs.read_bytes(params.path).decode())["payload"]
        return State(staging_dir=staging_dir, destination_tables={"payload": pl.DataFrame(payload)})
"""


_NEEDS_TWO_KINDS_SOURCE_PY = """\
import json
from pathlib import Path
from typing import ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import StagedSource, State
from interop.core.user_mappings import UserMappings
from interop.plugins.shared.pypsa_sienna_user_mappings import CarrierMappings
from interop.ports.outbound.filesystem import FilesystemPort, Location


# No mapping pipeline writes this one, so it stays the user's to supply.
class RegionMappings(UserMappings):
    regions: list[str] = []


class _NeedsTwoKindsParams(BaseModel):
    path: Location


class _NeedsTwoKinds(StagedSource):
    name: ClassVar[str] = "needs_two_kinds_source"
    params_schema: ClassVar[type[BaseModel] | None] = _NeedsTwoKindsParams
    prefix: ClassVar[str] = "needstwokinds"

    def __init__(
        self,
        fs: FilesystemPort,
        carrier_mappings: CarrierMappings,
        region_mappings: RegionMappings,
    ) -> None:
        self._fs = fs

    def load_into_state(self, params: BaseModel | None, staging_dir: Path) -> State:
        assert isinstance(params, _NeedsTwoKindsParams)
        payload = json.loads(self._fs.read_bytes(params.path).decode())["payload"]
        return State(staging_dir=staging_dir, destination_tables={"payload": pl.DataFrame(payload)})
"""


_EMIT_LATE_CARRIERS_SINK_PY = """\
from typing import ClassVar

import yaml
from pydantic import BaseModel

from interop.core.pipeline import Sink, State
from interop.core.user_mappings import UserMappingsOutput
from interop.plugins.shared.pypsa_sienna_user_mappings import CarrierMappings
from interop.ports.outbound.filesystem import FilesystemPort, Location


class _EmitLateCarriersParams(BaseModel):
    output_path: Location


class _EmitLateCarriers(Sink):
    name: ClassVar[str] = "emit_late_carriers"
    params_schema: ClassVar[type[BaseModel] | None] = _EmitLateCarriersParams
    writes_user_mappings: ClassVar[UserMappingsOutput | None] = UserMappingsOutput(
        schema=CarrierMappings, path_param="output_path"
    )

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def write(self, state: State, params: BaseModel | None) -> None:
        assert isinstance(params, _EmitLateCarriersParams)
        carriers = [
            {
                "pypsa_carrier": "derived_late",
                "sienna_component_type": "ThermalStandard",
                "sienna_fuel_type": "NATURAL_GAS",
                "sienna_prime_mover_type": "CC",
            }
        ]
        document = yaml.safe_dump({"carriers": carriers}, sort_keys=False)
        self._fs.write_bytes(params.output_path, document.encode())
"""


_MAPPING_PIPELINE = """\
source_framework: object_mappings
destination_framework: user_mappings
source:
  name: stage_object_mappings
sinks:
  - name: emit_fixture_carriers
    params:
      output_path: derived/carrier_mappings.yaml
"""


# ---------- given: fixtures on disk ----------


@given(parsers.parse('a payload file "{path}" carrying "{value}"'))
def given_payload_file(path: str, value: str) -> None:
    document = Path(path)
    document.parent.mkdir(parents=True, exist_ok=True)
    document.write_text(f'{{"payload": [{{"value": "{value}"}}]}}', encoding="utf-8")


@given(parsers.parse('an http payload at "{url}" carrying "{value}"'))
def given_http_payload(http_store: dict[str, bytes], url: str, value: str) -> None:
    http_store[url] = f'{{"payload": [{{"value": "{value}"}}]}}'.encode()


@given('a source plugin "read_payload" reading a payload file')
def given_read_payload_source() -> None:
    write_project_plugin("sources", "read_payload", _READ_PAYLOAD_SOURCE_PY)


@given('a step plugin "note_decision" recording one decision')
def given_note_decision_step() -> None:
    write_project_plugin("steps", "note_decision", _NOTE_DECISION_STEP_PY)


@given('a sink plugin "emit_note" writing to a path only it knows')
def given_emit_note_sink() -> None:
    write_project_plugin("sinks", "emit_note", _EMIT_NOTE_SINK_PY)


@given('a step plugin "report_carriers" recording the carriers it was given')
def given_report_carriers_step() -> None:
    write_project_plugin("steps", "report_carriers", _REPORT_CARRIERS_STEP_PY)


@given(parsers.parse('a mapping pipeline "{name}" turning object mappings into carrier mappings'))
def given_mapping_pipeline(name: str) -> None:
    write_project_plugin("sources", "stage_object_mappings", _OBJECT_MAPPINGS_SOURCE_PY)
    write_project_plugin("sinks", "emit_fixture_carriers", _EMIT_CARRIER_MAPPINGS_SINK_PY)
    _write_pipeline_in_subdir("mappings", name, _MAPPING_PIPELINE)


@given(
    parsers.parse('an http object mappings file at "{url}" naming "{plexos_object}" as "{carrier}"')
)
def given_http_object_mappings(
    http_store: dict[str, bytes], url: str, plexos_object: str, carrier: str
) -> None:
    http_store[url] = f"objects:\n  - name: {plexos_object}\n    carrier: {carrier}\n".encode()


@given(parsers.parse('a carrier mappings file "{path}" naming "{carrier}"'))
def given_carrier_mappings_file(path: str, carrier: str) -> None:
    document = Path(path)
    document.parent.mkdir(parents=True, exist_ok=True)
    document.write_text(
        yaml.safe_dump(
            {
                "carriers": [
                    {
                        "pypsa_carrier": carrier,
                        "sienna_component_type": "ThermalStandard",
                        "sienna_fuel_type": "NATURAL_GAS",
                        "sienna_prime_mover_type": "CC",
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


@given(parsers.parse('an object mappings file "{path}" naming "{plexos_object}" as "{carrier}"'))
def given_object_mappings_file(path: str, plexos_object: str, carrier: str) -> None:
    document = Path(path)
    document.parent.mkdir(parents=True, exist_ok=True)
    document.write_text(
        f"objects:\n  - name: {plexos_object}\n    carrier: {carrier}\n", encoding="utf-8"
    )


# ---------- given: leg manifests ----------


@given(parsers.parse('a pipeline "{name}" reading "{input_path}" and writing to "{output_path}"'))
def given_leg_reading_a_file(name: str, input_path: str, output_path: str) -> None:
    _write_leg(name, output_path, source_params={"path": input_path}, steps=("note_decision",))


@given(parsers.parse('a pipeline "{name}" reading a referenced file and writing to "{output}"'))
def given_leg_reading_a_reference(name: str, output: str) -> None:
    _write_leg(name, output, steps=("note_decision",))


@given(parsers.parse('a pipeline "{name}" reporting carriers and writing to "{output}"'))
def given_leg_reporting_carriers(name: str, output: str) -> None:
    _write_leg(name, output, steps=("report_carriers",))


@given(parsers.parse('a pipeline "{name}" reading "{input_path}" and also writing a note'))
def given_leg_writing_a_note(name: str, input_path: str) -> None:
    _write_leg(
        name,
        "outputs/interim.json",
        source_params={"path": input_path},
        steps=("note_decision",),
        notes=True,
    )


@given(parsers.parse('a pipeline "{name}" reading a referenced file and also writing a note'))
def given_referencing_leg_writing_a_note(name: str) -> None:
    _write_leg(name, "outputs/final.json", steps=("note_decision",), notes=True)


@given(parsers.parse('a pipeline "{name}" reading "{input_path}" and naming no output path'))
def given_leg_naming_no_output(name: str, input_path: str) -> None:
    _write_leg(name, None, source_params={"path": input_path}, steps=("note_decision",))


@given(parsers.parse('a pipeline "{name}" whose source consumes carriers, reading "{input_path}"'))
def given_leg_whose_source_needs_carriers(name: str, input_path: str) -> None:
    write_project_plugin("sources", "needs_carriers_source", _NEEDS_CARRIERS_SOURCE_PY)
    _write_source_leg(name, "needs_carriers_source", input_path)


def _write_source_leg(name: str, source: str, input_path: str) -> None:
    source_framework, destination_framework = _FRAMEWORKS_BY_PIPELINE[name]
    document = {
        "source_framework": source_framework,
        "destination_framework": destination_framework,
        "source": {"name": source, "params": {"path": input_path}},
        "sinks": [{"name": "emit_json", "params": {"output_path": "outputs/interim.json"}}],
    }
    write_pipeline(name, yaml.safe_dump(document, sort_keys=False))


@given(
    parsers.parse(
        'a pipeline "{name}" whose source consumes carriers and one other kind, '
        'reading "{input_path}"'
    )
)
def given_leg_whose_source_needs_two_kinds(name: str, input_path: str) -> None:
    write_project_plugin("sources", "needs_two_kinds_source", _NEEDS_TWO_KINDS_SOURCE_PY)
    _write_source_leg(name, "needs_two_kinds_source", input_path)


@given(parsers.parse('a pipeline "{name}" reading "{input_path}" and reporting carriers'))
def given_first_leg_reporting_carriers(name: str, input_path: str) -> None:
    _write_leg(
        name, "outputs/interim.json", source_params={"path": input_path}, steps=("report_carriers",)
    )


@given(parsers.parse('a pipeline "{name}" deriving carriers and writing to "{output}"'))
def given_leg_deriving_carriers(name: str, output: str) -> None:
    write_project_plugin("sinks", "emit_late_carriers", _EMIT_LATE_CARRIERS_SINK_PY)
    source_framework, destination_framework = _FRAMEWORKS_BY_PIPELINE[name]
    document = {
        "source_framework": source_framework,
        "destination_framework": destination_framework,
        "source": {"name": "read_payload"},
        "sinks": [
            {"name": "emit_json", "params": {"output_path": output}},
            {"name": "emit_late_carriers", "params": {"output_path": "derived/late.yaml"}},
        ],
    }
    write_pipeline(name, yaml.safe_dump(document, sort_keys=False))


@given(parsers.parse('a pipeline "{name}" deriving carriers twice'))
def given_leg_deriving_carriers_twice(name: str) -> None:
    write_project_plugin("sinks", "emit_late_carriers", _EMIT_LATE_CARRIERS_SINK_PY)
    source_framework, destination_framework = _FRAMEWORKS_BY_PIPELINE[name]
    document = {
        "source_framework": source_framework,
        "destination_framework": destination_framework,
        "source": {"name": "read_payload", "params": {"path": "inputs/source.json"}},
        "sinks": [
            {"name": "emit_late_carriers", "params": {"output_path": "derived/first.yaml"}},
            {"name": "emit_late_carriers", "params": {"output_path": "derived/second.yaml"}},
        ],
    }
    write_pipeline(name, yaml.safe_dump(document, sort_keys=False))


@given(parsers.parse('a pipeline "{name}" with two "emit_json" sinks'))
def given_leg_with_duplicate_sinks(name: str) -> None:
    _write_leg(name, "outputs/interim.json", source_params={"path": "inputs/source.json"}, sinks=2)


# ---------- given: composed manifests ----------


@given(parsers.parse('a composed pipeline "{name}" chaining "{first}" then "{second}"'))
def given_composed_pipeline(name: str, first: str, second: str) -> None:
    _write_composed(name, [(first, {}), (second, _wiring(first))])


@given(
    parsers.parse(
        'a composed pipeline "{name}" chaining "{first}" then "{second}" handing over "{handoff}"'
    )
)
def given_composed_pipeline_naming_the_handoff(
    name: str, first: str, second: str, handoff: str
) -> None:
    _write_composed(
        name,
        [(first, {"emit_json.output_path": handoff}), (second, _wiring(first))],
    )


@given(parsers.parse('a composed pipeline "{name}" chaining three legs that each write a note'))
def given_three_leg_composed_writing_notes(name: str) -> None:
    _write_leg(
        "alpha-to-beta",
        "outputs/interim.json",
        source_params={"path": "inputs/source.json"},
        steps=("note_decision",),
        notes=True,
    )
    _write_leg("beta-to-gamma", "outputs/second.json", steps=("note_decision",), notes=True)
    _write_leg("gamma-to-epsilon", "outputs/final.json", steps=("note_decision",))
    _write_composed(
        name,
        [
            ("alpha-to-beta", {}),
            ("beta-to-gamma", _wiring("alpha-to-beta")),
            ("gamma-to-epsilon", _wiring("beta-to-gamma")),
        ],
        destination="epsilon",
    )


@given(
    parsers.parse(
        'a composed pipeline "{name}" chaining "{first}" then "{second}" '
        'wiring "{key}" to "{value}"'
    )
)
def given_composed_pipeline_wired(name: str, first: str, second: str, key: str, value: str) -> None:
    _write_composed(name, [(first, {}), (second, {key: value})])


@given(
    parsers.parse('a composed pipeline "{name}" chaining "{first}" then "{second}" with no wiring')
)
def given_composed_pipeline_unwired(name: str, first: str, second: str) -> None:
    _write_composed(name, [(first, {}), (second, {})])


@given(
    parsers.parse(
        'a composed pipeline "{name}" chaining "{first}" then "{second}" '
        "where each leg reads the other's input"
    )
)
def given_composed_pipeline_with_a_cycle(name: str, first: str, second: str) -> None:
    _write_composed(
        name,
        [
            (first, {"read_payload.path": f"${second}.read_payload.path"}),
            (second, {"read_payload.path": f"${first}.read_payload.path"}),
        ],
    )


@given(
    parsers.parse(
        'a composed pipeline "{name}" with mappings "{mapping}" chaining "{first}" then "{second}"'
    )
)
def given_composed_pipeline_with_mappings(name: str, mapping: str, first: str, second: str) -> None:
    _write_composed(name, [(first, {}), (second, _wiring(first))], mappings=[(mapping, {})])


@given(
    parsers.parse(
        'a composed pipeline "{name}" with mappings "{mapping}" reading the model that "{first}" '
        'reads, then chaining it to "{second}"'
    )
)
def given_composed_pipeline_with_mappings_reading_model(
    name: str, mapping: str, first: str, second: str
) -> None:
    reads_the_model = {"stage_object_mappings.model_path": f"${first}.read_payload.path"}
    _write_composed(
        name,
        [(first, {}), (second, _wiring(first))],
        mappings=[(mapping, reads_the_model)],
    )


# ---------- when ----------


@when(
    parsers.parse('I run translate pipeline "{pipeline}" with user mappings "{user_mappings_path}"')
)
def run_translate_with_user_mappings(
    monkeypatch: pytest.MonkeyPatch, pipeline: str, user_mappings_path: str
) -> None:
    invoke_translate(monkeypatch, "alpha", "gamma", pipeline, user_mappings_path=user_mappings_path)


@when(parsers.parse('I run translate headlessly with pipeline "{pipeline}" keeping staging'))
def run_translate_keeping_staging(monkeypatch: pytest.MonkeyPatch, pipeline: str) -> None:
    invoke_main(monkeypatch, ["headless_cli", "--pipeline", pipeline, "--keep-staging"])


@when(parsers.parse('I run translate headlessly with pipeline "{pipeline}"'))
def run_translate_headlessly(monkeypatch: pytest.MonkeyPatch, pipeline: str) -> None:
    invoke_main(monkeypatch, ["headless_cli", "--pipeline", pipeline])


@when(
    parsers.parse('I run translate headlessly with pipeline "{pipeline}" overriding "{override}"')
)
def run_translate_headlessly_with_override(
    monkeypatch: pytest.MonkeyPatch, pipeline: str, override: str
) -> None:
    invoke_main(monkeypatch, ["headless_cli", "--pipeline", pipeline, "--override", override])


# ---------- then ----------


@then("the user was not asked for a mappings file")
def assert_not_asked_for_mappings(path_prompts: list[str]) -> None:
    asked = [prompt for prompt in path_prompts if prompt.startswith("User mappings file?")]
    assert not asked, f"expected no user-mappings prompt, got {asked}"


@then("the user was asked for a mappings file exactly once")
def assert_asked_for_mappings_once(path_prompts: list[str]) -> None:
    asked = [prompt for prompt in path_prompts if prompt.startswith("User mappings file?")]
    assert len(asked) == 1, f"expected one user-mappings prompt, got {asked}"


@then(parsers.parse('the http destination "{url}" contains "{expected}"'))
def assert_http_destination_contains(http_store: dict[str, bytes], url: str, expected: str) -> None:
    assert url in http_store, f"expected {url!r} in the stubbed store, got {list(http_store)!r}"
    actual = http_store[url].decode()
    assert expected in actual, f"expected {expected!r} at {url}, got {actual!r}"


@then(parsers.parse('the http filesystem was never given the hand-off file "{filename}"'))
def assert_handoff_stayed_local(http_store: dict[str, bytes], filename: str) -> None:
    """The reports do travel through the configured filesystem; the hand-off must not."""
    reached_http = [key for key in http_store if key.endswith(filename)]
    assert not reached_http, (
        f"the configured http filesystem was handed the interior hand-off: {reached_http}"
    )
