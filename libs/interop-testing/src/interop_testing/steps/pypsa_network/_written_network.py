"""Reading one component out of a network that a pipeline wrote to disk.

The Then steps in ``assert_network`` all ask the same five questions of a
written network: how many of a component there are, whether a named one is
there, what a string attribute says, what a numeric attribute is worth, and
whether a boolean flag is set. Each question is answered once here, so the
wording of a failure message and the lookup behind it cannot drift between
components.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, NamedTuple

import pandas as pd

from interop_testing.builders.pypsa_networks import read_network


class Component(NamedTuple):
    """How one PyPSA component is spelled in a step, and where its rows live."""

    plural: str
    frame: str


BUS = "bus"
GENERATOR = "generator"
LOAD = "load"
LINE = "line"
LINK = "link"
STORAGE_UNIT = "storage unit"
STORE = "store"
TRANSFORMER = "transformer"
SHUNT_IMPEDANCE = "shunt impedance"

COMPONENTS: dict[str, Component] = {
    BUS: Component("buses", "buses"),
    GENERATOR: Component("generators", "generators"),
    LOAD: Component("loads", "loads"),
    LINE: Component("lines", "lines"),
    LINK: Component("links", "links"),
    STORAGE_UNIT: Component("storage units", "storage_units"),
    STORE: Component("stores", "stores"),
    TRANSFORMER: Component("transformers", "transformers"),
    SHUNT_IMPEDANCE: Component("shunt impedances", "shunt_impedances"),
}

PLURAL_FRAMES: dict[str, str] = {
    component.plural: component.frame for component in COMPONENTS.values()
}

_RELATIVE_TOLERANCE = 1e-9
_ABSOLUTE_TOLERANCE = 1e-9


def read_frame(path: str, kind: str) -> pd.DataFrame:
    """Read the static frame holding every component of one kind."""
    return getattr(read_network(path), COMPONENTS[kind].frame)  # type: ignore[no-any-return]


def read_series_frame(path: str, kind: str, attribute: str) -> pd.DataFrame:
    """Read the time-varying frame holding one attribute of one component kind."""
    network = read_network(path)
    return getattr(network, f"{COMPONENTS[kind].frame}_t")[attribute]  # type: ignore[no-any-return]


def assert_component_count(path: str, kind: str, count: int) -> None:
    frame = read_frame(path, kind)
    assert len(frame) == count, (
        f"expected {count} {COMPONENTS[kind].plural} in {path}, "
        f"got {len(frame)}: {list(frame.index)}"
    )


def assert_no_components(path: str, plural: str) -> None:
    frame = getattr(read_network(path), PLURAL_FRAMES[plural])
    assert frame.empty, f"expected no {plural} in {path}, got {list(frame.index)}"


@dataclass(frozen=True)
class WrittenComponent:
    """One named component in a written network, addressed by its step-text word."""

    path: str
    kind: str
    name: str

    def read(self, attribute: str) -> Any:
        frame = read_frame(self.path, self.kind)
        assert self.name in frame.index, f"no {self.kind} {self.name!r} in {self.path}"
        return frame.at[self.name, attribute]

    def read_series(self, attribute: str) -> list[float]:
        column = read_series_frame(self.path, self.kind, attribute)[self.name]
        return [float(value) for value in column]

    def assert_absent(self) -> None:
        frame = read_frame(self.path, self.kind)
        assert self.name not in frame.index, f"unexpected {self.kind} {self.name!r} in {self.path}"

    def assert_label(self, attribute: str, expected: str) -> None:
        actual = self.read(attribute)
        assert actual == expected, (
            f"expected {self.kind} {self.name} {attribute} {expected!r}, got {actual!r}"
        )

    def assert_close(self, attribute: str, expected: float) -> None:
        actual = float(self.read(attribute))
        assert math.isclose(
            actual, expected, rel_tol=_RELATIVE_TOLERANCE, abs_tol=_ABSOLUTE_TOLERANCE
        ), f"expected {self.kind} {self.name} {attribute} = {expected}, got {actual}"

    def assert_flag_set(self, attribute: str) -> None:
        assert bool(self.read(attribute)), f"expected {self.kind} {self.name} {attribute} to be set"

    def assert_flag_clear(self, attribute: str) -> None:
        assert not bool(self.read(attribute)), (
            f"expected {self.kind} {self.name} {attribute} to be clear"
        )

    def assert_series(self, attribute: str, expected_values: str) -> None:
        expected = [float(value) for value in expected_values.split()]
        actual = self.read_series(attribute)
        label = f"{self.kind} {self.name} {attribute} series"
        assert len(actual) == len(expected), (
            f"expected {label} of length {len(expected)} {expected}, "
            f"got length {len(actual)} {actual}"
        )
        for actual_value, expected_value in zip(actual, expected, strict=True):
            assert math.isclose(
                actual_value,
                expected_value,
                rel_tol=_RELATIVE_TOLERANCE,
                abs_tol=_ABSOLUTE_TOLERANCE,
            ), f"expected {label} {expected}, got {actual}"

    def assert_no_series(self, attribute: str) -> None:
        frame = read_series_frame(self.path, self.kind, attribute)
        assert self.name not in frame.columns, (
            f"expected {self.kind} {self.name} to carry no {attribute} time series in {self.path}"
        )
