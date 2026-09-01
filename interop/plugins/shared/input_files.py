"""Finding one input file among the names it can be filed under.

``FilesystemPort`` lists no directory, so a source that accepts more than one name for the
same file asks the port about each name in turn.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from interop.ports.outbound.filesystem import FilesystemPort


def read_first_readable(
    fs: FilesystemPort, folder: Path, file_names: Sequence[str]
) -> bytes | None:
    """The bytes of the first of these files the folder holds, or None if it holds none."""
    for file_name in file_names:
        if fs.can_read(folder / file_name):
            return fs.read_bytes(folder / file_name)
    return None
