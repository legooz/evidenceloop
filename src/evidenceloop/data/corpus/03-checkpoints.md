# Checkpoints and human review in the fictional Beacon workflow

Fixture notice: This is original synthetic learning material, not a production runbook or a statement about a real organization.

Persist graph state under a stable thread identifier so an interrupted run can resume from its saved checkpoint. A durable local SQLite checkpointer can demonstrate a process restart without losing the pending review.

Pause for human review only after deterministic evidence checks and critic review pass. The reviewer can approve the draft, request a revision, or reject the answer.

Code before an interrupt may run again when the node resumes. Keep that code free of non-idempotent side effects, and validate the resumed review decision before applying it.

Checkpoint data can contain the question, retrieved passages, and generated drafts. Store the database outside version control and protect it according to the sensitivity of the documents.
