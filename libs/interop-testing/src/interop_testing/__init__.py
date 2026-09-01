"""Test harness for projects that build interop pipelines.

Installed with the ``testing`` extra (``uv add "interop-testing"``). It
publishes the fixture builders for every framework interop reads or writes, the
helpers that scaffold a project directory, and a driver that runs one pipeline
in-process. ``interop_testing.steps`` holds the matching pytest-bdd vocabulary,
so a project can write ``.feature`` files against its own pipelines without
copying any of this.

``interop_testing.builders`` holds one importable module per framework behind its
step module, so a project needing an assertion the vocabulary does not cover can
read the artefact with the same helpers rather than parsing it afresh.
"""

from interop_testing.builders.caiso_stack_models import CaisoStackModelBuilder
from interop_testing.builders.osemosys_models import OsemosysModelBuilder, ParameterSpec
from interop_testing.builders.plexos_models import PlexosModelBuilder
from interop_testing.builders.pypsa_networks import PyPSANetworkBuilder, read_network
from interop_testing.builders.sienna_results import SiennaResultsBuilder
from interop_testing.builders.sienna_systems import SiennaSystemBuilder
from interop_testing.pipeline_driver import run_pipeline
from interop_testing.projects import (
    DEFAULT_ADAPTERS_YAML,
    write_adapters_config,
    write_noop_pipeline,
    write_noop_validator_pipeline,
    write_pipeline,
    write_project_plugin,
    write_project_plugin_in_subdir,
    write_results_pipeline,
)

__all__ = [
    "DEFAULT_ADAPTERS_YAML",
    "CaisoStackModelBuilder",
    "OsemosysModelBuilder",
    "ParameterSpec",
    "PlexosModelBuilder",
    "PyPSANetworkBuilder",
    "SiennaResultsBuilder",
    "SiennaSystemBuilder",
    "read_network",
    "run_pipeline",
    "write_adapters_config",
    "write_noop_pipeline",
    "write_noop_validator_pipeline",
    "write_pipeline",
    "write_project_plugin",
    "write_project_plugin_in_subdir",
    "write_results_pipeline",
]
