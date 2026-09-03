from __future__ import annotations

import shutil
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from http import HTTPStatus
from typing import IO, ClassVar

import requests
from pydantic import BaseModel

from interop.ports.outbound.filesystem import FilesystemPort, Location


class HttpFilesystemConfig(BaseModel):
    # No URLs or auth here by design: signed URLs arrive per-call as
    # source/sink override params (see ADR: per-job configuration &
    # least-privilege scoping), not as static adapter config. Every field
    # here must default safely, since adapters.yaml may omit this block
    # entirely (see make_adapter_factory: configs.get(name, {})).
    timeout_seconds: float = 30.0


class HttpFilesystem(FilesystemPort):
    name: ClassVar[str] = "http_filesystem"
    port: ClassVar[type] = FilesystemPort
    config_schema: ClassVar[type[BaseModel] | None] = HttpFilesystemConfig

    def __init__(self, config: HttpFilesystemConfig | None = None) -> None:
        config = config or HttpFilesystemConfig()
        self._timeout = config.timeout_seconds

    def read_bytes(self, path: Location) -> bytes:
        response = requests.get(str(path), timeout=self._timeout)
        response.raise_for_status()
        return response.content

    def write_bytes(self, path: Location, data: bytes) -> Location:
        response = requests.put(str(path), data=data, timeout=self._timeout)
        response.raise_for_status()
        return path

    def can_read(self, path: Location) -> bool:
        # Only a 404 answers the question asked. A server may refuse HEAD outright (405,
        # 501) or gate it differently from GET (403), and a transport error says nothing
        # either, so anything else answers yes and lets the GET report the real failure.
        # Saying no here would refuse a file open_read would have fetched, which is the
        # false refusal this method exists to end.
        try:
            response = requests.head(str(path), timeout=self._timeout, allow_redirects=True)
        except requests.RequestException:
            return True
        return response.status_code != HTTPStatus.NOT_FOUND

    @contextmanager
    def open_read(self, path: Location) -> Generator[IO[bytes], None, None]:
        # h5py needs a seekable handle; a raw HTTP response stream isn't
        # seekable, so spool the full body to a temp file first.
        response = requests.get(str(path), stream=True, timeout=self._timeout)
        response.raise_for_status()
        with tempfile.TemporaryFile() as tmp:
            shutil.copyfileobj(response.raw, tmp)
            tmp.seek(0)
            yield tmp

    @contextmanager
    def open_write(self, path: Location) -> Generator[IO[bytes], None, None]:
        # Mirror of open_read: write into a local temp file, then PUT the
        # whole thing on successful exit. HTTP uploads are append-only, so
        # streaming writes directly to the connection isn't an option, and
        # h5py needs a seekable handle to write into in the first place.
        # If the caller's block raises, the exception propagates through this
        # yield before the PUT below is ever reached — no partial/garbage
        # upload lands at the destination on failure.
        with tempfile.TemporaryFile() as tmp:
            yield tmp
            tmp.seek(0)
            response = requests.put(str(path), data=tmp, timeout=self._timeout)
            response.raise_for_status()

    def resolve(self, base: Location, relative: str) -> Location:
        # Join the relative reference onto the base URL's directory.
        normalised = relative.replace("\\", "/")
        return f"{str(base).rsplit('/', 1)[0]}/{normalised}"

    def locate(self, path: Location) -> Location:
        return path

    def copy_tree(self, src: Location, dst: Location) -> None:
        # Only called by init_project_use_case, which hardcodes
        # LocalFilesystem directly and never resolves this adapter from the
        # registry (see container.py: init bootstraps adapters.yaml itself,
        # so it can't depend on a configured FilesystemPort). No code path
        # on the translate route calls copy_tree, so this is intentionally
        # unimplemented rather than inventing HTTP tree-copy semantics
        # nothing exercises.
        raise NotImplementedError(
            "http_filesystem does not support copy_tree; it is only used by "
            "init, which does not use this adapter"
        )
