# shellcheck shell=bash
owner=alice
dependabot_owner=alice
bundle() { # author base labels(csv) mergeable_state reviews-json checks-json [open_threads, or null to leave it out]
	jq -n --arg a "$1" --arg b "$2" --arg l "$3" --arg m "$4" --argjson r "$5" --argjson c "$6" --argjson t "${7:-0}" \
		--arg o "$owner" --arg d "$dependabot_owner" \
		'{pr:{state:"open",draft:false,user:{login:$a},base:{ref:$b},labels:($l|split(",")|map(select(.!=""))|map({name:.})),mergeable_state:$m,head:{sha:"h1"}},reviews:$r,checks:$c,dependabot_owner:$d}
		+ (if $t == null then {} else {open_threads:$t} end)
		+ (if $o == "" then {} else {owner:$o} end)'
}
with_owner() { # owner dependabot_owner command…; an empty owner leaves the key out
	local owner=$1 dependabot_owner=$2
	shift 2
	"$@"
}
green='[{"name":"lint","status":"completed","conclusion":"success"},{"name":"test (windows-latest, 3.13)","status":"completed","conclusion":"success"}]'
approved='[{"user":{"login":"carol"},"state":"APPROVED","commit_id":"h1"}]'
lint_only='[{"name":"lint","status":"completed","conclusion":"success"}]'
linux_only='[{"name":"lint","status":"completed","conclusion":"success"},{"name":"test (ubuntu-latest, 3.12)","status":"completed","conclusion":"success"}]'
no_lint='[{"name":"test (windows-latest, 3.13)","status":"completed","conclusion":"success"},{"name":"dco","status":"completed","conclusion":"success"}]'
mr() { bash "$skill/merge-ready.sh"; }

assert_eq ready "$(bundle alice main 'PR Ready,coderabbit done' clean "$approved" "$green" | mr)" "merge: approved, green, reviewed and clean"
assert_eq "not-ready: base is not main" "$(bundle alice issue-1 'coderabbit done' clean "$approved" "$green" | mr)" "merge: a stacked rung never merges"
assert_eq "not-ready: no coderabbit done" "$(bundle alice main 'PR Ready' clean "$approved" "$green" | mr)" "merge: owner PR needs its CodeRabbit review"
assert_eq "not-ready: mergeable_state is blocked" "$(bundle alice main 'PR Ready,coderabbit done' blocked "$approved" "$green" | mr)" "merge: a PR GitHub will not merge is not ready"
assert_eq "not-ready: changes requested" "$(bundle alice main 'PR Ready,coderabbit done' clean '[{"user":{"login":"carol"},"state":"APPROVED","commit_id":"h1"},{"user":{"login":"dave"},"state":"CHANGES_REQUESTED","commit_id":"h1"}]' "$green" | mr)" "merge: any change request blocks"
assert_eq ready "$(bundle alice main 'PR Ready,coderabbit done' clean '[{"user":{"login":"carol"},"state":"CHANGES_REQUESTED","commit_id":"h1"},{"user":{"login":"carol"},"state":"APPROVED","commit_id":"h1"}]' "$green" | mr)" "merge: a later approval supersedes a change request"
assert_eq ready "$(bundle alice main 'PR Ready,coderabbit done' clean '[{"user":{"login":"carol"},"state":"APPROVED","commit_id":"h1"},{"user":{"login":"carol"},"state":"COMMENTED","commit_id":"h1"}]' "$green" | mr)" "merge: a later comment does not hide an approval"
assert_eq "not-ready: no approval" "$(bundle alice main 'PR Ready,coderabbit done' clean '[{"user":{"login":"coderabbitai[bot]"},"state":"APPROVED","commit_id":"h1"}]' "$green" | mr)" "merge: a bot's approval does not count"
assert_eq "not-ready: no approval" "$(bundle alice main 'PR Ready,coderabbit done' clean '[{"user":{"login":"alice"},"state":"APPROVED","commit_id":"h1"}]' "$green" | mr)" "merge: the author's own approval does not count"
assert_eq "not-ready: held for the owner" "$(bundle alice main 'coderabbit done,hold' clean "$approved" "$green" | mr)" "merge: hold blocks"
assert_eq "not-ready: checks not green" "$(bundle alice main 'PR Ready,coderabbit done' clean "$approved" '[{"name":"test (windows-latest, 3.13)","status":"in_progress","conclusion":null}]' | mr)" "merge: Windows still running blocks"
assert_eq "not-ready: checks not green" "$(bundle alice main 'PR Ready,coderabbit done' clean "$approved" '[]' | mr)" "merge: no checks at all blocks"
assert_eq "not-ready: author not allowed" "$(bundle carol main 'coderabbit done' clean '[{"user":{"login":"alice"},"state":"APPROVED","commit_id":"h1"}]' "$green" | mr)" "merge: someone else's PR is not ours to merge"
assert_eq ready "$(bundle 'dependabot[bot]' main '' clean '[{"user":{"login":"alice"},"state":"APPROVED","commit_id":"h1"}]' "$green" | mr)" "merge: green Dependabot approved by the owner"
assert_eq "not-ready: needs owner review" "$(bundle 'dependabot[bot]' main 'needs owner review' clean '[{"user":{"login":"alice"},"state":"APPROVED","commit_id":"h1"}]' "$green" | mr)" "merge: a fixed Dependabot PR waits for the owner"
assert_eq "not-ready: no approval on the head" "$(bundle alice main 'PR Ready,coderabbit done' clean '[{"user":{"login":"dave"},"state":"APPROVED","commit_id":"h0"}]' "$green" | mr)" "merge: an approval of an older commit does not count"
assert_eq ready "$(bundle alice main 'PR Ready,coderabbit done' clean '[{"user":{"login":"carol"},"state":"APPROVED","commit_id":"h0"},{"user":{"login":"dave"},"state":"APPROVED","commit_id":"h1"}]' "$green" | mr)" "merge: one approval on the head is enough"
assert_eq "not-ready: changes requested" "$(bundle alice main 'PR Ready,coderabbit done' clean '[{"user":{"login":"carol"},"state":"CHANGES_REQUESTED","commit_id":"h0"},{"user":{"login":"dave"},"state":"APPROVED","commit_id":"h1"}]' "$green" | mr)" "merge: a change request on an older commit still blocks"
assert_eq "not-ready: no Windows test" "$(bundle alice main 'PR Ready,coderabbit done' clean "$approved" "$lint_only" | mr)" "merge: lint alone is not enough"
assert_eq "not-ready: no lint check" "$(bundle alice main 'PR Ready,coderabbit done' clean "$approved" "$no_lint" | mr)" "merge: lint must be present"
assert_eq "not-ready: no Windows test" "$(bundle alice main 'PR Ready,coderabbit done' clean "$approved" "$linux_only" | mr)" "merge: Linux test legs without the Windows leg block"
assert_eq "not-ready: open review threads" "$(bundle alice main 'PR Ready,coderabbit done' clean "$approved" "$green" 1 | mr)" "merge: an open review thread blocks"
assert_eq "not-ready: thread count unknown" "$(bundle alice main 'PR Ready,coderabbit done' clean "$approved" "$green" null | mr)" "merge: a missing thread count blocks"
assert_eq ready "$(with_owner alice bob bundle alice main 'PR Ready,coderabbit done' clean "$approved" "$green" | mr)" "merge: an owner's PR is ready for that owner"
assert_eq "not-ready: author not allowed" "$(with_owner bob alice bundle alice main 'PR Ready,coderabbit done' clean "$approved" "$green" | mr)" "merge: an owner's PR is not another owner's to merge"
assert_eq "not-ready: author not allowed" "$(with_owner bob alice bundle 'dependabot[bot]' main '' clean '[{"user":{"login":"alice"},"state":"APPROVED","commit_id":"h1"}]' "$green" | mr)" "merge: only the Dependabot owner merges Dependabot"
assert_eq "not-ready: no approval" "$(with_owner bob alice bundle bob main 'PR Ready,coderabbit done' clean '[{"user":{"login":"bob"},"state":"APPROVED","commit_id":"h1"}]' "$green" | mr)" "merge: the author's own approval does not count for any owner"
assert_eq "not-ready: owner unknown" "$(with_owner "" alice bundle alice main 'PR Ready,coderabbit done' clean "$approved" "$green" | mr)" "merge: no owner, no merge"
skipped='[{"name":"lint","status":"completed","conclusion":"skipped"},{"name":"test (ubuntu-latest, 3.13)","status":"completed","conclusion":"skipped"},{"name":"test (windows-latest, 3.13)","status":"completed","conclusion":"skipped"},{"name":"versions","status":"completed","conclusion":"success"}]'
assert_eq "not-ready: lint or a test leg did not succeed" "$(bundle alice main 'PR Ready,coderabbit done' clean "$approved" "$skipped" | mr)" "merge: skipped lint and test legs are not green"
windows_skipped='[{"name":"lint","status":"completed","conclusion":"success"},{"name":"test (ubuntu-latest, 3.13)","status":"completed","conclusion":"success"},{"name":"test (windows-latest, 3.13)","status":"completed","conclusion":"skipped"}]'
assert_eq "not-ready: lint or a test leg did not succeed" "$(bundle alice main 'PR Ready,coderabbit done' clean "$approved" "$windows_skipped" | mr)" "merge: a skipped Windows leg is not green"
other_skipped='[{"name":"lint","status":"completed","conclusion":"success"},{"name":"test (windows-latest, 3.13)","status":"completed","conclusion":"success"},{"name":"mutation","status":"completed","conclusion":"skipped"}]'
assert_eq ready "$(bundle alice main 'PR Ready,coderabbit done' clean "$approved" "$other_skipped" | mr)" "merge: a skipped job other than lint or tests is fine"
assert_eq "not-ready: no PR Ready" "$(bundle alice main 'coderabbit done' clean "$approved" "$green" | mr)" "merge: an owner PR without PR Ready never merges"
