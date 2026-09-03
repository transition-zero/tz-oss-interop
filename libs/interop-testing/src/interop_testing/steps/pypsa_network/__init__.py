"""pytest-bdd vocabulary for PyPSA networks, as a pipeline's input and its output.

Load with ``pytest_plugins = ["interop_testing.steps.pypsa_network"]`` (or the
whole vocabulary via ``"interop_testing.steps"``). The Given steps in
``build_network`` grow a network through the ``pypsa_network_builder`` fixture
that ``Given a PyPSA network`` creates; the Then steps in ``assert_network``
read a written network back off disk.
"""

# pytest-bdd registers a step by injecting a fixture into the globals of the module
# that declares it, so importing the step names here would register nothing.
pytest_plugins = [
    "interop_testing.steps.pypsa_network.build_network",
    "interop_testing.steps.pypsa_network.assert_network",
]
