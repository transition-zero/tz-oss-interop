"""A project-local translation step that canonicalises PyPSA generator carriers.

It runs before `pypsa_to_sienna_map_components` so the built-in carrier mapping
sees consistent carrier strings. Carriers it does not recognise are left
untouched, so the mapping still rejects genuinely unknown carriers loudly.
"""

from __future__ import annotations

from typing import ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.ports.outbound.reporting import (
    DestinationField,
    EventKind,
    SourceField,
    TranslationEvent,
)

# Canonical carriers, matching the keys in user_mappings.yaml.
_CANONICAL = {
    "CCGT",
    "OCGT",
    "coal",
    "lignite",
    "nuclear",
    "biomass",
    "onwind",
    "offwind-ac",
    "offwind-dc",
    "solar",
    "hydro",
    "PHS",
}
# Synonyms an upstream tool might emit (lower-cased), mapped to a canonical carrier.
_ALIASES = {"gas_cc": "CCGT", "gas_ocgt": "OCGT", "wind_onshore": "onwind", "pv": "solar"}
_BY_LOWER = {carrier.lower(): carrier for carrier in _CANONICAL}


def _normalise(carrier: str) -> str:
    """Trim, resolve a known alias, then match a canonical carrier case-insensitively."""
    key = carrier.strip()
    lowered = key.lower()
    if lowered in _ALIASES:
        return _ALIASES[lowered]
    return _BY_LOWER.get(lowered, key)


class NormaliseCarrier(TranslationStep):
    name: ClassVar[str] = "normalise_carrier"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def run(self, state: State, params: BaseModel | None) -> State:
        source = state.source_topology.get("generators")
        if source is None:
            return state
        generators = source.collect()
        if "carrier" not in generators.columns:
            return state

        rewrite = {value: _normalise(value) for value in generators["carrier"].unique().to_list()}
        for original, canonical in rewrite.items():
            if original == canonical:
                continue
            names = generators.filter(pl.col("carrier") == original)["name"].to_list()
            for name in names:
                self._recorder.append(
                    TranslationEvent(
                        kind=EventKind.VALUE_DERIVED,
                        sources=[
                            SourceField(
                                framework="pypsa",
                                component="Generator",
                                name=name,
                                attribute="carrier",
                                value=original,
                            )
                        ],
                        destinations=[
                            DestinationField(
                                framework="pypsa",
                                component="Generator",
                                name=name,
                                attribute="carrier",
                                value=canonical,
                            )
                        ],
                        derivation="normalised carrier name to canonical form",
                    )
                )
        state.source_topology["generators"] = generators.with_columns(
            pl.col("carrier").replace(rewrite).alias("carrier")
        ).lazy()
        return state
