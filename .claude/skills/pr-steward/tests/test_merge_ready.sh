# shellcheck shell=bash
bundle() { # lane author base labels(csv) mergeable_state reviews-json checks-json [open_threads, or null to leave it out]
	jq -n --arg lane "$1" --arg a "$2" --arg b "$3" --arg l "$4" --arg m "$5" --argjson r "$6" --argjson c "$7" --argjson t "${8:-0}" \
		'{pr:{state:"open",draft:false,user:{login:$a},base:{ref:$b},labels:($l|split(",")|map(select(.!=""))|map({name:.})),mergeable_state:$m,head:{sha:"h1"}},reviews:$r,checks:$c}
		+ (if $lane == "" then {} else {lane:$lane} end)
		+ (if $t == null then {} else {open_threads:$t} end)'
}
green='[{"name":"lint","status":"completed","conclusion":"success"},{"name":"test (windows-latest, 3.13)","status":"completed","conclusion":"success"}]'
approved='[{"user":{"login":"carol"},"state":"APPROVED","commit_id":"h1"}]'
lint_only='[{"name":"lint","status":"completed","conclusion":"success"}]'
linux_only='[{"name":"lint","status":"completed","conclusion":"success"},{"name":"test (ubuntu-latest, 3.12)","status":"completed","conclusion":"success"}]'
no_lint='[{"name":"test (windows-latest, 3.13)","status":"completed","conclusion":"success"},{"name":"dco","status":"completed","conclusion":"success"}]'
mr() { bash "$skill/merge-ready.sh"; }

assert_eq ready "$(bundle 'done' alice main '' clean "$approved" "$green" | mr)" "merge: approved, green, reviewed and clean"
assert_eq "not-ready: base is not main" "$(bundle 'done' alice issue-1 '' clean "$approved" "$green" | mr)" "merge: a stacked rung never merges"
assert_eq "not-ready: mergeable_state is blocked" "$(bundle 'done' alice main '' blocked "$approved" "$green" | mr)" "merge: a PR GitHub will not merge is not ready"
assert_eq "not-ready: changes requested" "$(bundle 'done' alice main '' clean '[{"user":{"login":"carol"},"state":"APPROVED","commit_id":"h1"},{"user":{"login":"dave"},"state":"CHANGES_REQUESTED","commit_id":"h1"}]' "$green" | mr)" "merge: any change request blocks"
assert_eq ready "$(bundle 'done' alice main '' clean '[{"user":{"login":"carol"},"state":"CHANGES_REQUESTED","commit_id":"h1"},{"user":{"login":"carol"},"state":"APPROVED","commit_id":"h1"}]' "$green" | mr)" "merge: a later approval supersedes a change request"
assert_eq ready "$(bundle 'done' alice main '' clean '[{"user":{"login":"carol"},"state":"APPROVED","commit_id":"h1"},{"user":{"login":"carol"},"state":"COMMENTED","commit_id":"h1"}]' "$green" | mr)" "merge: a later comment does not hide an approval"
assert_eq "not-ready: no approval" "$(bundle 'done' alice main '' clean '[{"user":{"login":"coderabbitai[bot]"},"state":"APPROVED","commit_id":"h1"}]' "$green" | mr)" "merge: a bot's approval does not count"
assert_eq "not-ready: no approval" "$(bundle 'done' alice main '' clean '[{"user":{"login":"alice"},"state":"APPROVED","commit_id":"h1"}]' "$green" | mr)" "merge: the author's own approval does not count"
assert_eq "not-ready: checks not green" "$(bundle 'done' alice main '' clean "$approved" '[{"name":"test (windows-latest, 3.13)","status":"in_progress","conclusion":null}]' | mr)" "merge: Windows still running blocks"
assert_eq "not-ready: checks not green" "$(bundle 'done' alice main '' clean "$approved" '[]' | mr)" "merge: no checks at all blocks"
assert_eq ready "$(bundle dependabot 'dependabot[bot]' main '' clean '[{"user":{"login":"alice"},"state":"APPROVED","commit_id":"h1"}]' "$green" | mr)" "merge: green Dependabot approved by the owner"
assert_eq "not-ready: needs owner review" "$(bundle dependabot 'dependabot[bot]' main 'needs owner review' clean '[{"user":{"login":"alice"},"state":"APPROVED","commit_id":"h1"}]' "$green" | mr)" "merge: a fixed Dependabot PR waits for the owner"
assert_eq "not-ready: no approval on the head" "$(bundle 'done' alice main '' clean '[{"user":{"login":"dave"},"state":"APPROVED","commit_id":"h0"}]' "$green" | mr)" "merge: an approval of an older commit does not count"
assert_eq ready "$(bundle 'done' alice main '' clean '[{"user":{"login":"carol"},"state":"APPROVED","commit_id":"h0"},{"user":{"login":"dave"},"state":"APPROVED","commit_id":"h1"}]' "$green" | mr)" "merge: one approval on the head is enough"
assert_eq "not-ready: changes requested" "$(bundle 'done' alice main '' clean '[{"user":{"login":"carol"},"state":"CHANGES_REQUESTED","commit_id":"h0"},{"user":{"login":"dave"},"state":"APPROVED","commit_id":"h1"}]' "$green" | mr)" "merge: a change request on an older commit still blocks"
assert_eq "not-ready: no Windows test" "$(bundle 'done' alice main '' clean "$approved" "$lint_only" | mr)" "merge: lint alone is not enough"
assert_eq "not-ready: no lint check" "$(bundle 'done' alice main '' clean "$approved" "$no_lint" | mr)" "merge: lint must be present"
assert_eq "not-ready: no Windows test" "$(bundle 'done' alice main '' clean "$approved" "$linux_only" | mr)" "merge: Linux test legs without the Windows leg block"
assert_eq "not-ready: open review threads" "$(bundle 'done' alice main '' clean "$approved" "$green" 1 | mr)" "merge: an open review thread blocks"
assert_eq "not-ready: thread count unknown" "$(bundle 'done' alice main '' clean "$approved" "$green" null | mr)" "merge: a missing thread count blocks"
assert_eq "not-ready: no approval" "$(bundle 'done' bob main '' clean '[{"user":{"login":"bob"},"state":"APPROVED","commit_id":"h1"}]' "$green" | mr)" "merge: the author's own approval does not count for any owner"
skipped='[{"name":"lint","status":"completed","conclusion":"skipped"},{"name":"test (ubuntu-latest, 3.13)","status":"completed","conclusion":"skipped"},{"name":"test (windows-latest, 3.13)","status":"completed","conclusion":"skipped"},{"name":"versions","status":"completed","conclusion":"success"}]'
assert_eq "not-ready: lint or a test leg did not succeed" "$(bundle 'done' alice main '' clean "$approved" "$skipped" | mr)" "merge: skipped lint and test legs are not green"
windows_skipped='[{"name":"lint","status":"completed","conclusion":"success"},{"name":"test (ubuntu-latest, 3.13)","status":"completed","conclusion":"success"},{"name":"test (windows-latest, 3.13)","status":"completed","conclusion":"skipped"}]'
assert_eq "not-ready: lint or a test leg did not succeed" "$(bundle 'done' alice main '' clean "$approved" "$windows_skipped" | mr)" "merge: a skipped Windows leg is not green"
other_skipped='[{"name":"lint","status":"completed","conclusion":"success"},{"name":"test (windows-latest, 3.13)","status":"completed","conclusion":"success"},{"name":"mutation","status":"completed","conclusion":"skipped"}]'
assert_eq ready "$(bundle 'done' alice main '' clean "$approved" "$other_skipped" | mr)" "merge: a skipped job other than lint or tests is fine"
for lane in foreign held owner-work needs-owner queued reviewed in-review; do
	assert_eq "not-ready: lane is $lane" "$(bundle "$lane" alice main '' clean "$approved" "$green" | mr)" "merge: the $lane lane never merges"
done
assert_eq "not-ready: lane is unknown" "$(bundle '' alice main '' clean "$approved" "$green" | mr)" "merge: no lane, no merge"
