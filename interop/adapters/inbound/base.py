from __future__ import annotations

from typing import ClassVar, Protocol, runtime_checkable

from dishka import Container


@runtime_checkable
class Launcher(Protocol):
    name: ClassVar[str]

    def run(self, container: Container) -> None: ...
