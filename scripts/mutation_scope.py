"""Which source files a mutation run mutates.

A run on a pull request mutates only the files that the pull request changes. This module
reads the changed paths on stdin and writes the mutable ones to stdout, one for each line:

    git diff --name-only --diff-filter=d <base>...HEAD | uv run python scripts/mutation_scope.py

The output can be empty. `scripts/run_mutmut.py` reads the list from the file that
`MUTATION_TARGETS_FILE` names, and never starts mutmut with an empty list, because an empty
`only_mutate` makes mutmut mutate every file.
"""

from __future__ import annotations

import fnmatch
import os
import sys
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"

TARGETS_FILE_ENVIRONMENT_VARIABLE = "MUTATION_TARGETS_FILE"

# The translation plugin layer (every step/source/sink plus the shared recipe code, and the
# Julia solver adapter) is exercised only by the @slow @fork_unsafe pipeline tests, which the
# default `not slow` filter excludes. Under that filter these modules have no covering test,
# so every one of their mutants is a "no tests" non-result: zero signal, but mutmut still
# generates and iterates them. They are ~83% of the mutant set, and the slow tail of them is
# what pushes the CI job past its timeout. The default run leaves them out; the fork-unsafe
# run (`make mutation-full`) keeps them mutable, where the fresh-interpreter re-exec in
# run_mutmut.py lets the @slow suite actually kill them. The generic noop/emit_json plugins
# are *not* excluded: non-slow tests cover them for real.
TRANSLATION_LAYER_ONLY_COVERED_BY_SLOW = [
    "interop/plugins/steps/*",
    "interop/plugins/shared/*",
    "interop/plugins/sources/stage_*",
    "interop/plugins/sinks/_extensions_json.py",
    "interop/plugins/sinks/emit_pypsa_*",
    "interop/plugins/sinks/emit_sienna_*",
    "interop/plugins/sinks/emit_power_simulations_*",
    "interop/plugins/sinks/emit_results_parquet.py",
    "interop/adapters/outbound/julia_solver.py",
    "interop/templates/*",
]


@dataclass(frozen=True)
class MutationScope:
    """The files mutmut can mutate: under a source path, and matched by no exclusion."""

    source_paths: list[str]
    excluded_patterns: list[str]

    def list_targets(self, changed_paths: Iterable[str]) -> list[str]:
        return sorted({path for path in changed_paths if self.is_mutable(path)})

    def is_mutable(self, path: str) -> bool:
        return (
            path.endswith(".py")
            and path.startswith(tuple(self.source_paths))
            and not any(fnmatch.fnmatch(path, pattern) for pattern in self.excluded_patterns)
        )


def main() -> None:
    changed_paths = [line.strip() for line in sys.stdin if line.strip()]
    targets = build_mutation_scope().list_targets(changed_paths)
    sys.stdout.write("".join(f"{target}\n" for target in targets))


def build_mutation_scope() -> MutationScope:
    config = read_mutmut_config()
    return MutationScope(
        source_paths=config["source_paths"],
        excluded_patterns=[*config["do_not_mutate"], *list_slow_only_patterns()],
    )


def read_mutmut_config() -> dict[str, list[str]]:
    pyproject = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    config: dict[str, list[str]] = pyproject["tool"]["mutmut"]
    return config


def list_slow_only_patterns() -> list[str]:
    if is_fork_unsafe_included():
        return []
    return TRANSLATION_LAYER_ONLY_COVERED_BY_SLOW


def is_fork_unsafe_included() -> bool:
    return bool(os.environ.get("MUTATION_INCLUDE_FORK_UNSAFE"))


def find_targets() -> list[str] | None:
    """The files a targeted run mutates, or None when the run mutates every file."""
    targets_file = os.environ.get(TARGETS_FILE_ENVIRONMENT_VARIABLE)
    if not targets_file:
        return None
    lines = Path(targets_file).read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip()]


if __name__ == "__main__":
    main()
