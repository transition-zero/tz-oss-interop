from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import IO, Annotated, ClassVar, Protocol, runtime_checkable

from pydantic import BeforeValidator


# Public (not _to_location): app.py's REPL also needs this exact
# URL-vs-local-path decision when converting a typed prompt answer, so the
# logic is centralized here rather than duplicated.
def to_location(value: Path | str) -> Location:
    if isinstance(value, str) and "://" in value:
        return value  # URL — leave as string, untouched
    return Path(value)  # local-style — normalize to a real Path


# Annotated + BeforeValidator, not a bare `Path | str`: pydantic's smart-union
# validation would otherwise leave an ordinary local path as a plain `str`
# (since `str` already matches), silently skipping the Path coercion below.
Location = Annotated[Path | str, BeforeValidator(to_location)]


# Public (not _location_name): shared by multiple sinks that need to extract
# a bare filename from a Location, same reasoning as `to_location` above.
def location_name(loc: Location) -> str:
    if isinstance(loc, str):
        return loc.rsplit("/", 1)[-1]
    return loc.name


class OutputDirectoryMarker:
    """Annotation marker for a pydantic ``Path`` field that names an output directory.

    Sinks that fan a system out into one file per component (rather than a single
    file) take a directory. The write path is created on write, so the field is a
    directory to populate, not a file to overwrite.
    """


OutputDirectory = Annotated[Path, OutputDirectoryMarker()]


class InputFileMarker:
    """Annotation marker for a field naming a file a source reads.

    Not pydantic's ``FilePath``, which resolves against the working directory. A leg of a
    chain is handed a path relative to the hand-off directory its port knows about, and a
    remote path is not on local disk at all, so only the port can answer whether the file
    is there. The marker keeps the prompt asking for a file that exists, where the working
    directory genuinely is the right place to look.
    """


InputFile = Annotated[Path | str, BeforeValidator(to_location), InputFileMarker()]


class InputDirectoryMarker:
    """Annotation marker for a field naming a directory a source reads.

    Not pydantic's ``DirectoryPath``, which resolves against the working directory: a leg of
    a chain is handed a path relative to the hand-off directory its port knows about, so the
    existence check would fail every chained run. Same reasoning as ``InputFileMarker``.
    """


InputDirectory = Annotated[Path, InputDirectoryMarker()]


# Told where a write landed and how large it was, by a port that reports its writes.
OnWrite = Callable[[Location, int], None]


@runtime_checkable
class FilesystemPort(Protocol):
    name: ClassVar[str]

    def read_bytes(self, path: Location) -> bytes: ...
    def write_bytes(self, path: Location, data: bytes) -> Location: ...
    def open_read(self, path: Location) -> AbstractContextManager[IO[bytes]]: ...
    def open_write(self, path: Location) -> AbstractContextManager[IO[bytes]]: ...
    def copy_tree(self, src: Location, dst: Location) -> None: ...
    # Whether `open_read` would find something to read. Only the port can answer: it holds
    # the root a relative path resolves against, and whether that root is even local.
    def can_read(self, path: Location) -> bool: ...
    # Where `path` actually lands, for a port that resolves it against a root.
    # `open_write` cannot report this itself, and a caller naming the file afterwards
    # (a run summary, a hand-off another leg reads) needs the resolved location.
    def locate(self, path: Location) -> Location: ...
    # Resolve a sibling resource named relative to `base` (e.g. a CSV referenced
    # by an input file), so callers never join paths behind the port's back.
    def resolve(self, base: Location, relative: str) -> Location: ...
