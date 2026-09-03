from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class NodeOverrides:
    """The params a caller supplies on top of what the manifest says.

    Steps and sinks are keyed by position, matching the `step[0].field` form the REPL prompts
    and the headless `--override` flag both use.
    """

    source: dict[str, Any] = field(default_factory=dict)
    steps: dict[int, dict[str, Any]] = field(default_factory=dict)
    sinks: dict[int, dict[str, Any]] = field(default_factory=dict)
