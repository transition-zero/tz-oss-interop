"""Compute a function-weighted maintainability score per file, write a Markdown report
with a shields.io badge, and gate on grade A across every source file.

Radon's own Maintainability Index is computed per file and is dominated by file length
(its `16.2 * ln(SLOC)` term), so a long module of small, simple functions scores the
same as one giant function. We care more about per-function size and complexity than
about raw file length, so the score here blends two views of the *same* radon measures
(Halstead volume, cyclomatic complexity, SLOC, comment ratio):

    combined = W_FUNCTION * mean(per-function MI) + W_FILE * (file MI)

The per-function MI feeds each function's own length and complexity into radon's
`mi_compute`, so small functions lift the score even in a long file; the file MI is
retained at a lower weight so module-level bloat still registers. Files with no
functions (pure constant/vocabulary modules) score on file MI alone.

The script exits non-zero if any file scores below grade A so the CI step fails; the
comment still posts thanks to `if: always()` on the workflow step.

Radon's MI grading (also applied to the combined score, same 0-100 scale):
    100 >= MI > 20  -> A (very high maintainability)
     20 >= MI > 10  -> B (medium)
     10 >= MI >= 0  -> C (extremely low)
"""

from __future__ import annotations

import ast
import sys
import traceback
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from radon.complexity import cc_visit
from radon.metrics import h_visit, mi_compute, mi_visit
from radon.raw import analyze
from radon.visitors import Function

# Weights blending the per-function view against the per-file view. Functions are
# weighted higher because per-function size and complexity matter more than file length.
W_FUNCTION: float = 0.7
W_FILE: float = 0.3

# Every package the repo ships, the workspace libs included: the harness under
# libs/ is published code a downstream reads and extends, so it is held to the
# same grade as interop itself.
_SOURCE_ROOTS = (Path("interop"), Path("libs"))

# Letter grade to shields.io color (MI has only three grades).
_GRADE_COLORS: dict[str, str] = {
    "A": "brightgreen",
    "B": "yellow",
    "C": "red",
}


def _grade_for(score: float) -> str:
    if score > 20:
        return "A"
    if score > 10:
        return "B"
    return "C"


@dataclass(frozen=True)
class FunctionScore:
    path: str
    name: str
    length: int
    complexity: int
    mi: float


@dataclass(frozen=True)
class FileScore:
    path: str
    file_mi: float
    func_mean: float
    combined: float
    functions: list[FunctionScore]

    @property
    def grade(self) -> str:
        return _grade_for(self.combined)


def _comment_percent(source: str) -> float:
    raw = analyze(source)
    if raw.sloc == 0:
        return 0.0
    return float((raw.comments + raw.multi) / raw.sloc * 100)


def _function_mi(
    halstead_volume: float, complexity: int, length: int, comment_percent: float
) -> float:
    """Per-function MI; a trivial (zero-volume or zero-line) function is perfectly maintainable."""
    if halstead_volume <= 0 or length <= 0:
        return 100.0
    return float(mi_compute(halstead_volume, complexity, length, comment_percent))


def _function_end_lines(source: str) -> dict[int, int]:
    """Map each function's `def` line to its true last line via the stdlib AST.

    radon's `Function.endline` is the line of the last AST node it visited, which falls
    short of the real end whenever a function tails off into a multi-line expression (e.g.
    a `return [ ... ]` comprehension). Slicing on that truncated end cuts mid-bracket, and
    `radon.raw.analyze` then runs the tokenizer off the end of the fragment and raises
    `SyntaxError`. `ast`'s `end_lineno` is the authoritative end of each definition.
    """
    end_by_def_line: dict[int, int] = {}
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.end_lineno is not None:
            end_by_def_line[node.lineno] = node.end_lineno
    return end_by_def_line


def _score_file(path: Path) -> FileScore:
    source = path.read_text(encoding="utf-8")
    source_lines = source.splitlines()
    file_mi = mi_visit(source, True)
    end_by_def_line = _function_end_lines(source)

    volumes: dict[str, deque[float]] = {}
    for name, report in h_visit(source).functions:
        volumes.setdefault(name, deque()).append(report.volume)

    functions: list[FunctionScore] = []
    for block in cc_visit(source):
        if not isinstance(block, Function):
            continue
        volume = volumes[block.name].popleft() if volumes.get(block.name) else 0.0
        end_line = end_by_def_line.get(block.lineno, block.endline)
        length = end_line - block.lineno + 1
        func_source = "\n".join(source_lines[block.lineno - 1 : end_line])
        func_comment_percent = _comment_percent(func_source)
        functions.append(
            FunctionScore(
                path=str(path),
                name=block.name,
                length=length,
                complexity=block.complexity,
                mi=_function_mi(volume, block.complexity, length, func_comment_percent),
            )
        )

    func_mean = sum(f.mi for f in functions) / len(functions) if functions else file_mi
    combined = W_FUNCTION * func_mean + W_FILE * file_mi
    return FileScore(str(path), file_mi, func_mean, combined, functions)


def _badge_url(grade: str, score: str) -> str:
    label = quote(f"{grade} ({score})")
    return f"https://img.shields.io/badge/maintainability-{label}-{_GRADE_COLORS[grade]}"


def _render(files: list[FileScore]) -> str:
    mean = sum(f.combined for f in files) / len(files)
    badge = _badge_url(_grade_for(mean), f"{mean:.2f}")

    lowest = min(files, key=lambda f: f.combined)
    all_functions = [fn for f in files for fn in f.functions]
    strained = min(all_functions, key=lambda fn: fn.mi) if all_functions else None
    offenders = [f for f in files if f.grade != "A"]

    gate_line = (
        "**Gate:** ❌ FAIL (require every file at grade A)" if offenders else "**Gate:** ✅ PASS"
    )

    lines: list[str] = [
        f"![maintainability index]({badge})",
        "",
        gate_line,
        f"**Score:** `{_grade_for(mean)} ({mean:.2f})` mean over {len(files)} files "
        f"(function-weighted: {W_FUNCTION:.0%} mean-of-functions, {W_FILE:.0%} file)",
        f"**Lowest file:** `{lowest.path}` at `{lowest.grade} ({lowest.combined:.2f})`",
    ]
    if strained is not None:
        lines.append(
            f"**Most strained function:** `{strained.path}::{strained.name}` "
            f"({strained.length} lines, CC {strained.complexity}) at MI {strained.mi:.1f}"
        )
    lines.append("")

    if offenders:
        lines.append(f"**Files below grade A:** {len(offenders)}")
        lines.append("")
        lines.append("| File | Grade | Combined | File MI | Func mean |")
        lines.append("| --- | --- | --- | --- | --- |")
        for f in offenders:
            lines.append(
                f"| `{f.path}` | {f.grade} | {f.combined:.2f} "
                f"| {f.file_mi:.2f} | {f.func_mean:.2f} |"
            )
        lines.append("")
    else:
        lines.append("All files grade A.")
        lines.append("")

    lines.append("<details><summary>Full report</summary>")
    lines.append("")
    lines.append("| File | Combined | File MI | Func mean | Worst function |")
    lines.append("| --- | --- | --- | --- | --- |")
    for f in sorted(files, key=lambda f: f.combined):
        worst = min(f.functions, key=lambda fn: fn.mi) if f.functions else None
        worst_cell = f"`{worst.name}` ({worst.length}ln, CC{worst.complexity})" if worst else "—"
        lines.append(
            f"| `{f.path}` | {f.combined:.2f} | {f.file_mi:.2f} "
            f"| {f.func_mean:.2f} | {worst_cell} |"
        )
    lines.append("")
    lines.append("</details>")
    lines.append("")
    return "\n".join(lines)


def _render_failure(reason: str, detail: str) -> str:
    return "\n".join(
        [
            "**Gate:** ❌ FAIL (maintainability report failed to run)",
            f"**Reason:** {reason}",
            "",
            "<details><summary>Traceback</summary>",
            "",
            "```",
            detail.rstrip() or "(no detail captured)",
            "```",
            "",
            "</details>",
            "",
        ]
    )


def _roots_label() -> str:
    return ", ".join(str(root) for root in _SOURCE_ROOTS)


def main() -> int:
    report_path = Path("maintainability_report.md")
    try:
        sources = sorted(path for root in _SOURCE_ROOTS for path in root.rglob("*.py"))
        files = [_score_file(path) for path in sources]
    except Exception as exc:  # noqa: BLE001 - report any failure to the PR comment, then fail CI
        report_path.write_text(_render_failure(str(exc), traceback.format_exc()), encoding="utf-8")
        print(f"Maintainability report failed: {exc}", file=sys.stderr)
        return 1

    if not files:
        report_path.write_text(
            _render_failure(f"no .py files under {_roots_label()}", ""), encoding="utf-8"
        )
        print(f"No source files found under {_roots_label()}", file=sys.stderr)
        return 1

    report = _render(files)
    report_path.write_text(report, encoding="utf-8")
    print(report)
    below_a = [f.path for f in files if f.grade != "A"]
    if below_a:
        print(
            f"Maintainability gate failed: {len(below_a)} file(s) below grade A: "
            f"{', '.join(below_a)}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
