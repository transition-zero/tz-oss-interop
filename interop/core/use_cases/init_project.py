from __future__ import annotations

import logging
from importlib.resources import as_file, files
from importlib.resources.abc import Traversable
from pathlib import Path

from interop.ports.inbound.init_project import (
    Example,
    InitProjectUseCase,
    TargetDirectoryNotEmptyError,
)
from interop.ports.outbound.filesystem import FilesystemPort

log = logging.getLogger(__name__)

_TEMPLATES = files("interop") / "templates"
_SKELETON = _TEMPLATES / "init"
_EXAMPLES = _TEMPLATES / "examples"


class InitializeProjectDirectory(InitProjectUseCase):
    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def __call__(self, target: Path, example: Example = Example.NONE) -> None:
        if target.is_dir() and any(target.iterdir()):
            raise TargetDirectoryNotEmptyError(target)

        log.debug("init project target=%s example=%s", target, example)
        target.mkdir(parents=True, exist_ok=True)

        self._copy_template(_SKELETON, target)
        self._copy_template(_EXAMPLES / example.value, target)

    def _copy_template(self, template: Traversable, target: Path) -> None:
        with as_file(template) as src:
            self._fs.copy_tree(src, target)
