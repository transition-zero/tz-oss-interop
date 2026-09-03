from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeAlias

from pydantic import BaseModel

if TYPE_CHECKING:
    from interop.core.pipeline import Sink

NodeClassLookup: TypeAlias = Callable[[str], type]
SinkClassLookup: TypeAlias = Callable[[str], type["Sink"]]


@dataclass(frozen=True)
class NodeLookups:
    source: NodeClassLookup
    step: NodeClassLookup
    sink: SinkClassLookup
    validator: NodeClassLookup


class UserMappings(BaseModel):
    """Marker base class for user-defined mapping schemas."""


UserMappingsLookup: TypeAlias = dict[type[UserMappings], UserMappings]


@dataclass(frozen=True)
class UserMappingsOutput:
    """A sink's declaration that the file it writes is a user mappings file.

    `schema` is what connects this sink to the legs that consume the file; nothing names
    it in a manifest. `path_param` must name the param of this sink that holds the
    output path.
    """

    schema: type[UserMappings]
    path_param: str
