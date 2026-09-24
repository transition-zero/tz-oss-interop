"""What an ensemble directory says about itself, so a reader never parses a filename.

``FilesystemPort`` cannot list a directory, and one of its adapters serves files over HTTP,
where no listing exists. So the sink that writes an ensemble states which replications it
wrote and what it called each one, and the source that reads the ensemble back asks the
manifest rather than guessing a filename template or probing for the next label.
"""

from __future__ import annotations

import json

from pydantic import BaseModel

ENSEMBLE_MANIFEST_FILENAME = "ensemble.json"


class EnsembleReplication(BaseModel):
    """One replication of an ensemble, and the file holding it."""

    sample: str
    # Relative to the directory holding the manifest, so moving the ensemble keeps it valid.
    filename: str


class EnsembleManifest(BaseModel):
    replications: list[EnsembleReplication] = []


def dump_ensemble_manifest(manifest: EnsembleManifest, indent: int) -> bytes:
    return json.dumps(manifest.model_dump(), indent=indent).encode("utf-8")


def parse_ensemble_manifest(document: object) -> EnsembleManifest:
    return EnsembleManifest.model_validate(document)
