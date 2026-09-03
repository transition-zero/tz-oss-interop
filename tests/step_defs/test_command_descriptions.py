from pathlib import Path

import pytest
from pytest_bdd import parsers, scenarios, then, when

from tests.step_defs.conftest import capture_main_menu_labels

FEATURE = Path(__file__).resolve().parents[1] / "features" / "command_descriptions.feature"
scenarios(str(FEATURE))


@when("I open the main menu", target_fixture="menu_labels")
def when_open_main_menu(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    return capture_main_menu_labels(monkeypatch)


@then(parsers.parse('the menu shows "{description}" beside the "{command}" command'))
def then_menu_shows_description(menu_labels: list[str], description: str, command: str) -> None:
    matching = [label for label in menu_labels if label.startswith(command)]
    assert matching, f"no menu entry for {command!r} in {menu_labels!r}"
    label = matching[0]
    assert description in label, f"expected {description!r} beside {command!r}, got {label!r}"
