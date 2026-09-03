"""Compare two frameworks by running each side's results pipeline through translate.

Compare owns no framework knowledge: it runs each side's results pipeline into a
scratch results.parquet, reads both back as long-format tables (variable, component,
category, timestamp, value), diffs them at the finest granularity both sides share,
and renders a report. The narrative lives in docs/results-format.md.
"""

from __future__ import annotations

import io
import logging
import shutil
import tempfile
from pathlib import Path

import polars as pl

from interop.core.results_format import RESULTS_FRAMEWORK, ResultsCol, ResultsVariable
from interop.ports.errors import UserInputError
from interop.ports.inbound.compare import CompareResult, CompareSide, CompareUseCase
from interop.ports.inbound.overrides import NodeOverrides
from interop.ports.inbound.pipeline_catalog import (
    FrameworkName,
    PipelineCatalogUseCase,
    PipelineName,
)
from interop.ports.inbound.translate import TranslateUseCase
from interop.ports.outbound.comparison_report import (
    ComparisonData,
    ComparisonReportPort,
    RollupRow,
    SideSummary,
    VariableCoverage,
)
from interop.ports.outbound.filesystem import FilesystemPort

log = logging.getLogger(__name__)


# The results table is emitted as this parquet file inside the sink's output_dir.
_RESULTS_PARQUET = "results.parquet"

_OUTPUT_DIR_PARAM = "output_dir"
_SIDE_B_SUFFIX = "_side_b"
_DIFF_COL = "abs_diff"
_CATEGORY_KEY = "category_key"

# Coverage label for a variable a side reports with neither a component nor a category
# (a system total such as surplus or load), so the gap is visible rather than blank.
_SYSTEM_LABEL = "(system)"


_MIN_COMPARABLE_FRAMEWORKS = 2

# The variable column's full set of names, which both sides are read onto.
_EVERY_VARIABLE = pl.Enum([variable.value for variable in ResultsVariable])


class CompareUsingPort(CompareUseCase):
    def __init__(
        self,
        translate: TranslateUseCase,
        report: ComparisonReportPort,
        fs: FilesystemPort,
        catalog: PipelineCatalogUseCase,
    ) -> None:
        self._translate = translate
        self._report = report
        self._fs = fs
        self._catalog = catalog

    def comparable_frameworks(self) -> dict[FrameworkName, list[PipelineName]]:
        pipelines_by_framework = self._catalog.results_pipelines_by_framework()
        if len(pipelines_by_framework) < _MIN_COMPARABLE_FRAMEWORKS:
            configured = ", ".join(sorted(pipelines_by_framework)) or "none"
            raise UserInputError(
                "compare needs results pipelines for at least two frameworks; "
                f"only {configured} configured"
            )
        return pipelines_by_framework

    def __call__(
        self,
        side_a: CompareSide,
        side_b: CompareSide,
        output_path: Path,
    ) -> CompareResult:
        if side_a.framework == side_b.framework:
            raise UserInputError(
                f"compare needs two different frameworks; both sides are {side_a.framework!r}"
            )
        log.debug(
            "compare side_a=%s (%s) side_b=%s (%s) output=%s",
            side_a.framework,
            side_a.pipeline,
            side_b.framework,
            side_b.pipeline,
            output_path,
        )
        table_a = self._run_side(side_a)
        table_b = self._run_side(side_b)

        diffs = _get_diff_at_finest_shared_grain(table_a, table_b)
        data = ComparisonData(
            side_a=_side_summary(side_a.framework, table_a),
            side_b=_side_summary(side_b.framework, table_b),
            snapshots_aligned=_snapshots_aligned(table_a, table_b),
            coverage=_coverage(table_a, table_b),
            rollup=_rollup(diffs),
            n_diffs=diffs.height,
        )
        self._report.render(data, output_path)
        return CompareResult(output_path=output_path, n_diffs=diffs.height)

    def _run_side(self, side: CompareSide) -> pl.DataFrame:
        scratch = Path(tempfile.mkdtemp(prefix="interop-compare-"))
        try:
            self._translate(
                side.framework,
                RESULTS_FRAMEWORK,
                side.pipeline,
                overrides=NodeOverrides(
                    source=side.source_params, sinks={0: {_OUTPUT_DIR_PARAM: str(scratch)}}
                ),
            )
            raw = self._fs.read_bytes(scratch / _RESULTS_PARQUET)
            return _naming_every_variable(pl.read_parquet(io.BytesIO(raw)))
        finally:
            shutil.rmtree(scratch, ignore_errors=True)


def _naming_every_variable(table: pl.DataFrame) -> pl.DataFrame:
    """Give both sides a variable column that knows every variable, not only its own.

    A side reporting no price writes a column that has never held one, and two columns
    knowing different variables can be neither joined nor filtered against each other.
    """
    return table.with_columns(
        pl.col(ResultsCol.VARIABLE.value).cast(pl.String).cast(_EVERY_VARIABLE)
    )


def _side_summary(framework: str, table: pl.DataFrame) -> SideSummary:
    return SideSummary(
        framework=framework,
        n_rows=table.height,
        objective=_objective(table),
    )


def _objective(table: pl.DataFrame) -> float | None:
    # None is expected, not an error: a side can be a dataset lifted from a published
    # report rather than a model we solved ourselves, and such a dataset need not carry
    # an objective cost.
    rows = table.filter(pl.col(ResultsCol.VARIABLE.value) == ResultsVariable.OBJECTIVE.value)
    if rows.height == 0:
        return None
    return float(rows[ResultsCol.VALUE.value][0])


def _snapshots_aligned(table_a: pl.DataFrame, table_b: pl.DataFrame) -> bool:
    return _timestamps(table_a) == _timestamps(table_b)


def _timestamps(table: pl.DataFrame) -> set[object]:
    return set(table[ResultsCol.TIMESTAMP.value].drop_nulls().to_list())


def _coverage(table_a: pl.DataFrame, table_b: pl.DataFrame) -> list[VariableCoverage]:
    variables = sorted(
        set(table_a[ResultsCol.VARIABLE.value].to_list())
        | set(table_b[ResultsCol.VARIABLE.value].to_list())
    )
    coverage: list[VariableCoverage] = []
    for variable in variables:
        labels_a = _list_coverage_labels(table_a, variable)
        labels_b = _list_coverage_labels(table_b, variable)
        common = labels_a & labels_b
        coverage.append(
            VariableCoverage(
                variable=variable,
                n_side_a=len(labels_a),
                n_side_b=len(labels_b),
                n_common=len(common),
                only_side_a=sorted(labels_a - labels_b),
                only_side_b=sorted(labels_b - labels_a),
            )
        )
    return coverage


def _list_coverage_labels(table: pl.DataFrame, variable: str) -> set[str]:
    rows = table.filter(pl.col(ResultsCol.VARIABLE.value) == variable)
    if rows.height == 0:
        return set()
    components = set(rows[ResultsCol.COMPONENT.value].drop_nulls().to_list())
    if components:
        return components
    categories = set(rows[ResultsCol.CATEGORY.value].drop_nulls().to_list())
    if categories:
        return categories
    return {_SYSTEM_LABEL}


def _get_diff_at_finest_shared_grain(table_a: pl.DataFrame, table_b: pl.DataFrame) -> pl.DataFrame:
    compared_by_category = _select_variables_either_side_reports_without_a_component(
        table_a, table_b
    )

    component_grain_a = _drop_rows_for_variables(table_a, compared_by_category)
    component_grain_b = _drop_rows_for_variables(table_b, compared_by_category)
    category_grain_a = _keep_rows_for_variables(table_a, compared_by_category)
    category_grain_b = _keep_rows_for_variables(table_b, compared_by_category)

    diffs_by_component = _diff_matching_components(component_grain_a, component_grain_b)
    diffs_by_category = _diff_after_summing_to_category(category_grain_a, category_grain_b)
    return pl.concat([diffs_by_component, diffs_by_category], how="vertical")


def _select_variables_either_side_reports_without_a_component(
    table_a: pl.DataFrame, table_b: pl.DataFrame
) -> set[str]:
    all_variables = set(table_a[ResultsCol.VARIABLE.value].to_list()) | set(
        table_b[ResultsCol.VARIABLE.value].to_list()
    )
    return {
        variable
        for variable in all_variables
        if not (_reports_a_component(table_a, variable) and _reports_a_component(table_b, variable))
    }


def _reports_a_component(table: pl.DataFrame, variable: str) -> bool:
    rows_with_a_component = table.filter(
        (pl.col(ResultsCol.VARIABLE.value) == variable)
        & pl.col(ResultsCol.COMPONENT.value).is_not_null()
    )
    return rows_with_a_component.height > 0


def _keep_rows_for_variables(table: pl.DataFrame, variables: set[str]) -> pl.DataFrame:
    return table.filter(pl.col(ResultsCol.VARIABLE.value).is_in(list(variables)))


def _drop_rows_for_variables(table: pl.DataFrame, variables: set[str]) -> pl.DataFrame:
    return table.filter(~pl.col(ResultsCol.VARIABLE.value).is_in(list(variables)))


def _diff_matching_components(table_a: pl.DataFrame, table_b: pl.DataFrame) -> pl.DataFrame:
    on = [ResultsCol.VARIABLE.value, ResultsCol.COMPONENT.value, ResultsCol.TIMESTAMP.value]
    matched = table_a.join(table_b, on=on, how="inner", suffix=_SIDE_B_SUFFIX)
    category = pl.col(ResultsCol.CATEGORY.value)
    category_b = pl.col(f"{ResultsCol.CATEGORY.value}{_SIDE_B_SUFFIX}")
    return matched.with_columns(
        _absolute_value_difference(),
        pl.coalesce([category, category_b]).alias(_CATEGORY_KEY),
    ).select([ResultsCol.VARIABLE.value, _CATEGORY_KEY, _DIFF_COL])


def _diff_after_summing_to_category(table_a: pl.DataFrame, table_b: pl.DataFrame) -> pl.DataFrame:
    on = [ResultsCol.VARIABLE.value, ResultsCol.CATEGORY.value, ResultsCol.TIMESTAMP.value]
    matched = _sum_each_timestamp_to_category(table_a).join(
        _sum_each_timestamp_to_category(table_b),
        on=on,
        how="inner",
        suffix=_SIDE_B_SUFFIX,
        nulls_equal=True,
    )
    return matched.with_columns(
        _absolute_value_difference(),
        pl.col(ResultsCol.CATEGORY.value).alias(_CATEGORY_KEY),
    ).select([ResultsCol.VARIABLE.value, _CATEGORY_KEY, _DIFF_COL])


def _sum_each_timestamp_to_category(table: pl.DataFrame) -> pl.DataFrame:
    # Dropping null-timestamp rows before grouping leaves the scalar objective (all
    # dimensions null) out of the category diff, where it would otherwise self-match.
    return (
        table.filter(pl.col(ResultsCol.TIMESTAMP.value).is_not_null())
        .group_by(
            [ResultsCol.VARIABLE.value, ResultsCol.CATEGORY.value, ResultsCol.TIMESTAMP.value]
        )
        .agg(pl.col(ResultsCol.VALUE.value).sum())
    )


def _absolute_value_difference() -> pl.Expr:
    value_a = pl.col(ResultsCol.VALUE.value)
    value_b = pl.col(f"{ResultsCol.VALUE.value}{_SIDE_B_SUFFIX}")
    return (value_a - value_b).abs().alias(_DIFF_COL)


def _rollup(joined: pl.DataFrame) -> list[RollupRow]:
    if joined.height == 0:
        return []
    grouped = (
        joined.group_by([ResultsCol.VARIABLE.value, _CATEGORY_KEY])
        .agg(
            pl.len().alias("n"),
            pl.col(_DIFF_COL).mean().alias("mae"),
            (pl.col(_DIFF_COL).pow(2).mean().sqrt()).alias("rmse"),
        )
        .sort([ResultsCol.VARIABLE.value, _CATEGORY_KEY], nulls_last=True)
    )
    return [
        RollupRow(
            variable=str(row[ResultsCol.VARIABLE.value]),
            category=row[_CATEGORY_KEY],
            n=int(row["n"]),
            mae=float(row["mae"]),
            rmse=float(row["rmse"]),
        )
        for row in grouped.iter_rows(named=True)
    ]
