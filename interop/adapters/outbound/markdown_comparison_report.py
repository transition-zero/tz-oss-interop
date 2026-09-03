"""Markdown rendering adapter for two-sided comparison reports."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

from interop.ports.outbound.comparison_report import ComparisonData, ComparisonReportPort
from interop.ports.outbound.filesystem import FilesystemPort

_MISSING = "-"


class MarkdownComparisonReport(ComparisonReportPort):
    name: ClassVar[str] = "markdown_comparison_report"
    port: ClassVar[type] = ComparisonReportPort

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def render(self, data: ComparisonData, output_path: Path) -> None:
        side_a = data.side_a.framework
        side_b = data.side_b.framework
        lines: list[str] = [
            f"# {side_a} vs {side_b} results comparison\n",
            f"- Run timestamp (UTC): {datetime.now(UTC).isoformat(timespec='seconds')}",
            f"- `{side_a}`: {data.side_a.n_rows:,} rows",
            f"- `{side_b}`: {data.side_b.n_rows:,} rows",
            f"- Rows compared: {data.n_diffs:,}",
            "",
            "## Objective\n",
            "| side | framework | objective |",
            "| --- | --- | --- |",
            f"| A | {side_a} | {_objective(data.side_a.objective)} |",
            f"| B | {side_b} | {_objective(data.side_b.objective)} |",
            "",
            "## Snapshot alignment\n",
            (
                "Both sides cover the same snapshots.\n"
                if data.snapshots_aligned
                else "**Snapshots differ**; rows are joined over the shared timestamps only.\n"
            ),
            "## Coverage by variable\n",
        ]
        lines.append(f"| variable | {side_a} | {side_b} | common | only {side_a} | only {side_b} |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for cover in data.coverage:
            lines.append(
                f"| {cover.variable} | {cover.n_side_a} | {cover.n_side_b} | "
                f"{cover.n_common} | {_names(cover.only_side_a)} | {_names(cover.only_side_b)} |"
            )
        lines.append("")

        lines.append("## Error by variable and category\n")
        if not data.rollup:
            lines.append("_(no shared rows to compare)_\n")
        else:
            lines.append("| variable | category | n | MAE | RMSE |")
            lines.append("| --- | --- | --- | --- | --- |")
            for row in data.rollup:
                category = row.category if row.category is not None else _MISSING
                lines.append(
                    f"| {row.variable} | {category} | {row.n:,} | "
                    f"{row.mae:,.4g} | {row.rmse:,.4g} |"
                )
            lines.append("")

        self._fs.write_bytes(output_path, "\n".join(lines).encode("utf-8"))


def _objective(value: float | None) -> str:
    return f"{value:,.4f}" if value is not None else "(unavailable)"


def _names(names: list[str]) -> str:
    return ", ".join(names) if names else _MISSING
