"""Check the feature tags that keep the mutation run inside its budget.

Two rules, both statically checkable:

1. Every feature file in a subdirectory of `tests/features/` drives a real end-to-end
   translation, so it carries `@slow`. The mutation run picks its per-mutant test set
   with `-m "not slow"` (pyproject `[tool.mutmut] pytest_add_cli_args`), and nearly
   every mutant in `interop/core/` is covered by nearly all of it, so one untagged
   pipeline feature multiplies the cost of the whole job.

2. `@fork_unsafe` never appears without `@slow` in effect. A fork-unsafe scenario makes
   every mutant it covers pay a fresh-interpreter re-exec, seconds apiece; without
   `@slow` to hold it out of the default run, those seconds land on the CI mutation job.

Neither rule can tell that a scenario runs a Polars compute in the first place, so a
missing `@fork_unsafe` still has to be caught by reading the mutation results: it shows
up as a timeout rather than a killed or surviving mutant.

The Test job applies no marker filter, so tagged scenarios still run on every push.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import NamedTuple

REPO_ROOT = Path(__file__).resolve().parents[1]
FEATURES_DIR = REPO_ROOT / "tests" / "features"
SLOW_TAG = "@slow"
FORK_UNSAFE_TAG = "@fork_unsafe"


class TagViolation(NamedTuple):
    path: Path
    line_number: int
    message: str


def parse_tags(line: str) -> set[str]:
    return {word for word in line.split() if word.startswith("@")}


def read_feature_tags(path: Path) -> set[str]:
    """The tags above the `Feature:` keyword, which every scenario in the file inherits.

    Rule 1 reads only these, so a file that tags each of its scenarios `@slow`
    individually is reported even though every scenario is in fact excluded. Tag the
    feature instead: a scenario added later would otherwise join the run untagged.
    """
    tags: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if not line.startswith("@"):
            return tags
        tags |= parse_tags(line)
    return tags


def read_tag_lines(path: Path) -> list[tuple[int, set[str]]]:
    """Every tag line in the file, as (1-based line number, tags on that line)."""
    numbered_lines = enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
    return [
        (number, parse_tags(line))
        for number, line in numbered_lines
        if line.strip().startswith("@")
    ]


def find_pipeline_features_missing_slow() -> list[TagViolation]:
    return [
        TagViolation(path, 1, f"pipeline feature without {SLOW_TAG}")
        for path in sorted(FEATURES_DIR.glob("*/**/*.feature"))
        if SLOW_TAG not in read_feature_tags(path)
    ]


def find_fork_unsafe_without_slow(path: Path) -> list[TagViolation]:
    inherited = read_feature_tags(path)
    effective = [(number, tags | inherited) for number, tags in read_tag_lines(path)]
    return [
        TagViolation(path, number, f"{FORK_UNSAFE_TAG} without {SLOW_TAG}")
        for number, tags in effective
        if FORK_UNSAFE_TAG in tags and SLOW_TAG not in tags
    ]


def find_all_fork_unsafe_without_slow() -> list[TagViolation]:
    return [
        violation
        for path in sorted(FEATURES_DIR.rglob("*.feature"))
        for violation in find_fork_unsafe_without_slow(path)
    ]


def report(violations: list[TagViolation]) -> None:
    print("Feature tags keep the mutation run inside its budget (see CLAUDE.md):", file=sys.stderr)
    print("", file=sys.stderr)
    for violation in violations:
        location = violation.path.relative_to(REPO_ROOT)
        print(f"{location}:{violation.line_number}: {violation.message}", file=sys.stderr)


def main() -> int:
    if not FEATURES_DIR.is_dir():
        print(f"features directory not found at {FEATURES_DIR}", file=sys.stderr)
        return 1
    violations = [*find_pipeline_features_missing_slow(), *find_all_fork_unsafe_without_slow()]
    if not violations:
        return 0
    report(violations)
    return 1


if __name__ == "__main__":
    sys.exit(main())
