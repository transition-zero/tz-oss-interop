"""pytest-bdd vocabulary for the files a pipeline run produced.

Framework-agnostic: what any project says about a file's existence, its text,
or a value inside a JSON document. Assertions about a *framework's* artefacts
live in that framework's step module.
"""

from __future__ import annotations

import json
from pathlib import Path

from pytest_bdd import given, parsers, then

from interop_testing.files import navigate_json, read_json


@given(parsers.parse('a file "{path}" exists'))
def given_file_exists(path: str) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text("{}", encoding="utf-8")


@given(parsers.parse('a file "{path}" containing "{content}"'))
def given_file_containing(path: str, content: str) -> None:
    _write_file(path, content)


@given(parsers.parse('a file "{path}" containing the lines:'))
def given_file_containing_lines(path: str, datatable: list[list[str]]) -> None:
    """A single-column `| line |` table, written one row per line."""
    _header, *rows = datatable
    _write_file(path, "".join(f"{line}\n" for (line,) in rows))


def _write_file(path: str, content: str) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")


@then(parsers.parse('the file "{path}" exists'))
def assert_file_exists(path: str) -> None:
    assert Path(path).is_file(), f"expected file {path!r} to exist, but it does not"


@then(parsers.parse('the file "{path}" does not exist'))
def assert_file_does_not_exist(path: str) -> None:
    assert not Path(path).exists(), f"expected file {path!r} not to exist, but it does"


@then(parsers.parse('the file "{path}" reads back as "{expected}"'))
def assert_file_reads_back_as(path: str, expected: str) -> None:
    actual = Path(path).read_text(encoding="utf-8")
    assert actual == expected, f"expected {expected!r} at {path}, got {actual!r}"


@then(parsers.parse('the file "{path}" contains "{expected}"'))
def assert_file_contains(path: str, expected: str) -> None:
    actual = Path(path).read_text(encoding="utf-8")
    assert expected in actual, f"expected {path} to contain {expected!r}, got {actual!r}"


@then(parsers.parse('the file "{path}" does not contain "{unexpected}"'))
def assert_file_does_not_contain(path: str, unexpected: str) -> None:
    actual = Path(path).read_text(encoding="utf-8")
    assert unexpected not in actual, (
        f"expected {path} not to contain {unexpected!r}, got {actual!r}"
    )


@then(parsers.parse('the file "{path}" is JSON indented with {width:d} spaces'))
def assert_json_indent(path: str, width: int) -> None:
    """Compare against the document re-serialised at that width, so content can change."""
    actual = Path(path).read_text(encoding="utf-8").rstrip("\n")
    expected = json.dumps(json.loads(actual), indent=width)
    assert actual == expected, f"{path} is not indented with {width} spaces:\n{actual}"


@then(parsers.parse('the file "{path}" parses as valid JSON'))
def assert_valid_json(path: str) -> None:
    read_json(path)


@then(parsers.parse('the file "{path}" parses as JSON with "{key_path}" set to {value}'))
def assert_json_key_value(path: str, key_path: str, value: str) -> None:
    expected = json.loads(value)
    actual = navigate_json(read_json(path), key_path, path)
    assert actual == expected, f"expected {key_path!r} = {expected!r} in {path}, got {actual!r}"


@then(parsers.parse('the file "{path}" parses as JSON where array "{key}" has length {length:d}'))
def assert_json_array_length(key: str, path: str, length: int) -> None:
    data = read_json(path)
    assert key in data, f"expected key {key!r} in {path}, got keys {list(data)!r}"
    actual = data[key]
    assert isinstance(actual, list), (
        f"expected {key!r} to be an array in {path}, got {type(actual).__name__}: {actual!r}"
    )
    assert len(actual) == length, (
        f"expected {key!r} to have length {length}, got {len(actual)}: {actual!r}"
    )
