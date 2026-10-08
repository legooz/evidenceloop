# Architecture and design decisions

EvidenceLoop uses one stateful graph to answer a question from a local corpus. The graph separates decisions about control flow from the generation of text, so each can be inspected and tested independently.

## The state is the interface

The graph carries the question, retrieval queries, evidence, current draft, validation findings, critique, revision feedback, draft count, review outcome, and trace events. Model-facing objects use strict Pydantic schemas. Evidence includes an ID, source location, line range, text, and retrieval score; a citation names an evidence ID and supplies a quote.

The latest draft and critique replace earlier values. Parallel retrieval results need a reducer that combines updates instead of letting the last worker overwrite the others. Trace events accumulate so the final result preserves the route through the workflow. Read the state definition and reducer annotations alongside the [LangGraph state and reducer documentation](https://docs.langchain.com/oss/python/langgraph/graph-api#state).

This distinction is a useful graph engineering exercise: a list does not automatically mean “append.” Appending validation errors across drafts, for example, would leave fixed errors active forever.

## Execution

1. **Plan.** Split the question into a small set of deterministic retrieval queries. This keeps the initial planning behavior reproducible.
2. **Retrieve.** Dispatch one retrieval task per query through LangGraph's `Send` primitive. Local BM25 ranks corpus chunks. Combine results before drafting.
3. **Draft.** Ask the selected backend for a structured set of claims and citations. Increment the draft count whenever a draft attempt is made.
4. **Validate.** Check citation presence, evidence IDs, and quote membership against the retrieved evidence. Unicode compatibility normalization and collapsed whitespace permit equivalent text formatting; matching remains case-sensitive. Quotes must contain at least two words and eight letters or digits. Failed validation routes directly to revision or budget exhaustion.
5. **Critique.** After validation passes, obtain backend feedback about the draft. A positive model judgment cannot bypass a failed deterministic check.
6. **Route.** Continue to review when checks pass, revise while the draft budget remains, or finish in an `exhausted` state. Missing evidence yields `insufficient_evidence`; backend failures yield `failed`.
7. **Review.** Pause for an approve, revise, or reject decision. Approval permits export. Revision returns to drafting under the existing budget.

`Send` lets each retrieval branch receive its own input while reducing its output into shared state. This is a small map/reduce workflow, as described in the [official `Send` reference](https://reference.langchain.com/python/langgraph/types/Send).

The graph does not invent more source material during revision. If retrieval misses the relevant passage, repeated drafting can still fail. Query reformulation and a second retrieval round are intentional extension exercises.

## Termination is a product rule

`max_drafts` is the total number of allowed draft attempts, including the initial draft and human-requested revisions. It is not a counter that resets after approval feedback. A run with a budget of one can draft once, but cannot repair that draft.

The application budget and LangGraph's recursion limit serve different purposes. The budget expresses what this workflow is allowed to spend on revision. A recursion limit bounds graph execution steps and acts as a separate guard. More nodes per draft do not buy more draft attempts.

A successful check can still be followed by human rejection. Likewise, reaching the budget is a legitimate result: the workflow reports failure instead of endlessly rewriting the same unsupported answer.

## Checkpointing and review

SQLite checkpoints associate graph state with a run ID. The CLI uses that identifier to inspect or resume a run from another process. Review uses `interrupt()` to pause and a resume command to supply a structured decision. The runtime restores the saved state when the same checkpoint database and run ID are used. See [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence) and [interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts).

An interrupted node resumes by running its function again. Code before the interrupt therefore needs to tolerate re-execution. Keep external effects, such as publishing a report or sending a message, out of the pre-interrupt path. This project writes an approved report only when the user explicitly runs the export command.

Durability here means that a review pause survives a process restart. The CLI resumes pending review interrupts; it does not yet provide recovery for arbitrary mid-execution failures. This is not a claim of exactly-once external effects or a multi-user job scheduler. Do not concurrently resume the same run from multiple processes.

Disabling review with `--no-review` yields `ready` when the checks pass. It does not assign `approved`, and it does not permit export. A terminal `ready` run cannot later be reviewed through the CLI; start a new run with review enabled.

## Two backends, one graph

| Backend | Purpose | Interpretation |
| --- | --- | --- |
| `demo` | Reproduce clean, repair, and failed-critique paths | Scripted behavior; no LLM call |
| `ollama` | Generate and critique with a local model | Model behavior varies; requires a running service |

Both implement the same draft and critique contract. The demo's repair scenario intentionally omits a first-pass citation. It tests whether the workflow notices and repairs a known defect. It cannot demonstrate that an LLM learns from criticism.

The Ollama adapter requests JSON conforming to the Pydantic schema and parses the result back into typed objects. Schema validation catches malformed structure; citation checks catch some evidence mistakes; neither proves semantic correctness.

## Trace and report boundaries

The event trace explains the execution path and draft attempts. The report exposes claims and source quotes for review. They serve different audiences: traces explain the system; reports help inspect the answer.

Corpus excerpts also appear in checkpoint state. Treat the local database and traces as containing the same data classification as the source documents. The committed examples use the bundled demonstration corpus.

## Tradeoffs to defend

| Choice | Benefit | Cost / next experiment |
| --- | --- | --- |
| Local BM25 | Small dependency footprint and inspectable ranking | Weak on paraphrases; compare a semantic retriever |
| Deterministic planner | Reproducible query generation | Limited decomposition; evaluate a model planner |
| Exact quote matching | Cheap and falsifiable evidence check | No entailment guarantee; label semantic counterexamples |
| Separate critique | Explicit quality feedback and routing | Extra model call; measure whether it helps |
| Finite draft budget | Predictable termination | Can block repairable drafts; study budget versus quality |
| SQLite checkpointer | Simple cross-process local review | Shared deployments require more operational design |

Choose extensions by measured failure cases. Adding a second agent or a vector store without an observed problem makes the graph larger without showing that it became more useful.
