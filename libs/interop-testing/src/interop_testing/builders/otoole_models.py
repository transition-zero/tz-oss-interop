from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

import yaml

VALUE_COLUMN = "VALUE"
_CSV_SUFFIX = ".csv"
_RESULT_CELL = "1"
_PADDING = " "


@dataclass(frozen=True)
class OtooleSet:
    """One declared set; ``is_padded`` writes a space before and after each member."""

    members: list[str]
    has_file: bool = True
    is_padded: bool = False

    @property
    def rows(self) -> list[list[str]]:
        padding = _PADDING if self.is_padded else ""
        return [[f"{padding}{member}{padding}"] for member in self.members]


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
    sets: dict[str, OtooleSet] = field(default_factory=dict)
    parameters: dict[str, OtooleParameter] = field(default_factory=dict)
    results: dict[str, list[str]] = field(default_factory=dict)

    def set_members(self, name: str, members: list[str], *, has_file: bool = True) -> None:
        self.sets[name] = OtooleSet(members, has_file)

    def set_member_padding(self, name: str) -> None:
        self.sets[name] = replace(self.sets[name], is_padded=True)

    def set_parameter(
        self,
        name: str,
        key: list[str],
        default: float,
        rows: list[list[str]],
        *,
        has_file: bool = True,
    ) -> None:
        self.parameters[name] = OtooleParameter(name, key, default, rows, has_file=has_file)

    def set_result(self, name: str, key: list[str]) -> None:
        self.results[name] = key

    def set_short_name(self, name: str, short_name: str) -> None:
        self.parameters[name] = replace(self.parameters[name], short_name=short_name)

    def set_header(self, name: str, header: list[str]) -> None:
        self.parameters[name] = replace(self.parameters[name], header=header)

    def write(self, config_path: Path, csv_dir: Path) -> None:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        csv_dir.mkdir(parents=True, exist_ok=True)
        config_path.write_text(yaml.safe_dump(self._build_config()), encoding="utf-8")
        for name, otoole_set in self.sets.items():
            if otoole_set.has_file:
                _write_csv(csv_dir / f"{name}{_CSV_SUFFIX}", [VALUE_COLUMN], otoole_set.rows)
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
