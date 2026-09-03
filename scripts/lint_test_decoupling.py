"""Statically check that BDD step files do not import production code.

BDD scenarios describe behavior from the user's perspective: drive translate
through the REPL, observe the printed output. Anything else couples the
scenario to an implementation detail the user never sees.

The rule: in `tests/step_defs/*.py` (excluding `conftest.py`), no name may be
imported from `interop.*`. All access to production code is mediated through
`tests/step_defs/conftest.py`, which exposes the user-facing entry points
(`_dispatch`, `Command`, `make_container`).

`interop_testing` is exempt. It is the published test harness, not production
code, and a downstream project imports it directly from its own step files —
routing our step files through a mediator instead would leave the harness
exercised in a way no user reproduces.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
STEP_DEFS_DIR = REPO_ROOT / "tests" / "step_defs"
MEDIATOR_FILES = {STEP_DEFS_DIR / "conftest.py", STEP_DEFS_DIR / "__init__.py"}
HARNESS_PACKAGE = "interop_testing"


def _is_forbidden(module: str) -> bool:
    if module == HARNESS_PACKAGE or module.startswith(f"{HARNESS_PACKAGE}."):
        return False
    return module == "interop" or module.startswith("interop.")


def _violations_in_file(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if _is_forbidden(module):
                imported = ", ".join(alias.name for alias in node.names)
                violations.append((node.lineno, f"from {module} import {imported}"))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if _is_forbidden(alias.name):
                    violations.append((node.lineno, f"import {alias.name}"))
    return violations


def main() -> int:
    if not STEP_DEFS_DIR.is_dir():
        print(f"step_defs directory not found at {STEP_DEFS_DIR}", file=sys.stderr)
        return 1

    failures: list[str] = []
    for path in sorted(STEP_DEFS_DIR.rglob("*.py")):
        if path in MEDIATOR_FILES:
            continue
        for lineno, stmt in _violations_in_file(path):
            relative = path.relative_to(REPO_ROOT)
            failures.append(
                f"{relative}:{lineno}: forbidden interop.* import in BDD step file: {stmt}"
            )

    if failures:
        print(
            "BDD step files must not import from interop.* (interop_testing aside); "
            "route through tests/step_defs/conftest.py, or reach for the published "
            "harness in interop_testing.",
            file=sys.stderr,
        )
        print("", file=sys.stderr)
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
