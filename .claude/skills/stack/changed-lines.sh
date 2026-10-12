#!/usr/bin/env bash
# changed-lines.sh <diff>   each added or removed line as "<path>:<line>", sorted
set -euo pipefail
[ $# -eq 1 ] || {
	echo "usage: $0 <diff>" >&2
	exit 2
}
# A header is known by its place, before a file's first @@, not by its prefix: a removed
# source line "-- a/foo" is written "--- a/foo" inside a hunk.
awk '
	/^diff --git / { path = $NF; sub(/^b\//, "", path); hunk = 0; next }
	/^@@ / { hunk = 1; next }
	!hunk && /^\+\+\+ b\// { path = substr($0, 7); next }
	hunk && /^[+-]/ { print path ":" $0 }
' "$1" | LC_ALL=C sort
