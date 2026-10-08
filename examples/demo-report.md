# Simulated evidence summary

**Question:** How should retries use idempotency and a bounded retry budget?

**Status:** approved | **Backend:** demo | **Draft attempts:** 2/3

> Offline extractive demonstration. No language model was used. The bundled corpus contains fictional engineering notes.

- Retrying a graph node after a crash can repeat its side effects. [1]

- CURRENT LESSON: Limit retries to transient failures, enforce a finite attempt budget, and use idempotency keys for replayable external operations. [2]

- A graph recursion limit is a final guard against routing bugs, not the application retry policy. [3]

## Limitations

- Offline demo: claims are copied excerpts; no LLM reasoning was performed.
- Lexical retrieval and quote checks do not establish truth or resolve conflicting notes.

## Evidence ledger

**[1] 01-retries.md, lines 9–9** (`ev-5c092b69ae2194b1`)

> Retrying a graph node after a crash can repeat its side effects.

**[2] 06-archived-incident.md, lines 9–9** (`ev-b0de01f8792c2c9c`)

> CURRENT LESSON: Limit retries to transient failures, enforce a finite attempt budget, and use idempotency keys for replayable external operations.

**[3] 04-loop-budgets.md, lines 9–9** (`ev-84ae67d9bde28f01`)

> A graph recursion limit is a final guard against routing bugs, not the application retry policy.

Citation validation checks source IDs and quoted text. It does not prove that a quote supports its surrounding claim or that the underlying source is true.
