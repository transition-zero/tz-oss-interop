from __future__ import annotations

from interop.ports.errors import UserInputError


class PluginCollisionError(UserInputError, RuntimeError):
    def __init__(self, category: str, name: str, first: str, second: str) -> None:
        super().__init__(
            f"Plugin name collision in {category!r}: {name!r} declared at {first} and {second}"
        )
        self.category = category
        self.name = name
        self.locations = (first, second)
