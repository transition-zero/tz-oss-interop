"""Helpers that scaffold an interop project directory from a test.

Every helper writes relative to the current working directory, which is where
plugin and pipeline discovery looks. Combine them with the ``isolated_cwd``
fixture from ``interop_testing.steps.isolation`` so each test gets an empty
project of its own.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from interop.core.runner import RESULTS_SUBDIR

# `load_adapters_config` raises when adapters.yaml is absent, so a project needs one
# before any run. This mirrors the file `interop init` writes.
DEFAULT_ADAPTERS_YAML = "bindings: {}\nadapters: {}\nobservability:\n  log_level: INFO\n"


def write_project_plugin(category: str, filename: str, source: str) -> None:
    """Write a project-local plugin to ``./plugins/<category>/<filename>.py``."""
    plugin_dir = Path.cwd() / "plugins" / category
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / f"{filename}.py").write_text(source, encoding="utf-8")


def write_project_plugin_in_subdir(category: str, subdir: str, filename: str, source: str) -> None:
    """Write a project-local plugin one directory deeper, to exercise nested discovery."""
    plugin_dir = Path.cwd() / "plugins" / category / subdir
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / f"{filename}.py").write_text(source, encoding="utf-8")


def write_pipeline(name: str, yaml_body: str) -> None:
    """Write a pipeline definition to ``./pipelines/<name>.yaml``."""
    pipeline_path = Path.cwd() / "pipelines" / f"{name}.yaml"
    pipeline_path.parent.mkdir(parents=True, exist_ok=True)
    pipeline_path.write_text(yaml_body, encoding="utf-8")


def write_results_pipeline(name: str, yaml_body: str) -> None:
    """Write a results pipeline to ``./pipelines/results/<name>.yaml``.

    Interop only looks for results pipelines in that subdirectory.
    """
    write_pipeline(f"{RESULTS_SUBDIR}/{name}", yaml_body)


_NOOP_PIPELINE_HEADER = """\
source_framework: noop
destination_framework: noop
source:
  name: noop
sinks:
  - name: noop
"""


def _render_node_list(key: str, names: Sequence[str]) -> str:
    if not names:
        return ""
    entries = "\n".join(f"  - name: {name}" for name in names)
    return f"{key}:\n{entries}\n"


def write_noop_pipeline(name: str, step_names: Sequence[str]) -> None:
    """Write a pipeline with the noop source and sink and the named steps, in order."""
    write_pipeline(name, _NOOP_PIPELINE_HEADER + _render_node_list("steps", step_names))


def write_noop_validator_pipeline(name: str, validator_names: Sequence[str]) -> None:
    """Write a pipeline with the noop source and sink and the named validators."""
    write_pipeline(name, _NOOP_PIPELINE_HEADER + _render_node_list("validators", validator_names))


def write_adapters_config(yaml_body: str) -> None:
    """Write ``./adapters.yaml``, replacing whatever is there."""
    (Path.cwd() / "adapters.yaml").write_text(yaml_body, encoding="utf-8")
