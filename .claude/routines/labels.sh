#!/usr/bin/env bash
# labels.sh ensure   create or update every label in labels.tsv
# labels.sh migrate  move bug -> type:bug and enhancement -> type:feature, then delete both
set -euo pipefail

repo=transition-zero/tz-oss-interop
here=$(cd "$(dirname "$0")" && pwd)

ensure() {
	tail -n +2 "$here/labels.tsv" | while IFS=$'\t' read -r name color description; do
		gh label create "$name" --repo "$repo" --color "$color" --description "$description" --force
	done
}

move() {
	local old=$1 new=$2 number
	gh api "repos/$repo/labels/$old" >/dev/null 2>&1 || return 0
	# The issues endpoint lists PRs too, so both kinds are relabelled.
	for number in $(gh api --paginate "repos/$repo/issues?labels=$old&state=all&per_page=100" --jq '.[].number'); do
		gh api -X POST "repos/$repo/issues/$number/labels" -f "labels[]=$new" >/dev/null
		gh api -X DELETE "repos/$repo/issues/$number/labels/$old" >/dev/null
		echo "#$number: $old -> $new"
	done
	gh label delete "$old" --repo "$repo" --yes
}

case "${1:-}" in
ensure) ensure ;;
migrate)
	move bug type:bug
	move enhancement type:feature
	;;
*)
	echo "usage: $0 ensure|migrate" >&2
	exit 2
	;;
esac
