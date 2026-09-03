from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from interop.ports.errors import UserInputError

_YAML_KEYS = {"bindings", "multi_bindings", "adapters", "observability"}
_MULTI_BINDING_KEYS = frozenset({"reporter"})


class AdaptersConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    bindings: dict[str, str] = Field(default_factory=dict)
    # Held separate from `bindings` so the common single-value case stays
    # strongly typed. The DI layer fans out the resulting adapters internally
    # (via MultiReport for `reporter`).
    multi_bindings: dict[str, list[str]] = Field(default_factory=dict)
    adapter_configs: dict[str, dict[str, Any]] = Field(default_factory=dict)
    log_level: str = "INFO"

    @model_validator(mode="before")
    @classmethod
    def _from_yaml(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        unknown = set(data) - _YAML_KEYS
        if unknown:
            raise ValueError(f"unknown top-level adapters.yaml key(s): {sorted(unknown)}")
        return {
            "bindings": data.get("bindings", {}),
            "multi_bindings": data.get("multi_bindings", {}),
            "adapter_configs": data.get("adapters", {}),
            "log_level": data.get("observability", {}).get("log_level", "INFO"),
        }

    @model_validator(mode="after")
    def _check_multi_binding_keys(self) -> AdaptersConfig:
        unsupported = set(self.multi_bindings) - _MULTI_BINDING_KEYS
        if unsupported:
            raise ValueError(
                f"multi_bindings only supports {sorted(_MULTI_BINDING_KEYS)}; "
                f"got unsupported key(s): {sorted(unsupported)}"
            )
        return self


class AdaptersConfigError(UserInputError, ValueError):
    def __init__(self, path: Path, original: ValidationError) -> None:
        super().__init__(f"adapters.yaml at {path} is invalid:\n{original}")
        self.path = path
        self.original = original


class MissingAdaptersConfigError(UserInputError, FileNotFoundError):
    def __init__(self, path: Path) -> None:
        super().__init__(
            f"adapters.yaml not found at {path}. Run `interop init <dir>` to scaffold a project."
        )
        self.path = path


class MalformedAdaptersYamlError(UserInputError, ValueError):
    def __init__(self, path: Path, original: yaml.YAMLError) -> None:
        super().__init__(f"adapters.yaml at {path} is not valid YAML:\n{original}")
        self.path = path
        self.original = original


def load_adapters_config(project_root: Path | None = None) -> AdaptersConfig:
    root = project_root or Path.cwd()
    path = root / "adapters.yaml"
    if not path.is_file():
        raise MissingAdaptersConfigError(path)
    try:
        parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise MalformedAdaptersYamlError(path, exc) from exc
    data = parsed if parsed is not None else {}
    try:
        return AdaptersConfig.model_validate(data)
    except ValidationError as exc:
        raise AdaptersConfigError(path, exc) from exc
