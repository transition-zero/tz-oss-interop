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
