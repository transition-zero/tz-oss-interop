from __future__ import annotations

import types
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, get_args, get_origin

import questionary
from pydantic import BaseModel
from pydantic.fields import FieldInfo
from pydantic.types import PathType

from interop.ports.outbound.filesystem import (
    InputDirectoryMarker,
    InputFileMarker,
    OutputDirectoryMarker,
)

PATH_PROMPT_HINT = "(Tab to list files)"


def _annotation_includes_path(annotation: Any) -> bool:
    if annotation is Path:
        return True
    origin = get_origin(annotation)
    if origin is Annotated:
        return _annotation_includes_path(get_args(annotation)[0])
    if origin is types.UnionType or str(origin) == "typing.Union":
        return any(_annotation_includes_path(arg) for arg in get_args(annotation))
    return False


def _path_markers(field_info: FieldInfo) -> list[Any]:
    """Every annotation marker on the field, including the ones inside a union arm.

    ``FilePath | None`` keeps its ``PathType`` on the arm rather than on the field, so
    reading ``field_info.metadata`` alone would classify an optional path as an output
    path and drop its existence check.
    """
    return [*field_info.metadata, *_annotation_markers(field_info.annotation)]


def _annotation_markers(annotation: Any) -> list[Any]:
    origin = get_origin(annotation)
    if origin is Annotated:
        return list(get_args(annotation)[1:])
    if origin is types.UnionType or str(origin) == "typing.Union":
        return [marker for arg in get_args(annotation) for marker in _annotation_markers(arg)]
    return []


def collect_node_params(
    schema: type[BaseModel] | None,
    yaml_params: dict[str, Any],
    prompt_prefix: str,
    replay_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Prompt for each schema field, prefilling a default for every value already known.

    ``replay_params`` (the answers recorded for a history entry being re-run) take
    precedence over the pipeline YAML as the offered default; both remain editable
    at the prompt.
    """
    if schema is None:
        return {}
    replay_params = replay_params or {}
    overrides: dict[str, Any] = {}
    for field_name, field_info in schema.model_fields.items():
        label = f"{prompt_prefix}.{field_name}"
        prompt = f"{label} ({field_info.description})?" if field_info.description else f"{label}?"
        default_value = replay_params.get(field_name, yaml_params.get(field_name))
        answer = _prompt_for_field(prompt, field_info, default_value)
        if answer is not None:
            overrides[field_name] = answer
    return overrides


class PathFieldKind(StrEnum):
    """What a path field's answer must point at."""

    EXISTING_FILE = "existing_file"
    EXISTING_DIRECTORY = "existing_directory"
    OUTPUT_DIRECTORY = "output_directory"
    OUTPUT_PATH = "output_path"


def _get_field_type(field_info: FieldInfo) -> PathFieldKind:
    """Classify a Path field. An ``InputFile``, an ``InputDirectory`` and pydantic's
    ``FilePath``/``DirectoryPath`` all name something that must already exist; an
    ``OutputDirectory`` names a directory to write into (created on write, so it need not
    exist yet); a bare ``Path`` is an output location that need not exist yet."""
    for meta in _path_markers(field_info):
        if isinstance(meta, InputFileMarker):
            return PathFieldKind.EXISTING_FILE
        if isinstance(meta, InputDirectoryMarker):
            return PathFieldKind.EXISTING_DIRECTORY
        if isinstance(meta, PathType):
            if meta.path_type == "file":
                return PathFieldKind.EXISTING_FILE
            if meta.path_type == "dir":
                return PathFieldKind.EXISTING_DIRECTORY
        if isinstance(meta, OutputDirectoryMarker):
            return PathFieldKind.OUTPUT_DIRECTORY
    return PathFieldKind.OUTPUT_PATH


def _does_user_want_default(answer: str) -> bool:
    """An empty answer submits the prefilled default instead of a new value."""
    return answer == ""


def _find_path_error(answer: str, field_type: PathFieldKind) -> str | None:
    """Return why the answer is invalid for the field type, or None if it is valid."""
    if _does_user_want_default(answer):
        return None
    is_url = "://" in answer
    # A URL-shaped answer skips local-existence checks: we deliberately don't
    # validate remote reachability here, since a synchronous network call inside a
    # prompt validator would block the REPL. Any real problem surfaces later as a
    # GET/PUT failure from http_filesystem. A directory field is always local, so a
    # URL there is still an error.
    path = Path(answer)
    match field_type:
        case PathFieldKind.EXISTING_FILE:
            if is_url:
                return None
            if path.is_dir():
                return f"{answer} is a directory; provide a file"
            if not path.exists():
                return f"{answer} does not exist; provide an existing file"
            if not path.is_file():
                return f"{answer} is not a file; provide a regular file"
        case PathFieldKind.EXISTING_DIRECTORY:
            if path.is_file():
                return f"{answer} is a file; provide an existing directory"
            if not path.exists():
                return f"{answer} does not exist; provide an existing directory"
            if not path.is_dir():
                return f"{answer} is not a directory; provide an existing directory"
        case PathFieldKind.OUTPUT_DIRECTORY:
            if is_url:
                return None
            # The sink writes one file per component underneath, so a missing path
            # (created on write) or an existing directory is fine; only an existing
            # file is wrong.
            if path.is_file():
                return f"{answer} is a file; provide a directory path"
        case PathFieldKind.OUTPUT_PATH:
            if is_url:
                return None
            if path.is_dir():
                return f"{answer} is a directory; provide a file path"
    return None


def _choose_path_validator(field_info: FieldInfo) -> Callable[[str], bool | str]:
    """Adapt path validation to questionary, which wants True or an error message string."""
    field_type = _get_field_type(field_info)

    def validate(answer: str) -> bool | str:
        error = _find_path_error(answer, field_type)
        return error if error is not None else True

    return validate


def _prompt_for_field(prompt: str, field_info: FieldInfo, default_value: Any) -> Any:
    if field_info.annotation is bool:
        default = bool(default_value) if default_value is not None else False
        return questionary.confirm(prompt, default=default).ask()

    default_str = ""
    if default_value is not None:
        default_str = str(default_value)
    elif not field_info.is_required() and field_info.default is not None:
        default_str = str(field_info.default)

    if _annotation_includes_path(field_info.annotation):
        # The path widget autocompletes on Tab so the user is not typing blind.
        validate = _choose_path_validator(field_info)
        answer = questionary.path(
            f"{prompt}  {PATH_PROMPT_HINT}", default=default_str, validate=validate
        ).ask()
    else:
        answer = questionary.text(prompt, default=default_str).ask()
    if _does_user_want_default(answer):
        return None
    return answer
