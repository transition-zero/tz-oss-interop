#!/usr/bin/env bash
# install-tools.sh   install make and uv when absent, fail when the caller's PATH cannot reach
#                    either tool, then sync the Python environment
set -euo pipefail

# The cloud image has neither tool. CI also takes the latest uv release.
command -v make >/dev/null || sudo dnf install -y -q make
command -v uv >/dev/null || python3 -m pip install --user --quiet uv
# The routine runs make and uv later, from shells that have this PATH.
for tool in make uv; do
	if ! command -v "$tool" >/dev/null; then
		echo "install-tools: $tool is installed, but not on the caller's PATH. Add $HOME/.local/bin to PATH." >&2
		exit 1
	fi
done
uv sync --locked --all-groups
