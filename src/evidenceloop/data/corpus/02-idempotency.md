# Idempotency and side effects in the fictional Beacon workflow

Fixture notice: This is original synthetic learning material, not a production runbook or a statement about a real organization.

An idempotency key identifies one intended operation across repeated attempts. The receiving service must atomically record the key and return the previous result when that key is replayed.

A graph checkpoint records workflow state, but it does not make an external payment, email, or database write atomic with that checkpoint. A crash between a side effect and checkpoint persistence can cause the node to execute again.

Keep externally visible side effects after explicit approval and design those operations to tolerate replay. A local checkpoint by itself is not a guarantee of exactly-once execution.

For the teaching workflow, draft generation and citation checks have no external write effects. Publishing an answer is represented by a local final state only.
