"""Statically check that every test file drives tests through pytest-bdd.

This project uses BDD scenarios as the test surface: scenarios describe
behavior from a user's perspective and drive translate through the REPL.
Plain pytest functions (`def test_*()` with no @scenario decorator)
escape that discipline — they become unit tests by another name.

The rule: every `tests/**/test_*.py` file (other than `conftest.py`) must
declare its tests through one of pytest-bdd's two binding forms:
  - `scenarios("<file>.feature")` — binds every scenario in a feature file
  - `@scenario("<file>.feature", "<title>")` — binds a single scenario to
    a named function

A `def test_*()` without a `@scenario` decorator, or a `test_*.py` file
with no pytest-bdd binding at all, is a violation. Catches the slide
back into plain pytest at lint time.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = REPO_ROOT / "tests"


def _has_scenarios_call(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "scenarios":
            return True
        if isinstance(func, ast.Attribute) and func.attr == "scenarios":
            return True
    return False


def _is_scenario_decorator(decorator: ast.expr) -> bool:
    if isinstance(decorator, ast.Call):
        decorator = decorator.func
    if isinstance(decorator, ast.Name):
        return decorator.id == "scenario"
    if isinstance(decorator, ast.Attribute):
        return decorator.attr == "scenario"
    return False


def _classify_test_functions(
    tree: ast.Module,
) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    """Return (decorated, undecorated) test_* function definitions."""
    decorated: list[tuple[int, str]] = []
    undecorated: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if not node.name.startswith("test_"):
            continue
        if any(_is_scenario_decorator(d) for d in node.decorator_list):
            decorated.append((node.lineno, node.name))
        else:
            undecorated.append((node.lineno, node.name))
    return decorated, undecorated


def _violations_in_file(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    relative = path.relative_to(REPO_ROOT)

    has_scenarios = _has_scenarios_call(tree)
    decorated, undecorated = _classify_test_functions(tree)

    violations: list[str] = []
    for lineno, name in undecorated:
        violations.append(
            f"{relative}:{lineno}: plain pytest function {name!r} "
            "(must be bound via @scenario or scenarios())"
        )
    if not has_scenarios and not decorated and not undecorated:
        violations.append(
            f"{relative}: no scenarios() call and no @scenario-decorated tests; "
            "either bind to a .feature file or rename if this is not a test module"
        )
    return violations


def main() -> int:
    if not TESTS_DIR.is_dir():
        print(f"tests directory not found at {TESTS_DIR}", file=sys.stderr)
        return 1

    failures: list[str] = []
    for path in sorted(TESTS_DIR.rglob("test_*.py")):
        if path.name == "conftest.py" or "__pycache__" in path.parts:
            continue
        failures.extend(_violations_in_file(path))

    if failures:
        print(
            "All test files must drive tests through pytest-bdd "
            "(scenarios(...) or @scenario(...)). Plain pytest functions are forbidden.",
            file=sys.stderr,
        )
        print("", file=sys.stderr)
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
