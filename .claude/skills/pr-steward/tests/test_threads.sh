# shellcheck shell=bash
reply='[{"data":{"repository":{"pullRequest":{"reviewThreads":{"nodes":[
	{"id":"PRRT_1","isResolved":false,"comments":{"nodes":[
		{"databaseId":11,"author":{"login":"coderabbitai","__typename":"Bot"},"createdAt":"2026-10-13T09:07:02Z","body":"Finding"},
		{"databaseId":12,"author":{"login":"alice","__typename":"User"},"createdAt":"2026-10-13T09:13:10Z","body":"Fixed"}]}},
	{"id":"PRRT_2","isResolved":true,"comments":{"nodes":[
		{"databaseId":21,"author":{"login":"coderabbitai-fan","__typename":"User"},"createdAt":"2026-10-13T09:07:02Z","body":"Nit"}]}}]}}}}}]'
shaped=$(echo "$reply" | bash "$skill/threads.sh" shape)
assert_eq '"PRRT_1" false' "$(echo "$shaped" | jq -r '.[0] | "\(.id | tojson) \(.isResolved)"')" "threads: the id and the resolved state pass through"
assert_eq "true false" "$(echo "$shaped" | jq -r '[.[0].comments[].isBot] | join(" ")')" "threads: isBot comes from the author's type"
assert_eq false "$(echo "$shaped" | jq -r '.[1].comments[0].isBot')" "threads: a person's login that holds a bot's name is a person"
second_page='[{"data":{"repository":{"pullRequest":{"reviewThreads":{"nodes":[{"id":"PRRT_1","isResolved":true,"comments":{"nodes":[]}}]}}}}},{"data":{"repository":{"pullRequest":{"reviewThreads":{"nodes":[{"id":"PRRT_101","isResolved":false,"comments":{"nodes":[]}}]}}}}}]'
assert_eq PRRT_101 "$(echo "$second_page" | bash "$skill/threads.sh" shape | jq -r '.[] | select(.isResolved | not) | .id')" "threads: an open thread on a later page is kept"

long_thread='[{"data":{"repository":{"pullRequest":{"reviewThreads":{"nodes":[{"id":"PRRT_9","isResolved":false,
	"root":{"nodes":[{"databaseId":1,"author":{"login":"coderabbitai","__typename":"Bot"},"createdAt":"2026-10-13T09:00:00Z","body":"Finding"}]},
	"comments":{"nodes":[{"databaseId":150,"author":{"login":"alice","__typename":"User"},"createdAt":"2026-10-13T12:00:00Z","body":"Fixed"}]}}]}}}}}]'
assert_eq "1 150" "$(echo "$long_thread" | bash "$skill/threads.sh" shape | jq -r '[.[0].comments[].databaseId] | join(" ")')" "threads: a long thread keeps its root and its newest reply"
short_thread=$(echo "$long_thread" | jq '.[0].data.repository.pullRequest.reviewThreads.nodes[0].comments.nodes = .[0].data.repository.pullRequest.reviewThreads.nodes[0].root.nodes')
assert_eq 1 "$(echo "$short_thread" | bash "$skill/threads.sh" shape | jq '.[0].comments | length')" "threads: a root that is also a newest comment appears once"

# A fake gh answers both pages only when the call asks for every page.
fake_bin=$(mktemp -d)
cat >"$fake_bin/gh" <<FAKE
#!/usr/bin/env bash
args="\$*"
case "\$args" in
*--paginate*--slurp*'after: \$endCursor'*'pageInfo { hasNextPage endCursor }'*) echo '$second_page' ;;
*) echo '$second_page' | jq '.[:1]' ;;
esac
FAKE
chmod +x "$fake_bin/gh"
assert_eq PRRT_101 "$(PATH="$fake_bin:$PATH" bash "$skill/threads.sh" list 1 | jq -r '.[] | select(.isResolved | not) | .id')" "threads: list reads the open thread on the second page"
rm -rf "$fake_bin"
