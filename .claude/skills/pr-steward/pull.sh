#!/usr/bin/env bash
# pull.sh <n>   one PR as REST JSON, read again while GitHub has not yet computed mergeable_state
set -euo pipefail

for attempt in 1 2 3 4; do
	pr=$(gh api "repos/transition-zero/tz-oss-interop/pulls/${1:?pr}")
	[ "$(jq -r .mergeable_state <<<"$pr")" != unknown ] && break
	[ "$attempt" -lt 4 ] && sleep "${PULL_RETRY_SECONDS:-5}"
done
printf '%s\n' "$pr"
