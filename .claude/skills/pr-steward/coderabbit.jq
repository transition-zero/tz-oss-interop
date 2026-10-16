# Shared by coderabbit.sh. Each definition reads {reviews, comments}, or {comments} for paused.

def cr: .user.login == "coderabbitai[bot]";
def t(f): f | fromdateiso8601;
def summary: .body | contains("## Walkthrough");

# A review with nothing to fix posts no review object, only its "## Walkthrough" summary or a
# "Review finished" notice. An empty-bodied review is a reply in a thread. The summary is
# edited on pauses and replies, so only its created_at is a review time, and a limit note
# left inside a summary is stale; a standalone limit notice is dated by its updated_at,
# because CodeRabbit rewrites one notice in place.
def events:
	[.reviews[] | select(cr) | select((.body // "") != "") | t(.submitted_at)] as $reviews
	| [.comments[] | select(cr) | select(.body | test("Review finished")) | t(.created_at // .updated_at)] as $finished
	| [.comments[] | select(cr) | select(summary)] as $summaries
	# One review can post a review object and create the summary; the summary then adds no review.
	| [$summaries[] | select(.created_at) | t(.created_at)
	   | select(. as $at | ($reviews + $finished) | any(. - $at | fabs < 600) | not)] as $summaries_at
	| [.comments[] | select(cr) | select(summary | not) | (.body | capture("available in (?<m>[0-9]+) minute")?) as $c
	   | select($c != null) | {at: t(.updated_at), until: (t(.updated_at) + (($c.m | tonumber) * 60))}] as $limits
	| [.comments[] | select(.user.login == $ARGS.named.owner) | select(.body | contains("@coderabbitai review")) | t(.created_at)] as $asks
	| {reviews: ($reviews + $finished + $summaries_at), reviewed: (($reviews + $finished + $summaries) | length > 0),
	   limits: $limits, asks: $asks};

# The allowance is per hour and changes with use; the newest note that states it wins, and
# with no note the allowance is one review an hour.
def allowance:
	def stated: (.body // "") | first(capture("allowance at (?<n>[0-9]+) reviews? per hour"),
		capture("up to (?<n>[0-9]+) included reviews? per hour")) | .n | tonumber;
	[(.reviews[] | select(cr) | {at: t(.submitted_at), n: stated}),
	 (.comments[] | select(cr) | {at: t(.created_at // .updated_at), n: stated})]
	| max_by(.at) | .n // 1;

# Only a reply after the owner's newest pause request counts: the summary also says
# "Reviews paused" when CodeRabbit pauses itself, and it keeps that text after a resume.
# A resume from anyone after that request ends the pause.
def paused:
	([.comments[] | select(.user.login == $ARGS.named.owner and (.body | contains("@coderabbitai pause")))
	  | t(.created_at)] | max) as $asked
	| ([.comments[] | select(cr | not) | select(.body | contains("@coderabbitai resume")) | t(.created_at)] | max) as $resumed
	| $asked != null and ($resumed == null or $resumed < $asked)
	  and any(.comments[]; cr and (.body | contains("Reviews paused")) and t(.created_at) > $asked);
