# syntax=docker/dockerfile:1.7
# ---- build stage: install deps with uv, produce a clean .venv ----
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

WORKDIR /app

# Copy only what's needed to resolve dependencies first, so Docker's layer
# cache can skip the (slow) dependency install when only application code
# changes, not pyproject.toml/uv.lock.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --frozen --no-install-project

# Now copy the actual package and install it into the same venv. App code
# changes invalidate only this layer, not the dependency-install layer above.
COPY interop/ ./interop/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --frozen --no-editable

# ---- runtime stage: minimal image, just the venv + package ----
FROM python:3.13-slim AS runtime

# Copy the fully-populated virtualenv from the build stage — no uv, no
# build toolchain, no dev/test dependencies end up in this final image.
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# The project (pipelines/, adapters.yaml, etc.) is supplied at runtime,
# mounted into this directory — this image never bakes in a specific
# project. See README's "Headless invocation" section: headless_cli
# resolves everything from cwd.
WORKDIR /project

# Volatile build args go last: passing a new GIT_SHA/VERSION on rebuild
# only invalidates this final metadata layer, not the dependency/source
# layers above. VERSION defaults to "unknown" since tag-derived versioning
# (hatch-vcs) doesn't exist yet — see the Packaging story; this label
# should start reflecting a real version once that lands.
ARG GIT_SHA=unknown
ARG VERSION=unknown
LABEL org.opencontainers.image.revision="$GIT_SHA"
LABEL org.opencontainers.image.version="$VERSION"

ENTRYPOINT ["interop", "headless_cli"]
