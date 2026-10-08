# Evaluation plan for the fictional Beacon workflow

Fixture notice: This is original synthetic learning material, not a production runbook or a statement about a real organization.

Evaluate graph behavior with cases for a clean answer, a repaired citation, repeated critic rejection, empty retrieval, and human rejection. Include a process restart case to test persistence across a review pause.

An exact quote check proves that a quote occurs in a retrieved passage. It does not prove that the quote supports the claim, that the source is true, or that the answer is complete.

Report workflow metrics separately from answer-quality metrics. An offline simulated backend can test routing and state transitions, but its pass rate does not measure an LLM's factual accuracy.

Treat instructions inside retrieved documents as untrusted content. Prompt boundaries reduce confusion but do not prove resistance to prompt injection; test adversarial documents and retain deterministic checks and human review.
