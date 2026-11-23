# /// script
# requires-python = ">=3.11"
# dependencies = ["packaging>=24"]
# ///
"""Emit the uv arguments that resolve each capped dependency at its highest version.

A dependency with an upper bound is one this project promises to work with across a
range, and the lockfile pins one point in that range. CI tests the lockfile, so without
this the top of each range reaches a consumer untested.

Writes ``key=value`` lines for ``$GITHUB_OUTPUT``: ``upgrade`` is the
``--upgrade-package`` arguments, and ``names`` lists the distributions for the log.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

from packaging.requirements import Requirement

_PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"
_CAPPING_OPERATORS = frozenset({"<", "<="})


def main() -> int:
    capped = list_capped_dependencies(read_dependencies())
    print(f"upgrade={' '.join(f'--upgrade-package {name}' for name in capped)}")
    print(f"names={' '.join(capped) or '(none)'}")
    return 0


def read_dependencies() -> list[str]:
    metadata = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    dependencies: list[str] = metadata["project"]["dependencies"]
    return dependencies


def list_capped_dependencies(dependencies: list[str]) -> list[str]:
    """The name of every dependency whose specifier states an upper bound, as declared."""
    parsed = map(Requirement, dependencies)
    return [requirement.name for requirement in parsed if has_upper_bound(requirement)]


def has_upper_bound(requirement: Requirement) -> bool:
    return any(clause.operator in _CAPPING_OPERATORS for clause in requirement.specifier)


if __name__ == "__main__":
    sys.exit(main())
