# The Batch job request contract

## The problem

The Interop Coordinator will need to ask tz-oss-interop's Batch pipeline to run a
translation. Today that ask is a shell script: `batch/submit.sh` in tz-infra-interop
`sed`-substitutes a handful of values into `batch/job-spec.json` (GCP Batch's own job
document) and submits it with `gcloud`. The values it substitutes are:

- `SIGNED_READ_URL` / `SIGNED_WRITE_URL` — signed GCS URLs the job's fetch/push runnables
  use to move the source model in and the translated output out.
- the pipeline name (`pypsa-to-sienna` by default), spliced into the `process` runnable's
  command line.
- `--override` values on that same command line — `source.path=...` and
  `sink[0].output_h5_file_path=...` today, hardcoded for one pipeline.
- the image tag, read from `INTEROP_IMAGE_TAG`, defaulting to a string bumped by hand.

This ticket defines the request contract the coordinator will construct instead of
templating JSON — a versioned Python type, published from this repo the same way the
container image already is. It does not touch `job-spec.json` or `submit.sh`, and it does
not implement submission logic (job-spec construction, GCP Batch API calls, or the
resulting job handle) — that is tz-infra-interop#54.

## The design

### `BatchJobRequest` lives in `interop/ports/batch_job_request.py`

Not `ports/inbound/` or `ports/outbound/`: it is not a use-case interface either direction,
it is a boundary contract between two separate deployables (the coordinator process and the
Batch container image), read by neither through Dishka resolution. It sits directly under
`ports/`, alongside `ports/errors.py`, which is a shared type for the same reason. A plain
pydantic `BaseModel`, matching every other params/request shape in this repo
(`EmitSiennaFilesParams`, and the rest of the `*Params` types under `plugins/*`).

Fields map onto `job-spec.json`'s actual placeholders one for one:

| Field | job-spec.json placeholder |
| --- | --- |
| `pipeline` | the `pypsa-to-sienna` string spliced into the `process` command line |
| `image_tag` | `INTEROP_IMAGE_TAG`, folded into `<ARTIFACT_REGISTRY_IMAGE_URI>` |
| `signed_read_url` | `SIGNED_READ_URL` |
| `signed_write_url` | `SIGNED_WRITE_URL` |
| `overrides` | the `--override` flags on the `process` command line |

`pipeline` is a plain `str`, matching `PipelineName` in
`ports/inbound/pipeline_catalog.py` — pipeline names are manifest stems discovered at
runtime, not a closed enum, and a project can add its own alongside the built-ins (as
tz-infra-interop's `project/pipelines/*.yaml` already does).

`signed_read_url` / `signed_write_url` are plain `str`, not pydantic's `HttpUrl`. A GCS V4
signed URL's validity depends on its exact query string (signature, expiry, scoped
headers); `HttpUrl` re-parses and re-serialises a URL, which risks changing that string
well enough to break the signature. Nothing about this contract needs to inspect the URL,
so it is carried as an opaque string.

`image_tag` is a plain `str` (e.g. `v0.2.0`), not a full image URI. The registry host is
environment-specific Terraform output (`artifact_registry_uri`, read fresh per environment
in `submit.sh`); the coordinator has no reason to know it, and folding it into this field
would tie a request meant to be environment-agnostic to one environment's infrastructure.

### `overrides` reuses `NodeOverrides`, not a new shape

The real choice this ticket has to make explicit: how does the contract carry
per-pipeline variability, given the known pipelines already disagree on what their sink(s)
need? `pypsa-to-sienna` writes `system.json` plus a companion `output_h5_file_path`;
`pypsa-to-tz-core` writes a manifest to `output_dir`; `pypsa-to-sienna-csv` writes to a
different `output_dir` shape entirely. Two shapes were rejected before landing on the one
below.

**A fixed set of common fields** (e.g. `source_path`, `sink_output_path`) was rejected: it
already can't express `pypsa-to-sienna`'s two sink paths in one field, and every new
pipeline that adds a differently-shaped sink would force a field onto every other
pipeline's request, whether or not it applies.

**A typed override model per pipeline** (e.g. `PypsaToSiennaOverrides`,
`PypsaToTzCoreOverrides`) was rejected: it would couple this published contract to every
pipeline's current param names, needing a new type — and a new release of this package —
every time a pipeline's params change or a pipeline is added. That is the same
maintain-two-copies-in-sync risk this ticket's parent issue investigated for
`adapters.yaml`/pipeline-config drift and found not to hold today; inventing it here, on
purpose, in the one place meant to formalise the interface, would be a step backwards.

`overrides` instead reuses `NodeOverrides` from `ports/inbound/overrides.py` verbatim —
the same `source: dict[str, str]` / `steps: dict[int, dict[str, str]]` /
`sinks: dict[int, dict[str, str]]` shape that `headless_cli`'s own `--override` flag
already parses into, and that the REPL's node-param prompts already read as
`source.<field>`, `step[<n>].<field>`, `sink[<n>].<field>`. This is not a new pattern: it
is the one this repo already uses to let one CLI invocation override arbitrary params on
an arbitrary pipeline manifest without knowing its shape in advance. Reusing it here means:

- A pipeline gaining, losing, or renaming a sink param needs no change to this contract.
- Constructing the eventual `--override` flags from a validated `BatchJobRequest` is a
  direct, lossless walk of `overrides.source` / `.steps` / `.sinks` — no translation layer
  between "what the coordinator asked for" and "what headless_cli already accepts."
- pydantic v2 accepts a plain stdlib dataclass as a field type natively (verified against
  the installed pydantic 2.13), including JSON round-tripping the integer `step`/`sink`
  index keys, so no parallel pydantic re-declaration of `NodeOverrides` is needed.

The cost is that `overrides` is unvalidated beyond "some dict of params" — the contract
cannot catch "that pipeline has no sink at index 2" or "that field isn't spelled that way"
at request-construction time. That validation already exists downstream (whatever
constructs the pipeline run reads the manifest and applies these the same way `--override`
does today) and is out of scope for a request contract that, per this ticket, must not
duplicate `adapters.yaml`/pipeline-config knowledge to stay in sync with.

### Versioning and publishing

No separate schema version field. This type ships as part of the `interop` package, and
the package's own version — `pyproject.toml`'s `version`, matched by a `vX.Y.Z` git tag —
is the version a consumer pins to. That is the same mechanism `tz-internal-interop`
already uses to pin `interop` as a git dependency, and the same tag push already triggers
`.github/workflows/publish.yml`'s GHCR container build. Adding this contract is an
additive change to the package's public surface, so the version bumps `0.1.0` → `0.2.0`.

## Non-goals

- No response, job-handle, or error schema — tz-infra-interop#54.
- No change to `job-spec.json`, `submit.sh`, or any coordinator-side code.
- No pipeline-specific override validation — see above.
