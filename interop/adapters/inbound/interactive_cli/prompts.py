"""What the prompts of every command share: how a user error is printed, and how a recorded
answer becomes the default of a select."""

from __future__ import annotations

from typing import Any

import questionary

from interop.ports.errors import UserInputError


def print_user_error(exc: UserInputError) -> None:
    questionary.print(str(exc), style="fg:red")


def choose_select_default(value: Any, options: list[str]) -> str | None:
    """A recorded answer is only usable as a select default if it is still a choice."""
    if isinstance(value, str) and value in options:
        return value
    return None
