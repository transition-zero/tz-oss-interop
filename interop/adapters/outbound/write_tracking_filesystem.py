from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import IO, ClassVar

from interop.ports.outbound.filesystem import FilesystemPort, Location, OnWrite


class WriteTrackingFilesystem(FilesystemPort):
    """Passes every call to the filesystem it wraps, and reports each write to `on_write`."""

    name: ClassVar[str] = "write_tracking_filesystem"
    port: ClassVar[type] = FilesystemPort

    def __init__(self, inner: FilesystemPort, on_write: OnWrite) -> None:
        self._inner = inner
        self._on_write = on_write

    def read_bytes(self, path: Location) -> bytes:
        return self._inner.read_bytes(path)

    def write_bytes(self, path: Location, data: bytes) -> Location:
        written = self._inner.write_bytes(path, data)
        self._on_write(written, len(data))
        return written

    @contextmanager
    def open_read(self, path: Location) -> Generator[IO[bytes], None, None]:
        with self._inner.open_read(path) as f:
            yield f

    @contextmanager
    def open_write(self, path: Location) -> Generator[IO[bytes], None, None]:
        with self._inner.open_write(path) as f:
            yield f
            f.seek(0, 2)
            size = f.tell()
        self._on_write(self._inner.locate(path), size)

    def copy_tree(self, src: Location, dst: Location) -> None:
        self._inner.copy_tree(src, dst)

    def can_read(self, path: Location) -> bool:
        return self._inner.can_read(path)

    def resolve(self, base: Location, relative: str) -> Location:
        return self._inner.resolve(base, relative)

    def locate(self, path: Location) -> Location:
        return self._inner.locate(path)
