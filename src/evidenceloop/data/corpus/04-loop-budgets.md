# Bounded repair loops in the fictional Beacon workflow

Fixture notice: This is original synthetic learning material, not a production runbook or a statement about a real organization.

Set an explicit draft attempt budget before starting a repair loop. Increment the counter for every attempted draft, including drafts that fail to produce a valid response.

Mechanical citation failures, critic rejection, and human requests for revision all consume the same finite draft budget. Reject the run when that budget is exhausted instead of silently accepting the last draft.

A graph recursion limit is a final guard against routing bugs, not the application retry policy. Use a separate draft attempt budget to make termination explainable in the execution trace.

Keep transport retries distinct from reasoning revisions. With two HTTP attempts per model call, a draft-plus-critic iteration can issue at most four HTTP requests; a call timeout bounds each request's inactivity, not a whole-run wall-clock deadline.
