from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from interop.ports.errors import UserInputError
from interop.ports.inbound.overrides import NodeOverrides

# Mirrors the prompt-prefix convention `collect_node_params` uses
# (`source.<field>`, `step[0].<field>`, `sink[0].<field>`; prompts add a trailing `?`),
# so a headless --override key reads the same way the prompt it replaces did.
_SOURCE_FLAG_RE = re.compile(r"^source\.(\w+)$")
_STEP_FLAG_RE = re.compile(r"^step\[(\d+)\]\.(\w+)$")
_SINK_FLAG_RE = re.compile(r"^sink\[(\d+)\]\.(\w+)$")

_SOURCE_ENV_RE = re.compile(r"^INTEROP_OVERRIDE_SOURCE__(\w+)$")
_STEP_ENV_RE = re.compile(r"^INTEROP_OVERRIDE_STEP_(\d+)__(\w+)$")
_SINK_ENV_RE = re.compile(r"^INTEROP_OVERRIDE_SINK_(\d+)__(\w+)$")
_ENV_OVERRIDE_PREFIX = "INTEROP_OVERRIDE_"


class OverrideSyntaxError(UserInputError, ValueError):
    def __init__(self, raw: str) -> None:
        super().__init__(
            f"invalid override {raw!r}; expected 'source.<field>=<value>', "
            "'step[<n>].<field>=<value>', or 'sink[<n>].<field>=<value>' "
            "(or the INTEROP_OVERRIDE_SOURCE__/STEP_<n>__/SINK_<n>__ env var equivalents)"
        )


def parse_override_flags(raw_values: Sequence[str]) -> NodeOverrides:
    """Parse repeated --override KEY=VALUE flags into the TranslateUseCase override shapes."""
    parsed = NodeOverrides()
    for raw in raw_values:
        if "=" not in raw:
            raise OverrideSyntaxError(raw)
        key, value = raw.split("=", 1)
        if match := _SOURCE_FLAG_RE.match(key):
            parsed.source[match.group(1)] = value
        elif match := _STEP_FLAG_RE.match(key):
            parsed.steps.setdefault(int(match.group(1)), {})[match.group(2)] = value
        elif match := _SINK_FLAG_RE.match(key):
            parsed.sinks.setdefault(int(match.group(1)), {})[match.group(2)] = value
        else:
            raise OverrideSyntaxError(raw)
    return parsed


def parse_override_env(env: Mapping[str, str]) -> NodeOverrides:
    """Parse INTEROP_OVERRIDE_* environment variables into the same override shapes.

    Field names are lowercased because Windows upper-cases every environment
    variable name, so `INTEROP_OVERRIDE_SINK_0__path` arrives as `...__PATH`
    there and would otherwise name a field no params model has.
    """
    parsed = NodeOverrides()
    for env_key, value in env.items():
        if match := _SOURCE_ENV_RE.match(env_key):
            parsed.source[match.group(1).lower()] = value
        elif match := _STEP_ENV_RE.match(env_key):
            parsed.steps.setdefault(int(match.group(1)), {})[match.group(2).lower()] = value
        elif match := _SINK_ENV_RE.match(env_key):
            parsed.sinks.setdefault(int(match.group(1)), {})[match.group(2).lower()] = value
        elif env_key.startswith(_ENV_OVERRIDE_PREFIX):
            raise OverrideSyntaxError(env_key)
    return parsed


def merge_overrides(env_overrides: NodeOverrides, flag_overrides: NodeOverrides) -> NodeOverrides:
    """Merge env- and flag-sourced overrides; flag-sourced entries win on key collision."""
    return NodeOverrides(
        source={**env_overrides.source, **flag_overrides.source},
        steps=_merge_indexed(env_overrides.steps, flag_overrides.steps),
        sinks=_merge_indexed(env_overrides.sinks, flag_overrides.sinks),
    )


def _merge_indexed(
    env: dict[int, dict[str, Any]], flag: dict[int, dict[str, Any]]
) -> dict[int, dict[str, Any]]:
    return {idx: {**env.get(idx, {}), **flag.get(idx, {})} for idx in {*env, *flag}}
