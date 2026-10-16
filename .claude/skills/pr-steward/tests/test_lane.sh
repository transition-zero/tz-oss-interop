# shellcheck shell=bash
lane_pr() { # number draft labels(csv) [author]
	jq -n --argjson n "$1" --argjson d "$2" --arg l "$3" --arg a "${4:-alice}" \
		'{number:$n,draft:$d,user:{login:$a},labels:($l|split(",")|map(select(.!=""))|map({name:.}))}'
}
lanes() { # reviewed-json [owner] [dependabot owner]
	jq -s --argjson r "$1" --arg o "${2-alice}" --arg d "${3-alice}" '{pulls: ., reviewed: $r, owner: $o, dependabot_owner: $d}' | bash "$skill/lane.sh"
}
lane_of() { lanes "$@" | jq -r 'to_entries[0].value'; }

assert_eq foreign "$(lane_pr 1 false 'PR Ready' bob | lane_of '[]')" "lane: another person's PR is foreign"
assert_eq held "$(lane_pr 1 false 'PR Ready,hold' | lane_of '[]')" "lane: hold wins over every owner lane"
assert_eq held "$(lane_pr 1 false 'hold' 'dependabot[bot]' | lane_of '[]')" "lane: hold holds a Dependabot PR too"
assert_eq dependabot "$(lane_pr 1 false '' 'dependabot[bot]' | lane_of '[]')" "lane: Dependabot's PR for the Dependabot owner"
assert_eq foreign "$(lane_pr 1 false '' 'dependabot[bot]' | lane_of '[]' alice bob)" "lane: Dependabot's PR is foreign to another owner"
assert_eq owner-work "$(lane_pr 1 false 'coderabbit done' | lane_of '[]')" "lane: an owner PR without PR Ready is the owner's own work"
assert_eq needs-owner "$(lane_pr 1 true 'PR Ready,needs owner' | lane_of '[]')" "lane: needs owner wins over draft"
assert_eq queued "$(lane_pr 1 true 'PR Ready' | lane_of '[]')" "lane: a PR Ready draft is queued"
assert_eq 'done' "$(lane_pr 1 false 'PR Ready,coderabbit done' | lane_of '[1]')" "lane: coderabbit done wins over reviewed"
assert_eq reviewed "$(lane_pr 1 false 'PR Ready' | lane_of '[1]')" "lane: a reviewed PR waits for its findings"
assert_eq in-review "$(lane_pr 1 false 'PR Ready' | lane_of '[]')" "lane: a ready PR with no review yet is in review"
assert_eq '{"1":"queued","2":"foreign"}' "$({ lane_pr 1 true 'PR Ready'; lane_pr 2 false '' bob; } | lanes '[]')" "lane: one entry for each open PR"
lane_pr 1 true 'PR Ready' | lanes '[]' "" >/dev/null 2>&1 && rc=0 || rc=$?
assert_eq 1 "$([ "$rc" -ne 0 ] && echo 1 || echo 0)" "lane: no owner is an error, not a lane"

fake_bin=$(mktemp -d)
cat >"$fake_bin/gh" <<FAKE
#!/usr/bin/env bash
count=\$(cat "$fake_bin/count" 2>/dev/null || echo 0)
echo \$((count + 1)) >"$fake_bin/count"
if [ "\$count" -lt "\$(cat "$fake_bin/unknown_reads")" ]; then echo '{"number":7,"mergeable_state":"unknown"}'; else echo '{"number":7,"mergeable_state":"clean"}'; fi
FAKE
chmod +x "$fake_bin/gh"
echo 2 >"$fake_bin/unknown_reads"
assert_eq "clean 3" "$(PATH="$fake_bin:$PATH" PULL_RETRY_SECONDS=0 bash "$skill/pull.sh" 7 | jq -r .mergeable_state) $(cat "$fake_bin/count")" "pull: reads again until mergeable_state is known"
echo 0 >"$fake_bin/count"
echo 9 >"$fake_bin/unknown_reads"
assert_eq "unknown 4" "$(PATH="$fake_bin:$PATH" PULL_RETRY_SECONDS=0 bash "$skill/pull.sh" 7 | jq -r .mergeable_state) $(cat "$fake_bin/count")" "pull: stops after four reads and returns the last"
rm -rf "$fake_bin"
