"""Build an OSeMOSYS model in the otoole CSV format: a config YAML and a directory of CSV files."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

import yaml

VALUE_COLUMN = "VALUE"
_CSV_SUFFIX = ".csv"
_RESULT_CELL = "1"


@dataclass(frozen=True)
class OtooleParameter:
    """One declared parameter; its CSV file takes the ``short_name`` when it has one."""

    name: str
    key: list[str]
    default: float
    rows: list[list[str]]
    short_name: str | None = None
    has_file: bool = True
    header: list[str] | None = None

    @property
    def file_stem(self) -> str:
        return self.short_name or self.name

    @property
    def columns(self) -> list[str]:
        return self.header if self.header is not None else [*self.key, VALUE_COLUMN]


@dataclass
class OtooleModelBuilder:
    """Collects the sets, parameters and results of one model, then writes them at once."""

    sets: dict[str, list[str]] = field(default_factory=dict)
    parameters: dict[str, OtooleParameter] = field(default_factory=dict)
    results: dict[str, list[str]] = field(default_factory=dict)

    def add_set(self, name: str, members: list[str]) -> None:
        self.sets[name] = members

    def add_parameter(
        self,
        name: str,
        key: list[str],
        default: float,
        rows: list[list[str]],
        *,
        short_name: str | None = None,
        has_file: bool = True,
        header: list[str] | None = None,
    ) -> None:
        self.parameters[name] = OtooleParameter(
            name, key, default, rows, short_name, has_file, header
        )

    def add_result(self, name: str, key: list[str]) -> None:
        self.results[name] = key

    def set_short_name(self, name: str, short_name: str) -> None:
        self.parameters[name] = replace(self.parameters[name], short_name=short_name)

    def set_header(self, name: str, header: list[str]) -> None:
        self.parameters[name] = replace(self.parameters[name], header=header)

    def write(self, config_path: Path, csv_dir: Path) -> None:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        csv_dir.mkdir(parents=True, exist_ok=True)
        config_path.write_text(yaml.safe_dump(self._build_config()), encoding="utf-8")
        for name, members in self.sets.items():
            _write_csv(csv_dir / f"{name}{_CSV_SUFFIX}", [VALUE_COLUMN], [[m] for m in members])
        for parameter in self.parameters.values():
            if parameter.has_file:
                csv_path = csv_dir / f"{parameter.file_stem}{_CSV_SUFFIX}"
                _write_csv(csv_path, parameter.columns, parameter.rows)
        for name, key in self.results.items():
            _write_csv(
                csv_dir / f"{name}{_CSV_SUFFIX}",
                [*key, VALUE_COLUMN],
                [[_RESULT_CELL] * (len(key) + 1)],
            )

    def _build_config(self) -> dict[str, dict[str, object]]:
        config: dict[str, dict[str, object]] = {
            name: {"type": "set", "dtype": "str"} for name in self.sets
        }
        for parameter in self.parameters.values():
            config[parameter.name] = _build_parameter_entry(parameter)
        for name, key in self.results.items():
            config[name] = {"type": "result", "indices": key, "dtype": "float", "default": 0}
        return config


def _build_parameter_entry(parameter: OtooleParameter) -> dict[str, object]:
    entry: dict[str, object] = {
        "type": "param",
        "indices": parameter.key,
        "dtype": "float",
        "default": parameter.default,
    }
    if parameter.short_name is not None:
        entry["short_name"] = parameter.short_name
    return entry


def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    lines = [",".join(header), *(",".join(row) for row in rows)]
    path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
