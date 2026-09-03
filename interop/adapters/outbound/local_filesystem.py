from __future__ import annotations

import shutil
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import IO, ClassVar

from pydantic import BaseModel

from interop.ports.outbound.filesystem import FilesystemPort, Location


def _require_path(path: Location) -> Path:
    # local_filesystem should never receive a URL: that would mean the
    # wrong FilesystemPort adapter is bound (should be http_filesystem
    # instead). Fail loudly here rather than letting _resolve's Path-only
    # logic (.is_absolute(), joining onto self._root) fail confusingly.
    if isinstance(path, str):
        raise TypeError(
            f"local_filesystem received a non-Path location ({path!r}); "
            "did you mean to bind a different filesystem adapter?"
        )
    return path


class LocalFilesystemConfig(BaseModel):
    root: Path | None = None


class LocalFilesystem(FilesystemPort):
    name: ClassVar[str] = "local_filesystem"
    port: ClassVar[type] = FilesystemPort
    config_schema: ClassVar[type[BaseModel] | None] = LocalFilesystemConfig

    def __init__(self, config: LocalFilesystemConfig | None = None) -> None:
        self._root = config.root if config else None

    def read_bytes(self, path: Location) -> bytes:
        return self._resolve(_require_path(path)).read_bytes()

    def write_bytes(self, path: Location, data: bytes) -> Location:
        target = self._resolve(_require_path(path))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return target

    @contextmanager
    def open_read(self, path: Location) -> Generator[IO[bytes], None, None]:
        with open(self._resolve(_require_path(path)), "rb") as f:
            yield f

    @contextmanager
    def open_write(self, path: Location) -> Generator[IO[bytes], None, None]:
        target = self._resolve(_require_path(path))
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w+b") as f:
            yield f

    def copy_tree(self, src: Location, dst: Location) -> None:
        shutil.copytree(
            self._resolve(_require_path(src)), self._resolve(_require_path(dst)), dirs_exist_ok=True
        )

    def can_read(self, path: Location) -> bool:
        return self._resolve(_require_path(path)).is_file()

    def resolve(self, base: Location, relative: str) -> Location:
        # PLEXOS-style relative paths are Windows-style and sit beside the input file.
        return _require_path(base).parent / relative.replace("\\", "/")

    def locate(self, path: Location) -> Location:
        return self._resolve(_require_path(path))

    def _resolve(self, path: Path) -> Path:
        if self._root is None or path.is_absolute():
            return path
        return self._root / path
