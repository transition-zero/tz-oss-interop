from __future__ import annotations

import logging
from importlib.resources import as_file, files
from pathlib import Path

from interop.ports.inbound.init_project import (
    Example,
    InitProjectUseCase,
    TargetDirectoryNotEmptyError,
)
from interop.ports.outbound.filesystem import FilesystemPort

log = logging.getLogger(__name__)


class InitializeProjectDirectory(InitProjectUseCase):
    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def __call__(self, target: Path, example: Example = Example.NONE) -> None:
        if target.is_dir() and any(target.iterdir()):
            raise TargetDirectoryNotEmptyError(target)

        log.debug("init project target=%s example=%s", target, example)
        target.mkdir(parents=True, exist_ok=True)

        with as_file(files("interop") / "templates" / "init") as src:
            self._fs.copy_tree(src, target)

        self._overlay_example(target, example)

    def _overlay_example(self, target: Path, example: Example) -> None:
        if example is Example.NONE:
            return
        with as_file(files("interop") / "templates" / "examples" / example.value) as src:
            self._fs.copy_tree(src, target)
        (target / "pipelines" / "example.yaml").unlink(missing_ok=True)
