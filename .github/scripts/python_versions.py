# /// script
# requires-python = ">=3.11"
# ///
"""Emit the Python versions CI runs on, derived from ``requires-python``.

Writes ``key=value`` lines for ``$GITHUB_OUTPUT``: ``all`` is the JSON matrix of
every supported 3.x, ``latest`` is the newest of them.
"""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path

_PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"

# Only `>=3.x` and `<3.x` are understood; anything else raises rather than
# guessing a matrix from a specifier this cannot evaluate.
_CLAUSE = re.compile(r"(?P<operator>>=|<)3\.(?P<minor>\d+)")


def main() -> int:
    versions = derive_supported_versions(read_requires_python())
    print(f"all={json.dumps(versions)}")
    print(f"latest={versions[-1]}")
    return 0


def read_requires_python() -> str:
    metadata = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    requires_python: str = metadata["project"]["requires-python"]
    return requires_python


def derive_supported_versions(requires_python: str) -> list[str]:
    """Every supported 3.x, oldest first."""
    oldest, beyond_newest = _read_bounds(requires_python)
    versions = [f"3.{minor}" for minor in range(oldest, beyond_newest)]
    if not versions:
        raise ValueError(f"requires-python {requires_python!r} admits no version")
    return versions


def _read_bounds(requires_python: str) -> tuple[int, int]:
    """The inclusive lower and exclusive upper 3.x minor."""
    minors: dict[str, int] = {}
    for clause in requires_python.split(","):
        operator, minor = _parse_clause(clause.strip())
        if operator in minors:
            raise ValueError(f"requires-python {requires_python!r} repeats {operator!r}")
        minors[operator] = minor
    if minors.keys() != {">=", "<"}:
        raise ValueError(f"requires-python {requires_python!r} needs a '>=' and a '<' clause")
    return minors[">="], minors["<"]


def _parse_clause(clause: str) -> tuple[str, int]:
    match = _CLAUSE.fullmatch(clause)
    if match is None:
        raise ValueError(f"unsupported requires-python clause {clause!r}")
    return match["operator"], int(match["minor"])


if __name__ == "__main__":
    sys.exit(main())
