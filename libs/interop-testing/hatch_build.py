"""Pin the tz-oss-interop requirement to the version of this build.

hatch-vcs derives both distributions' versions from the same git tag. This hook
reads the version hatchling has already resolved and writes the requirement, so
no file states a version and the two can never disagree.
"""

from typing import Any

from hatchling.metadata.plugin.interface import MetadataHookInterface

LIBRARY = "tz-oss-interop"


class LibraryPinMetadataHook(MetadataHookInterface):
    """Put `tz-oss-interop==<this build's version>` in front of the dependencies."""

    PLUGIN_NAME = "custom"

    def update(self, metadata: dict[Any, Any]) -> None:
        pin = f"{LIBRARY}=={metadata['version']}"
        metadata["dependencies"] = [pin, *self.config["dependencies"]]
