"""Text that an adapter puts inside a Julia string literal."""

from __future__ import annotations

from pathlib import Path


def build_julia_path_text(path: Path) -> str:
    """`path` as the text of a Julia double-quoted string, which reads `$` and `"` as code."""
    return str(path).replace("\\", "/").replace('"', '\\"').replace("$", "\\$")
