from interop_testing import write_adapters_config
from pytest_bdd import given, parsers, scenarios

scenarios("../features/adapters_config.feature")


@given(parsers.parse('I add an adapters.yaml binding filesystem to "{adapter_name}"'))
def given_add_adapters_yaml_binding(adapter_name: str) -> None:
    write_adapters_config(f"bindings:\n  filesystem: {adapter_name}\n")


@given(parsers.parse('I add an adapters.yaml with raw content "{content}"'))
def given_add_adapters_yaml_raw(content: str) -> None:
    write_adapters_config(content)


@given("I add an adapters.yaml that gives local_filesystem an invalid root config")
def given_bad_local_filesystem_config() -> None:
    write_adapters_config(
        "bindings:\n"
        "  filesystem: local_filesystem\n"
        "adapters:\n"
        "  local_filesystem:\n"
        "    root:\n"
        "      - not\n"
        "      - a\n"
        "      - valid\n"
        "      - path\n"
    )
