"""Addressing a node's param within a pipeline, and reading or writing it.

`<node>.<param>` sets a value and `$<pipeline>.<node>.<param>` reads one. A node is
named by its plugin rather than its position, so reordering a pipeline's sinks cannot
silently rewire a chain.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from interop.core.composition.document import CompositionError
from interop.core.runner import NodeSpec, PipelineSpec

REFERENCE_PREFIX = "$"
_SEGMENT_SEPARATOR = "."
_REFERENCE_SEGMENTS = 3
_PARAM_ADDRESS_SEGMENTS = 2


@dataclass(frozen=True)
class ParamAddress:
    node: str
    param: str

    def __str__(self) -> str:
        return f"{self.node}{_SEGMENT_SEPARATOR}{self.param}"


@dataclass(frozen=True)
class Reference:
    """A `$<pipeline>.<node>.<param>` value, parsed."""

    pipeline: str
    address: ParamAddress

    def __str__(self) -> str:
        return f"{REFERENCE_PREFIX}{self.pipeline}{_SEGMENT_SEPARATOR}{self.address}"


def parse_reference(value: object) -> Reference | None:
    if not isinstance(value, str) or not value.startswith(REFERENCE_PREFIX):
        return None
    segments = value.removeprefix(REFERENCE_PREFIX).split(_SEGMENT_SEPARATOR)
    if len(segments) != _REFERENCE_SEGMENTS or not all(segments):
        raise CompositionError(
            f"Malformed reference {value!r}; expected '{REFERENCE_PREFIX}<pipeline>.<node>.<param>'"
        )
    pipeline, node, param = segments
    return Reference(pipeline=pipeline, address=ParamAddress(node=node, param=param))


def parse_param_address(key: str) -> ParamAddress:
    segments = key.split(_SEGMENT_SEPARATOR)
    if len(segments) != _PARAM_ADDRESS_SEGMENTS or not all(segments):
        raise CompositionError(f"Malformed param key {key!r}; expected '<node>.<param>'")
    return ParamAddress(node=segments[0], param=segments[1])


def nodes_of(spec: PipelineSpec) -> list[NodeSpec]:
    return [spec.source, *spec.steps, *spec.sinks]


def find_node(pipeline: str, spec: PipelineSpec, node: str) -> NodeSpec:
    nodes = nodes_of(spec)
    matching = [candidate for candidate in nodes if candidate.name == node]
    if len(matching) > 1:
        raise CompositionError(
            f"Pipeline {pipeline!r} has more than one node named {node!r}, so it cannot be "
            "addressed by name. Give the duplicated nodes distinct plugins."
        )
    if not matching:
        available = sorted(candidate.name for candidate in nodes)
        raise CompositionError(
            f"Pipeline {pipeline!r} has no node named {node!r}. Available: {available}"
        )
    return matching[0]


def read_param(
    pipeline: str, spec: PipelineSpec, address: ParamAddress, *, advice: str | None = None
) -> Any:
    """`advice` says where to set the param, which depends on who is asking: a chain names
    the files it hands over, while anything else is the pipeline's own business.
    """
    node = find_node(pipeline, spec, address.node)
    if address.param not in node.params:
        where = advice or f"Set '{address}' in that pipeline's manifest."
        raise CompositionError(
            f"Node {address.node!r} in pipeline {pipeline!r} sets no param {address.param!r}. "
            f"{where} Params it does set: {sorted(node.params)}"
        )
    return node.params[address.param]


def set_param(pipeline: str, spec: PipelineSpec, address: ParamAddress, value: Any) -> PipelineSpec:
    """`spec` is not modified; the param is set on a copy."""
    find_node(pipeline, spec, address.node)
    return PipelineSpec(
        source_framework=spec.source_framework,
        destination_framework=spec.destination_framework,
        source=_rewrite(spec.source, address, value),
        steps=[_rewrite(step, address, value) for step in spec.steps],
        sinks=[_rewrite(sink, address, value) for sink in spec.sinks],
        validators=list(spec.validators),
    )


def _rewrite(node: NodeSpec, address: ParamAddress, value: Any) -> NodeSpec:
    if node.name != address.node:
        return node
    return NodeSpec(name=node.name, params={**node.params, address.param: value})


def apply_leg_params(pipeline: str, spec: PipelineSpec, params: dict[str, Any]) -> PipelineSpec:
    for key, value in params.items():
        spec = set_param(pipeline, spec, parse_param_address(key), value)
    return spec
