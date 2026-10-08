# Retry policy for the fictional Beacon workflow

Fixture notice: This is original synthetic learning material, not a production runbook or a statement about a real organization.

Retry transient network timeouts and temporary service failures with a fixed attempt limit. A retry policy needs both a maximum number of attempts and a timeout for each attempt.

Do not retry validation errors or permanent authorization failures automatically. Repeating an unchanged invalid request consumes the retry budget without improving the result.

Retrying a graph node after a crash can repeat its side effects. Use an idempotency key before retrying an operation that writes to an external service.

Record attempt counts and the final failure category in the execution trace. Avoid logging credentials, raw private documents, or complete service error bodies.
