"""The whole pytest-bdd step vocabulary, loadable as one pytest plugin.

    pytest_plugins = ["interop_testing.steps"]

in the conftest beside your ``testpaths`` (pytest rejects ``pytest_plugins`` in
a conftest deeper in the tree) registers every module below. List modules
individually instead if a project wants only part of the vocabulary — a project
that never touches Plexos need not register its words.
"""

pytest_plugins = [
    "interop_testing.steps.isolation",
    "interop_testing.steps.files",
    "interop_testing.steps.pipeline",
    "interop_testing.steps.reports",
    "interop_testing.steps.pypsa_network",
    "interop_testing.steps.caiso_stack_model",
    "interop_testing.steps.sienna_system",
    "interop_testing.steps.sienna_results",
    "interop_testing.steps.osemosys_model",
    "interop_testing.steps.plexos_model",
    "interop_testing.steps.plexos_resources",
    "interop_testing.steps.power_simulations",
]
