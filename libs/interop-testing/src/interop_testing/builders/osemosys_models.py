"""Builds a synthetic OSeMOSYS model in the otoole CSV form, and writes it.

An OSeMOSYS model reaches a translator as a folder of CSVs plus the config YAML that declares
them. The builder holds both and writes them together on save, so one fixture states what the
model declares and what it holds.

``save`` puts the config beside the data folder rather than inside it, which is where a real
model puts it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NamedTuple

import yaml

VALUE_COLUMN = "VALUE"
"""The last column of every otoole CSV, and the only column of a set CSV."""

DATA_SUBDIR = "CSVFiles"
"""The folder ``save`` writes the CSVs into, under the directory it is given."""

CONFIG_FILE = "config.yaml"
"""The config ``save`` writes beside the data folder."""

_CSV_SUFFIX = ".csv"


@dataclass(frozen=True)
class ParameterSpec:
    """What the config declares about one parameter or one result variable."""

    name: str
    indices: tuple[str, ...]
    dtype: str = "float"
    default: float = 0.0
    short_name: str | None = None


class _PendingCsv(NamedTuple):
    """One CSV the model states but has not written yet."""

    columns: list[str]
    rows: list[Sequence[object]]


@dataclass
class OsemosysModelBuilder:
    """Incrementally builds an OSeMOSYS model and writes its folder and config once."""

    _declared: dict[str, dict[str, Any]] = field(default_factory=dict)
    _pending: dict[str, _PendingCsv] = field(default_factory=dict)
    _file_names: dict[str, str] = field(default_factory=dict)
    _saved: bool = False

    def add_set(self, name: str, members: Sequence[object]) -> None:
        """Declare a set and hold its CSV. The members give the data type."""
        self._check_not_saved(f"set {name!r}")
        self._declare(name, {"dtype": _dtype_of(members), "type": "set"})
        self._hold_csv(name, [VALUE_COLUMN], [[member] for member in members])

    def add_parameter(self, spec: ParameterSpec, rows: Sequence[Sequence[object]]) -> None:
        """Declare a parameter and hold its CSV. A row is the index values, then the value."""
        self._check_not_saved(f"parameter {spec.name!r}")
        self._declare(spec.name, _body(spec, "param"))
        self._hold_csv(spec.name, [*spec.indices, VALUE_COLUMN], rows)

    def add_result(self, spec: ParameterSpec, rows: Sequence[Sequence[object]]) -> None:
        """Declare a result variable and hold its CSV, which names a solve output."""
        self._check_not_saved(f"result {spec.name!r}")
        self._declare(spec.name, _body(spec, "result"))
        self._hold_csv(spec.name, [*spec.indices, VALUE_COLUMN], rows)

    def omit_parameter_file(self, name: str) -> None:
        """Keep the config declaration and drop the CSV, so the folder does not hold it."""
        self._check_not_saved(f"the omission of {name!r}")
        del self._pending[name]

    def file_parameter_under_short_name(self, name: str) -> None:
        """File the CSV under the short name the config gives, as a model built for GLPK does."""
        self._check_not_saved(f"the short name of {name!r}")
        short_name = self._declared[name].get("short_name")
        if short_name is None:
            raise ValueError(f"parameter {name!r} declares no short_name")
        self._file_names[name] = f"{short_name}{_CSV_SUFFIX}"

    def save(self, directory: Path) -> None:
        """Write the data folder and the config beside it."""
        if self._saved:
            raise RuntimeError("Model already saved.")
        data_dir = directory / DATA_SUBDIR
        data_dir.mkdir(parents=True, exist_ok=True)
        for name, pending in self._pending.items():
            (data_dir / self._file_names[name]).write_text(_csv_text(pending), encoding="utf-8")
        config = yaml.safe_dump(self._declared, sort_keys=False)
        (directory / CONFIG_FILE).write_text(config, encoding="utf-8")
        self._saved = True

    def _declare(self, name: str, body: dict[str, Any]) -> None:
        self._declared[name] = body

    def _hold_csv(self, name: str, columns: list[str], rows: Sequence[Sequence[object]]) -> None:
        self._pending[name] = _PendingCsv(columns, [list(row) for row in rows])
        self._file_names[name] = f"{name}{_CSV_SUFFIX}"

    def _check_not_saved(self, component_desc: str) -> None:
        if self._saved:
            raise RuntimeError(f"Cannot add {component_desc}: model already saved.")


def _body(spec: ParameterSpec, entry_type: str) -> dict[str, Any]:
    body: dict[str, Any] = {
        "indices": list(spec.indices),
        "type": entry_type,
        "dtype": spec.dtype,
        "default": spec.default,
    }
    if spec.short_name is not None:
        body["short_name"] = spec.short_name
    return body


def _dtype_of(members: Sequence[object]) -> str:
    """``int`` where every member is a whole number, and ``str`` otherwise."""
    return "int" if all(str(member).lstrip("-").isdigit() for member in members) else "str"


def _csv_text(pending: _PendingCsv) -> str:
    lines = [",".join(pending.columns)]
    lines.extend(",".join(str(value) for value in row) for row in pending.rows)
    return "\n".join(lines) + "\n"
