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
        match example:
            case Example.NONE:
                return
            case Example.PYPSA:
                with as_file(files("interop") / "templates" / "examples" / "pypsa") as src:
                    self._fs.copy_tree(src, target)
                # The pypsa example ships its own pipeline; drop the bare
                # skeleton's noop placeholder so the project has just the one.
                (target / "pipelines" / "example.yaml").unlink(missing_ok=True)
