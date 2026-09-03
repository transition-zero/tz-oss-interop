# Batch job request contract

`interop.ports.batch_job_request.BatchJobRequest` is the contract the Interop Coordinator
uses to ask tz-oss-interop's Batch pipeline to run a translation job. It is a published
part of the `interop` package: a consumer depends on a tagged version of this repo (the
same git dependency mechanism `tz-internal-interop` already uses) and imports the type
directly.

This is a request contract only. It says what a coordinator asks for; it says nothing
about how that request becomes a GCP Batch job, what comes back, or how errors are
reported. Batch submission logic, job handles, and error shapes are a separate concern.

## Fields

| Field | Type | Meaning |
| --- | --- | --- |
| `pipeline` | `PipelineName` (a `str` alias) | The pipeline manifest to run, e.g. `pypsa-to-sienna`. Not a closed enum — pipeline names are manifest stems resolved at runtime, and a project can add its own alongside the built-ins. |
| `image_tag` | `str` | The published tz-oss-interop image tag to run the job on (e.g. `v0.2.0`), not a full image URI — the registry host is environment-specific infrastructure this request doesn't need to know. |
| `signed_read_url` | `str` | Signed GCS URL the job downloads its source model from. |
| `signed_write_url` | `str` | Signed GCS URL the job uploads its translated output to. |
| `overrides` | `NodeOverrides` | Params layered over the pipeline manifest. Optional — defaults to empty, meaning the job runs the manifest exactly as written. |

`signed_read_url` and `signed_write_url` are opaque strings, not a URL type: a GCS V4
signed URL's validity depends on its exact query string, and a URL type that re-parses and
re-serialises the value risks changing it well enough to break the signature.

## `overrides` reuses the existing override shape

`overrides` is `interop.ports.inbound.overrides.NodeOverrides` — the same
`source`/`step[n]`/`sink[n]` keyed-dict shape `headless_cli`'s own `--override` flag
already parses into, and the REPL's node-param prompts already read as `source.<field>`,
`step[<n>].<field>`, `sink[<n>].<field>`. See the design spec
(`docs/specs/2026-09-03-batch-job-request-contract-design.md`) for why a fixed set of
common fields and a typed-per-pipeline override model were both rejected in favour of
reusing this shape.

A request may omit `overrides` entirely; it then defaults to an empty `NodeOverrides`
(all three dicts empty), the same as passing no `--override` flags to `headless_cli` —
the job runs the pipeline manifest's own params unchanged. That is meaningful on its own
(a pipeline whose manifest already points at fixed paths needs nothing layered on top),
not just a placeholder a caller is expected to always fill in. In practice a Batch
submission almost always sets at least `source` (the source path is `/mnt/share/...`,
decided by where the job's fetch step wrote the download, not by the manifest), but the
contract does not require it.

```python
from interop.ports.batch_job_request import BatchJobRequest
from interop.ports.inbound.overrides import NodeOverrides

request = BatchJobRequest(
    pipeline="pypsa-to-sienna",
    image_tag="v0.2.0",
    signed_read_url="https://storage.googleapis.com/...",
    signed_write_url="https://storage.googleapis.com/...",
    overrides=NodeOverrides(
        source={"path": "/mnt/share/pypsa_network.nc"},
        sinks={0: {"output_h5_file_path": "/mnt/share/output.h5"}},
    ),
)
```

## Versioning

There is no separate schema version. `BatchJobRequest` ships as part of the `interop`
package; a consumer pins to a `vX.Y.Z` git tag of this repo, the same tag that triggers
`.github/workflows/publish.yml`'s container build.
