#!/usr/bin/env bash
# approved-by.sh   the login that holds epic:approved now, or nothing, from the issue's
#                  events slurped page by page: gh api --paginate …/events | jq -s .
set -euo pipefail

jq -r '
	add // [] | [.[] | select((.event == "labeled" or .event == "unlabeled") and .label.name == "epic:approved")]
	| last | select(. != null and .event == "labeled") | .actor.login'
