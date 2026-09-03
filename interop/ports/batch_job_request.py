"""The contract the Interop Coordinator uses to request a translation job from
tz-oss-interop's Batch pipeline. See docs/specs/2026-09-03-batch-job-request-contract-design.md
for why the fields are shaped this way.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from interop.ports.inbound.overrides import NodeOverrides
from interop.ports.inbound.pipeline_catalog import PipelineName


class BatchJobRequest(BaseModel):
    """One translation job submission, independent of any single environment.

    `signed_read_url` and `signed_write_url` are carried as opaque strings, not a URL
    type: a GCS V4 signed URL's validity depends on its exact query string, and a URL
    type that re-parses and re-serialises would risk changing it. `image_tag` names a
    published tz-oss-interop image tag (e.g. "v0.2.0"), not a full image URI — the
    registry host is environment-specific infrastructure this request has no reason to
    know.
    """

    pipeline: PipelineName = Field(
        description="The pipeline manifest to run, e.g. 'pypsa-to-sienna'."
    )
    image_tag: str = Field(description="The published tz-oss-interop image tag to run the job on.")
    signed_read_url: str = Field(
        description="Signed GCS URL the job downloads its source model from."
    )
    signed_write_url: str = Field(
        description="Signed GCS URL the job uploads its translated output to."
    )
    overrides: NodeOverrides = Field(
        default_factory=NodeOverrides,
        description=(
            "Params layered over the pipeline manifest, keyed the same way as "
            "headless_cli's --override flag: source/step[n]/sink[n]. Omitted or "
            "empty means the job runs the manifest's own params unchanged."
        ),
    )
