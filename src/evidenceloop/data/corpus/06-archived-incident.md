# Archived incident and superseded guidance for the fictional Beacon workflow

Fixture notice: This is an original synthetic incident, with intentionally conflicting historical guidance for evaluation. No real incident or organization is described.

ARCHIVED GUIDANCE, SUPERSEDED: Retry every failure indefinitely until a worker succeeds. Assume that checkpoint persistence makes all external side effects exactly once.

The fictional incident review rejected that old retry advice. An unbounded retry loop amplified service overload, and a crash after a side effect but before checkpoint persistence produced a duplicate operation.

CURRENT LESSON: Limit retries to transient failures, enforce a finite attempt budget, and use idempotency keys for replayable external operations. Cite the archived statement only as historical guidance, never as the current recommendation.
