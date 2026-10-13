#!/usr/bin/env bash
# threads.sh list <pr>       each review thread as {id, isResolved, comments: [{databaseId, login, isBot, createdAt, body}]}
# threads.sh shape           the same, from the pages of a GraphQL reviewThreads reply on stdin
# threads.sh resolve <id>    resolve one thread by its GraphQL id
set -euo pipefail

repo=transition-zero/tz-oss-interop

# GraphQL drops the "[bot]" that REST puts on a bot's login, so isBot comes from the author's type.
# A thread keeps its root, which a reply targets, and its newest comments, which the reply rule reads.
shape() {
	jq '[.[].data.repository.pullRequest.reviewThreads.nodes[]
		| ((.root.nodes // []) | map(.databaseId)) as $root_ids
		| {id, isResolved, comments: [(.root.nodes // [])[],
			(.comments.nodes[] | select(.databaseId as $id | $root_ids | index($id) | not))]
			| map({databaseId, login: .author.login, isBot: (.author.__typename == "Bot"), createdAt, body})}]'
}

list() {
	# The merge gate counts open threads, so every page must be read.
	gh api graphql --paginate --slurp -F owner="${repo%/*}" -F name="${repo#*/}" -F number="$1" -f query='
		query($owner: String!, $name: String!, $number: Int!, $endCursor: String) {
			repository(owner: $owner, name: $name) {
				pullRequest(number: $number) {
					reviewThreads(first: 100, after: $endCursor) {
						pageInfo { hasNextPage endCursor }
						nodes { id isResolved
							root: comments(first: 1) { nodes { ...comment } }
							comments(last: 100) { nodes { ...comment } } }
					}
				}
			}
		}
		fragment comment on PullRequestReviewComment { databaseId author { login __typename } createdAt body }' | shape
}

resolve() {
	gh api graphql -F id="$1" -f query='
		mutation($id: ID!) { resolveReviewThread(input: {threadId: $id}) { thread { isResolved } } }' \
		--jq .data.resolveReviewThread.thread.isResolved
}

case "${1:-}" in
list) list "${2:?pr}" ;;
shape) shape ;;
resolve) resolve "${2:?thread id}" ;;
*)
	echo "usage: $0 list <pr> | shape | resolve <thread id>" >&2
	exit 2
	;;
esac
