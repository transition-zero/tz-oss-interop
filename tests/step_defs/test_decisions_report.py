from pathlib import Path

from interop_testing import write_adapters_config, write_project_plugin
from pytest_bdd import given, parsers, scenarios

FEATURE = Path(__file__).resolve().parents[1] / "features" / "decisions_report.feature"
scenarios(str(FEATURE))


_EMIT_TEST_EVENTS_STEP_PY = """\
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


class _EmitTestEvents(TranslationStep):
    name: ClassVar[str] = "emit_test_events"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def run(self, state: State, params: BaseModel | None) -> State:
        for event in _events():
            self._recorder.append(event)
        return state


def _events() -> list[TranslationEvent]:
    return [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                SourceField(
                    framework="pypsa", component="Generator", name="gen-1",
                    attribute="p_nom", value=100.0, unit="MW",
                )
            ],
            destinations=[
                DestinationField(
                    framework="sienna", component="ThermalStandard", name="gen-1",
                    attribute="active_power_limits.max", value=1.0, unit="pu_MVA",
                )
            ],
            derivation="p_nom / base_power = 100 / 100",
        ),
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                SourceField(
                    framework="pypsa", component="Generator", name="gen-1",
                    attribute="carrier", value="coal", unit=None,
                )
            ],
            destinations=[
                DestinationField(
                    framework="sienna", component="ThermalStandard", name="gen-1",
                    attribute="prime_mover_type", value="ST", unit=None,
                ),
                DestinationField(
                    framework="sienna", component="ThermalStandard", name="gen-1",
                    attribute="fuel", value="COAL", unit=None,
                ),
            ],
            derivation="carrier_lookup[coal] = (ST, COAL)",
        ),
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                SourceField(
                    framework="pypsa", component="Bus", name="bus-1",
                    attribute="v_nom", value=380.0, unit="kV",
                ),
                SourceField(
                    framework="pypsa", component="Bus", name="bus-2",
                    attribute="v_nom", value=380.0, unit="kV",
                ),
            ],
            destinations=[
                DestinationField(
                    framework="sienna", component="Area", name="area-A",
                    attribute="aggregated_voltage", value=380.0, unit="kV",
                )
            ],
            derivation="mean(bus[area=A].v_nom)",
        ),
        TranslationEvent(
            kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
            sources=[],
            destinations=[
                DestinationField(
                    framework="sienna", component="ThermalStandard", name="gen-1",
                    attribute="must_run", value=False, unit=None,
                )
            ],
            note="ThermalStandard.must_run not present in PyPSA; using translator default",
        ),
        TranslationEvent(
            kind=EventKind.USER_CONFIG_DEFAULT_APPLIED,
            sources=[],
            destinations=[
                DestinationField(
                    framework="sienna", component="ThermalStandard", name="gen-1",
                    attribute="ramp_limits.up", value=0.5, unit="pu/min",
                )
            ],
            derivation="user config: defaults.coal.ramp_up_MW_per_min / base_power = 50 / 100",
        ),
        TranslationEvent(
            kind=EventKind.COMPONENT_SKIPPED,
            sources=[
                SourceField(
                    framework="pypsa", component="ShuntImpedance", name="shunt-1",
                    attribute=None, value=None, unit=None,
                )
            ],
            destinations=[],
            note="ShuntImpedance has no Sienna equivalent",
        ),
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                SourceField(
                    framework="pypsa", component="Generator", name="gas|peaker",
                    attribute="carrier", value="gas", unit=None,
                )
            ],
            destinations=[
                DestinationField(
                    framework="sienna", component="ThermalStandard", name="gas|peaker",
                    attribute="prime_mover_type", value="GT", unit=None,
                )
            ],
            derivation="carrier_lookup[gas] = (GT, GAS)",
        ),
    ]
"""


# Only the first and last EventKind, so the two kinds between them render as empty
# sections in the middle of the report.
_EMIT_SPARSE_EVENTS_STEP_PY = """\
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


class _EmitSparseEvents(TranslationStep):
    name: ClassVar[str] = "emit_sparse_events"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def run(self, state: State, params: BaseModel | None) -> State:
        self._recorder.append(
            TranslationEvent(
                kind=EventKind.VALUE_DERIVED,
                sources=[
                    SourceField(
                        framework="pypsa", component="Generator", name="gen-1",
                        attribute="p_nom", value=100.0, unit="MW",
                    )
                ],
                destinations=[
                    DestinationField(
                        framework="sienna", component="ThermalStandard", name="gen-1",
                        attribute="active_power_limits.max", value=1.0, unit="pu_MVA",
                    )
                ],
                derivation="p_nom / base_power = 100 / 100",
            )
        )
        self._recorder.append(
            TranslationEvent(
                kind=EventKind.COMPONENT_SKIPPED,
                sources=[
                    SourceField(
                        framework="pypsa", component="ShuntImpedance", name="shunt-1",
                        attribute=None, value=None, unit=None,
                    )
                ],
                destinations=[],
                note="ShuntImpedance has no Sienna equivalent",
            )
        )
        return state
"""


@given('a step plugin "emit_test_events" that appends a representative set of TranslationEvents')
def given_emit_test_events_step() -> None:
    write_project_plugin("steps", "emit_test_events", _EMIT_TEST_EVENTS_STEP_PY)


@given(
    'a step plugin "emit_sparse_events" that appends only a derived value and a skipped component'
)
def given_emit_sparse_events_step() -> None:
    write_project_plugin("steps", "emit_sparse_events", _EMIT_SPARSE_EVENTS_STEP_PY)


@given(parsers.re(r'adapters\.yaml binds reporter to "(?P<name>[^"]+)"$'))
def given_reporter_binding(name: str) -> None:
    write_adapters_config(f"bindings:\n  reporter: {name}\n")


@given(
    parsers.re(
        r'adapters\.yaml multi-binds reporter to "(?P<first>[^"]+)" and "(?P<second>[^"]+)"$'
    )
)
def given_reporter_multi_binding(first: str, second: str) -> None:
    write_adapters_config(f"multi_bindings:\n  reporter: [{first}, {second}]\n")
