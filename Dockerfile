# syntax=docker/dockerfile:1.7
# ---- build stage: install deps with uv, produce a clean .venv ----
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

WORKDIR /app

# Copy only what's needed to resolve dependencies first, so Docker's layer
# cache can skip the (slow) dependency install when only application code
# changes, not pyproject.toml/uv.lock. README.md, LICENSE and NOTICE travel
# with them because pyproject.toml declares them as the readme and the licence
# files, and hatchling reads all three to build the wheel below.
COPY pyproject.toml uv.lock README.md LICENSE NOTICE ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --frozen --no-install-project

# Now copy the actual package and install it into the same venv. App code
# changes invalidate only this layer, not the dependency-install layer above.
COPY interop/ ./interop/

# hatch-vcs takes the version from a git tag, and .dockerignore keeps .git out
# of the build context, so the version comes in as a build argument instead.
# setuptools_scm, which hatch-vcs wraps, reads this variable. The argument sits
# here rather than at the top of the stage so a new version invalidates only
# this layer, not the dependency install above.
ARG VERSION=0.0.0
ENV SETUPTOOLS_SCM_PRETEND_VERSION=${VERSION}
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

# Volatile build args go last: passing a new GIT_SHA on rebuild only
# invalidates this final metadata layer, not the dependency/source layers
# above. VERSION is the pushed tag with its leading "v" removed, so the label
# and the installed distribution state the same version.
ARG GIT_SHA=unknown
ARG VERSION=0.0.0
LABEL org.opencontainers.image.revision="$GIT_SHA"
LABEL org.opencontainers.image.version="$VERSION"

ENTRYPOINT ["interop", "headless_cli"]
