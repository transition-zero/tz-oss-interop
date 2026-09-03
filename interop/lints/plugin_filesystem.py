"""Forbid plugins from touching the filesystem behind FilesystemPort's back.

Sinks and sources receive file locations as params fields whose names contain
``path``. Such a value, and anything derived from it, may only be handed to a
method on ``self._fs`` (the injected FilesystemPort). Passing it to anything else
(``open``, ``h5py.File``, ``Path.mkdir``, a library export call) reads or writes
the local disk directly, which breaks as soon as the port is backed by a root
remap or remote storage. Staging scratch (paths derived from ``staging_dir``) is
deliberately exempt for sources: it is process-local by contract.

Steps and validators must not touch the filesystem at all: they transform
in-memory state. The import contract already stops them importing the port or
the sources/sinks modules; this check closes the remaining hole of direct calls,
by flagging any use of ``open``, ``Path(...)``, ``staging_dir``, or a params path
in a call.

The check is a per-function taint analysis:

- Seeds: ``params.<attr>`` where ``attr`` contains ``path`` (all layers); for
  steps additionally ``Path(...)`` constructions and any ``staging_dir`` access.
- Propagation: names assigned from a tainted expression are tainted. ``with``
  targets bound from ``self._fs`` calls are not (port streams are the sanctioned
  way to read and write). f-strings do not propagate taint, so paths may appear
  in error messages.
- Violation: a call that receives a tainted argument, or is a method on a
  tainted receiver, unless the callee is ``self._fs.<method>`` (never allowed in
  steps). In steps, any bare ``open(...)`` call is also a violation.

A project scaffolded by ``interop init`` keeps its plugins under
``./plugins/<category>/``, which is the default the console script scans.
"""

from __future__ import annotations

import argparse
import ast
import sys
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

PARAMS_NAME = "params"
FS_ATTRIBUTE = "_fs"

DEFAULT_PLUGIN_ROOT = Path("plugins")


@dataclass(frozen=True)
class CategoryRule:
    fs_callee_allowed: bool
    extra_seed: Callable[[ast.AST], bool] | None
    open_banned: bool
    message: str


def _is_fs_callee(func: ast.expr) -> bool:
    return (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Attribute)
        and func.value.attr == FS_ATTRIBUTE
        and isinstance(func.value.value, ast.Name)
        and func.value.value.id == "self"
    )


def _is_self_method_callee(func: ast.expr) -> bool:
    """Direct method call on self (e.g. self.build_document(...)).

    Excluded: self._fs.* — those are caught by _is_fs_callee above.
    These methods are checked independently by the linter, so any
    filesystem access inside them will be flagged in their own scope.
    """
    return (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id == "self"
    )


def _is_fs_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and _is_fs_callee(node.func)


def _is_self_method_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and _is_self_method_callee(node.func)


def _is_params_path_seed(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == PARAMS_NAME
        and "path" in node.attr
    )


def _is_step_seed(node: ast.AST) -> bool:
    is_path_construction = (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == Path.__name__
    )
    is_staging_dir_access = isinstance(node, ast.Attribute) and node.attr == "staging_dir"
    return is_path_construction or is_staging_dir_access


def _is_open_call(node: ast.Call) -> bool:
    return isinstance(node.func, ast.Name) and node.func.id == "open"


CATEGORY_RULES: dict[str, CategoryRule] = {
    "sinks": CategoryRule(
        fs_callee_allowed=True,
        extra_seed=None,
        open_banned=False,
        message="sinks may only pass output paths to self._fs.* (FilesystemPort)",
    ),
    "sources": CategoryRule(
        fs_callee_allowed=True,
        extra_seed=None,
        open_banned=False,
        message="sources may only pass input paths to self._fs.* (FilesystemPort)",
    ),
    "steps": CategoryRule(
        fs_callee_allowed=False,
        extra_seed=_is_step_seed,
        open_banned=True,
        message="steps must not touch the filesystem",
    ),
    "validators": CategoryRule(
        fs_callee_allowed=False,
        extra_seed=_is_step_seed,
        open_banned=True,
        message="validators must not touch the filesystem",
    ),
}


def _walk_skipping_sanitisers(node: ast.AST) -> Iterator[ast.AST]:
    """Yield sub-nodes, not descending into sanitising constructs.

    f-strings only display a path, and a ``self._fs.<method>(...)`` call is the
    sanctioned hand-off, so its result (data or a port stream) is not a path.
    """
    if isinstance(node, ast.JoinedStr) or _is_fs_call(node) or _is_self_method_call(node):
        return
    yield node
    for child in ast.iter_child_nodes(node):
        yield from _walk_skipping_sanitisers(child)


def _is_tainted(node: ast.AST, tainted_names: set[str], rule: CategoryRule) -> bool:
    for sub in _walk_skipping_sanitisers(node):
        if _is_params_path_seed(sub):
            return True
        if rule.extra_seed is not None and rule.extra_seed(sub):
            return True
        if isinstance(sub, ast.Name) and sub.id in tainted_names:
            return True
    return False


def _tainted_names(function: ast.FunctionDef, rule: CategoryRule) -> set[str]:
    """Fixpoint over assignments: names bound from tainted expressions are tainted."""
    tainted: set[str] = set()
    while True:
        before = len(tainted)
        for node in ast.walk(function):
            targets: list[ast.expr] = []
            value: ast.expr | None = None
            if isinstance(node, ast.Assign):
                targets, value = node.targets, node.value
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                targets, value = [node.target], node.value
            elif isinstance(node, ast.withitem) and node.optional_vars is not None:
                targets, value = [node.optional_vars], node.context_expr
            if value is not None and _is_tainted(value, tainted, rule):
                for target in targets:
                    if isinstance(target, ast.Name):
                        tainted.add(target.id)
        if len(tainted) == before:
            return tainted


def _function_violations(function: ast.FunctionDef, rule: CategoryRule) -> list[ast.Call]:
    tainted = _tainted_names(function, rule)
    violations = []
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        if rule.fs_callee_allowed and (
            _is_fs_callee(node.func) or _is_self_method_callee(node.func)
        ):
            continue
        if rule.open_banned and _is_open_call(node):
            violations.append(node)
            continue
        receives_taint = any(
            _is_tainted(arg, tainted, rule)
            for arg in [*node.args, *(kw.value for kw in node.keywords)]
        )
        called_on_taint = isinstance(node.func, ast.Attribute) and _is_tainted(
            node.func.value, tainted, rule
        )
        if receives_taint or called_on_taint:
            violations.append(node)
    return violations


def _check_category(directory: Path, rule: CategoryRule) -> list[str]:
    # rglob, not glob: steps are organised into per-direction subpackages.
    failures: list[str] = []
    for source_path in sorted(directory.rglob("*.py")):
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            failures.extend(
                f"{source_path}:{call.lineno}: {ast.unparse(call.func)}() "
                f"receives a filesystem path; {rule.message}"
                for call in _function_violations(node, rule)
            )
    return failures


def check_plugin_filesystem(plugin_roots: Iterable[Path]) -> list[str]:
    """Return one message per plugin call that reaches the filesystem directly.

    Each entry in ``plugin_roots`` is a directory holding the category
    subdirectories named in ``CATEGORY_RULES``; a category that is absent is
    skipped. Outbound adapters are not covered: implementing the port is what
    they are for.
    """
    return [
        failure
        for root in plugin_roots
        for category, rule in CATEGORY_RULES.items()
        if (root / category).is_dir()
        for failure in _check_category(root / category, rule)
    ]


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
    args = parser.parse_args(argv)
    failures = check_plugin_filesystem(args.plugin_roots)
    for failure in failures:
        print(failure, file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
