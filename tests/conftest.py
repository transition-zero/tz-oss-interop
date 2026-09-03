# pytest_plugins must be declared in the rootdir conftest; nested conftests raise.
# Everything the harness publishes — project scaffolding, the pipeline driver, and each
# framework's builder and assertion vocabulary — arrives through this one entry, the
# same way a downstream project registers it.
pytest_plugins = ["interop_testing.steps", "tests.step_defs.plugin_fixtures"]
