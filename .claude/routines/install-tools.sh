#!/usr/bin/env bash
# install-tools.sh   install make and uv when absent, then sync the Python environment
set -euo pipefail

# The cloud image has neither tool. pip puts uv here, which a fresh shell may not have on PATH.
export PATH="$HOME/.local/bin:$PATH"

command -v make >/dev/null || sudo dnf install -y -q make
command -v uv >/dev/null || python3 -m pip install --user --quiet uv
uv sync --locked --all-groups
