"""Parse `mutmut results`, write a Markdown report, gate on a threshold.

Reads the saved mutmut state via `mutmut results`, tallies mutants by status,
computes a kill score (killed / (killed + survived)), writes a Markdown table
to `mutation_score.md` for the sticky PR comment, and exits non-zero if the
score falls below `MUTATION_THRESHOLD` (default `0.0` = advisory).

Mutants with `no_tests`, `skipped`, `timeout`, or `suspicious` status do not
count toward the denominator: they represent code paths the test suite does
not exercise, not test failures.

The CI job bounds the mutmut step, so a slow run can be cut short. mutmut saves
each result as it finishes, so the state read here is valid but may be partial:
mutants the run never reached carry a `not checked` status. The report says so
rather than scoring a partial run as if it were complete.

Timeouts dominate wall-clock cost in CI (each one burns its whole budget before
being killed), so the report also lists the functions owning the most timeouts.
That makes it obvious which `do_not_mutate` additions would shed the most runtime.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections import Counter
from enum import StrEnum
from pathlib import Path


class Status(StrEnum):
    KILLED = "killed"
    SURVIVED = "survived"
    NO_TESTS = "no tests"
    TIMEOUT = "timeout"
    SUSPICIOUS = "suspicious"
    SKIPPED = "skipped"
    SEGFAULT = "segfault"
    CAUGHT_BY_TYPE_CHECK = "caught by type check"
    NOT_CHECKED = "not checked"


_STATUS_RE = re.compile(r":\s*(" + "|".join(re.escape(s.value) for s in Status) + r")\s*$")
# Each mutmut mutant name ends with `__mutmut_<N>`. Stripping that yields the
# owning function (method names keep the `ǁClassǁmethod` segment).
_MUTANT_SUFFIX_RE = re.compile(r"__mutmut_\d+$")


def _run_results() -> str:
    """The saved mutmut state, or an empty report if there is none to read.

    This runs even when the mutmut step failed or was cut short, so a missing or
    unreadable state is a report saying nothing ran, not a second CI failure on top
    of the first.
    """
    # `--all true` is required: bare `mutmut results` only lists non-killed mutants,
    # which would understate the kill count.
    proc = subprocess.run(
        ["uv", "run", "mutmut", "results", "--all", "true"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        print(
            f"`mutmut results` exited {proc.returncode}; reporting an empty run.\n"
            f"{proc.stderr.strip()}",
            file=sys.stderr,
        )
        return ""
    return proc.stdout


def _parse_counts(text: str) -> dict[Status, int]:
    counts: dict[Status, int] = {s: 0 for s in Status}
    for line in text.splitlines():
        match = _STATUS_RE.search(line)
        if match:
            counts[Status(match.group(1))] += 1
    return counts


def _timeout_owners(text: str) -> Counter[str]:
    owners: Counter[str] = Counter()
    for line in text.splitlines():
        match = _STATUS_RE.search(line)
        if not match or match.group(1) != Status.TIMEOUT.value:
            continue
        mutant_name = line[: match.start()].strip()
        owner = _MUTANT_SUFFIX_RE.sub("", mutant_name)
        owners[owner] += 1
    return owners


def _score(counts: dict[Status, int]) -> float:
    denominator = counts[Status.KILLED] + counts[Status.SURVIVED]
    if denominator == 0:
        return 0.0
    return counts[Status.KILLED] / denominator


def _render_markdown(counts: dict[Status, int], score: float, timeouts: Counter[str]) -> str:
    tested = counts[Status.KILLED] + counts[Status.SURVIVED]
    lines = [
        "## Mutation testing report",
        "",
        f"**Score: {score:.1%}** ({counts[Status.KILLED]} killed / {tested} tested)",
        "",
    ]
    if counts[Status.NOT_CHECKED]:
        lines.extend(
            [
                f"> ⚠️ The run was cut short with {counts[Status.NOT_CHECKED]} mutants "
                "unchecked, so this score covers only the part that ran.",
                "",
            ]
        )
    lines.extend(
        [
            "| Status | Count |",
            "| --- | --- |",
            f"| 🎉 Killed | {counts[Status.KILLED]} |",
            f"| 🙁 Survived | {counts[Status.SURVIVED]} |",
            f"| 🫥 No tests | {counts[Status.NO_TESTS]} |",
            f"| ⏰ Timeout | {counts[Status.TIMEOUT]} |",
            f"| 🤔 Suspicious | {counts[Status.SUSPICIOUS]} |",
            f"| 🔇 Skipped | {counts[Status.SKIPPED]} |",
            f"| 💥 Segfault | {counts[Status.SEGFAULT]} |",
            f"| 🧙 Caught by type check | {counts[Status.CAUGHT_BY_TYPE_CHECK]} |",
            f"| ❓ Not checked | {counts[Status.NOT_CHECKED]} |",
            "",
        ]
    )
    if timeouts:
        lines.extend(
            [
                "### Timeout-prone functions",
                "",
                "Each timeout burns its whole budget (`timeout_multiplier` and "
                "`timeout_constant` in `pyproject.toml`) before mutmut kills it, so "
                "the functions below dominate wall-clock cost. Adding them to "
                "`do_not_mutate` is the fastest way to cut CI time.",
                "",
                "| Function | Timeouts |",
                "| --- | --- |",
            ]
        )
        for owner, count in timeouts.most_common():
            lines.append(f"| `{owner}` | {count} |")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    text = _run_results()
    counts = _parse_counts(text)
    score = _score(counts)
    timeouts = _timeout_owners(text)

    output_path = Path(os.environ.get("MUTMUT_SCORE_FILE", "mutation_score.md"))
    output_path.write_text(_render_markdown(counts, score, timeouts), encoding="utf-8")

    if timeouts:
        print("Timeout-prone functions:")
        for owner, count in timeouts.most_common():
            print(f"  {count:>4}  {owner}")

    threshold = float(os.environ.get("MUTATION_THRESHOLD", "0.0"))
    if score < threshold:
        print(
            f"Mutation score {score:.1%} is below threshold {threshold:.1%}",
            file=sys.stderr,
        )
        return 1

    print(f"Mutation score: {score:.1%} (threshold {threshold:.1%})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
