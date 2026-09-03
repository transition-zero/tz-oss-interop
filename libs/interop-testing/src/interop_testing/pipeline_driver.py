"""Run a pipeline in-process, the way a test wants to run one."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from interop.adapters.inbound.headless_cli.app import run_headless
from interop.di.container import make_container


def run_pipeline(
    pipeline: str,
    *,
    overrides: Sequence[str] = (),
    user_mappings_path: str | None = None,
    keep_staging: bool = False,
    project_root: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> int:
    """Translate through `pipeline` headlessly and return the process exit code.

    Plugins and pipelines are discovered from `project_root`, defaulting to the
    current working directory, so a project's own `plugins/` and `pipelines/`
    are picked up. Each override is a headless `KEY=VALUE` string, for example
    `source.path=inputs/network.nc` or `sink[0].path=outputs/system.json`.

    Nothing is raised on failure: a bad pipeline, a rejected override, or a
    failing translate all come back as a non-zero exit code with the reason
    logged, which is what the command-line caller sees too.
    """
    argv = ["--pipeline", pipeline]
    for override in overrides:
        argv += ["--override", override]
    if user_mappings_path is not None:
        argv += ["--user-mappings-path", user_mappings_path]
    if keep_staging:
        argv.append("--keep-staging")
    return run_headless(make_container(project_root), argv, env or {})
