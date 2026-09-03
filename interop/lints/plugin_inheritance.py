"""Statically check that plugin classes inherit their Protocol.

A plugin class is any class under a plugin category directory that declares a
non-empty ``name = "..."`` class attribute. For each, this check asserts the
class reaches the matching Protocol through its bases (Source / TranslationStep
/ Validator / Sink for plugins; the Port declared via ``port = SomePort`` for
adapters), following bare-name bases declared elsewhere in the same category.
Structural typing lets mypy pass a class that never inherits its Protocol,
while discovery rejects it at registration time, so this catches a mistake
nothing else does.

A project scaffolded by ``interop init`` keeps its plugins under
``./plugins/<category>/``, which is the default the console script scans.
"""

from __future__ import annotations

import argparse
import ast
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

DEFAULT_PLUGIN_ROOT = Path("plugins")

# Category directory name -> the bases a class declaring `name` must reach.
# `adapters` is None: the required base is read from each class's `port = ...`.
CATEGORY_BASES: dict[str, tuple[str, ...] | None] = {
    "sources": ("Source", "StagedSource"),
    "steps": ("TranslationStep",),
    "validators": ("Validator",),
    "sinks": ("Sink",),
    "adapters": None,
}


def _string_class_attribute(node: ast.ClassDef, attr_name: str) -> str | None:
    """Return the string literal assigned to `attr_name` at class level, or None."""
    for stmt in node.body:
        if (
            isinstance(stmt, ast.AnnAssign)
            and isinstance(stmt.target, ast.Name)
            and stmt.target.id == attr_name
            and isinstance(stmt.value, ast.Constant)
            and isinstance(stmt.value.value, str)
        ):
            return stmt.value.value
        if (
            isinstance(stmt, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == attr_name for t in stmt.targets)
            and isinstance(stmt.value, ast.Constant)
            and isinstance(stmt.value.value, str)
        ):
            return stmt.value.value
    return None


def _name_class_attribute(node: ast.ClassDef, attr_name: str) -> str | None:
    """Return the bare identifier assigned to `attr_name` at class level, or None.

    Only matches `attr = Identifier` (no attribute access, no subscript).
    """
    for stmt in node.body:
        if (
            isinstance(stmt, ast.AnnAssign)
            and isinstance(stmt.target, ast.Name)
            and stmt.target.id == attr_name
            and isinstance(stmt.value, ast.Name)
        ):
            return stmt.value.id
        if (
            isinstance(stmt, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == attr_name for t in stmt.targets)
            and isinstance(stmt.value, ast.Name)
        ):
            return stmt.value.id
    return None


def _base_names(node: ast.ClassDef) -> set[str]:
    # Only bare-name bases are accepted (e.g. `class Foo(Source):`). Dotted
    # forms like `class Foo(pipeline.Source):` are rejected on purpose: a
    # static AST can't resolve whether `pipeline.Source` is the expected
    # Protocol or an unrelated class that happens to share the final
    # attribute name, so we require plugins to import the Protocol directly.
    names: set[str] = set()
    for base in node.bases:
        if isinstance(base, ast.Name):
            names.add(base.id)
        elif isinstance(base, ast.Subscript) and isinstance(base.value, ast.Name):
            names.add(base.value.id)
    return names


def _read_category_bases(paths: Sequence[Path]) -> dict[str, set[str]]:
    """Map each class defined in a plugin category to its bare-name bases.

    ``discover()`` checks the Protocol against the resolved class's ``__mro__``, so a
    plugin may reach its Protocol through a shared base declared alongside it. Reading
    the whole category lets this check follow that hop the same way.
    """
    bases_by_class: dict[str, set[str]] = {}
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                bases_by_class[node.name] = _base_names(node)
    return bases_by_class


def _resolve_bases(node: ast.ClassDef, bases_by_class: dict[str, set[str]]) -> set[str]:
    """Every base reachable from a class through bare-name bases in the same category."""
    resolved: set[str] = set()
    pending = list(_base_names(node))
    while pending:
        base = pending.pop()
        if base in resolved:
            continue
        resolved.add(base)
        pending.extend(bases_by_class.get(base, set()))
    return resolved


def _check_file(
    path: Path, expected_bases: tuple[str, ...] | None, bases_by_class: dict[str, set[str]]
) -> list[str]:
    errors: list[str] = []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        if _string_class_attribute(node, "name") is None:
            continue
        bases = _resolve_bases(node, bases_by_class)
        if expected_bases is None:
            declared_port = _name_class_attribute(node, "port")
            if declared_port is None:
                errors.append(
                    f"{path}:{node.lineno}: adapter class {node.name!r} declares a 'name' "
                    "but no 'port = SomePort' attribute"
                )
            elif declared_port not in bases:
                errors.append(
                    f"{path}:{node.lineno}: adapter class {node.name!r} declares "
                    f"port = {declared_port} but does not inherit from {declared_port}"
                )
        elif not any(base in bases for base in expected_bases):
            expected_str = " or ".join(expected_bases)
            errors.append(
                f"{path}:{node.lineno}: class {node.name!r} declares a 'name' "
                f"but does not inherit from {expected_str}"
            )
    return errors


def _check_category(directory: Path, expected_bases: tuple[str, ...] | None) -> list[str]:
    # rglob, not glob: discovery walks a category recursively, so steps and
    # validators may be organised into per-direction or per-framework subpackages.
    paths = sorted(directory.rglob("*.py"))
    bases_by_class = _read_category_bases(paths)
    return [
        error
        for path in paths
        if path.name != "__init__.py"
        for error in _check_file(path, expected_bases, bases_by_class)
    ]


def check_plugin_inheritance(
    plugin_roots: Iterable[Path], adapter_dirs: Iterable[Path] = ()
) -> list[str]:
    """Return one message per plugin class that fails to inherit its Protocol.

    Each entry in ``plugin_roots`` is a directory holding the category
    subdirectories named in ``CATEGORY_BASES``; a category that is absent is
    skipped. ``adapter_dirs`` names directories that *are themselves* an
    adapter category, for a layout that does not nest them under a plugin root.
    """
    errors: list[str] = []
    categories = [
        (root / category, expected)
        for root in plugin_roots
        for category, expected in CATEGORY_BASES.items()
    ]
    categories.extend((directory, None) for directory in adapter_dirs)
    for directory, expected in categories:
        if directory.is_dir():
            errors.extend(_check_category(directory, expected))
    return errors


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "plugin_roots",
        nargs="*",
        type=Path,
        default=[DEFAULT_PLUGIN_ROOT],
        metavar="ROOT",
        help="directory holding the plugin category subdirectories (default: plugins)",
    )
    parser.add_argument(
        "--adapters-dir",
        action="append",
        type=Path,
        default=[],
        dest="adapter_dirs",
        metavar="DIR",
        help="a directory that is itself an adapter category; repeatable",
    )
    args = parser.parse_args(argv)
    errors = check_plugin_inheritance(args.plugin_roots, args.adapter_dirs)
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
