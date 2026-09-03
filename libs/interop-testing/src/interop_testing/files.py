"""Readers shared by the file and document assertions.

Framework step modules build their own assertions on these, so a project that
needs a check the published vocabulary does not cover can do the same.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_json(path: str | Path) -> Any:
    """Parse a JSON file, failing with the path in the message if it is not there."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def navigate_json(data: Any, key_path: str, context: str) -> Any:
    """Navigate a dot-separated path through nested dicts/lists.

    `context` names the document in assertion messages, so a failure says which
    file (and which component within it) the missing key was expected in.
    """
    actual = data
    segments = key_path.split(".")
    for i, segment in enumerate(segments):
        current = ".".join(segments[:i]) or "<root>"
        if isinstance(actual, list):
            assert segment.isdigit(), (
                f"expected numeric index for list at {current!r} in {context}, got {segment!r}"
            )
            actual = actual[int(segment)]
        elif isinstance(actual, dict):
            assert segment in actual, (
                f"expected key {segment!r} at {current!r} in {context}, got keys {list(actual)!r}"
            )
            actual = actual[segment]
        else:
            raise AssertionError(
                f"expected dict or list at {current!r} in {context}, "
                f"got {type(actual).__name__}: {actual!r}"
            )
    return actual
