from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Protocol, runtime_checkable

from interop.ports.errors import UserInputError


class Example(StrEnum):
    """Pre-built example a scaffold can be seeded from. NONE is the bare skeleton."""

    NONE = "none"
    PYPSA = "pypsa"


class TargetDirectoryNotEmptyError(UserInputError, ValueError):
    def __init__(self, target: Path) -> None:
        super().__init__(f"Target directory {target} exists and is not empty.")
        self.target = target


@runtime_checkable
class InitProjectUseCase(Protocol):
    def __call__(self, target: Path, example: Example = Example.NONE) -> None: ...
