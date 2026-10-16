#!/usr/bin/env bash
# install-tools.sh   install make and uv when absent, sync the Python environment, and fail
#                    when the caller's PATH cannot reach either tool
set -euo pipefail

caller_path=$PATH
# The cloud image has neither tool. pip puts uv here.
export PATH="$HOME/.local/bin:$PATH"

command -v make >/dev/null || sudo dnf install -y -q make
command -v uv >/dev/null || python3 -m pip install --user --quiet uv
uv sync --locked --all-groups

# The routine runs make and uv later, from shells that have the caller's PATH, not this one.
for tool in make uv; do
	if ! PATH=$caller_path command -v "$tool" >/dev/null; then
		echo "install-tools: $tool is installed, but not on the caller's PATH. Add $HOME/.local/bin to PATH." >&2
		exit 1
	fi
done
