# Evaluate the workflow and the answers separately

EvidenceLoop includes deterministic regression scenarios so control-flow changes can be checked without a model server or API key. Their result is a software behavior check. It is not a benchmark of research intelligence, factual accuracy, or model quality.

## Run the checks

```bash
python -m pytest
python -m ruff check .
evidenceloop evaluate --output results.json
```

The [committed evaluation artifact](../examples/evaluation.json) records one run of the included scenarios. Regenerate results after changes. Use the command's reported scenario outcomes rather than assuming that a successful-looking report means every assertion passed. Approval decisions in this suite and in the committed demo are scripted test inputs; they do not represent independent human review.

## What the scenarios exercise

| Scenario | Controlled behavior | Engineering question |
| --- | --- | --- |
| Clean | A draft supplies valid citations immediately | Can a passing draft reach the completion/review path? |
| Repair | The first draft intentionally omits a citation | Does validation feed a bounded second attempt? |
| Reject | The backend continues to fail critique | Does the workflow stop at its draft budget? |
| Empty retrieval | No evidence is returned | Does execution abstain before generating a draft? |
| Corrupted citations | An unknown source or fabricated quote is inserted | Can a permissive critic bypass the evidence gate? |
| Review decisions | Scripted approve, revise, and reject inputs | Do decisions produce the expected states and consume the shared budget? |
| SQLite restart | Rebuild the graph and open the saved database | Does pending review resume with its evidence snapshot? |

Additional tests should cover quote mismatches, unknown evidence IDs, missing evidence, malformed backend output, persistence, review decisions, and export authorization. Read the current tests for the exact cases under test; the table above explains the scenario design rather than claiming complete coverage.

## Invariants worth preserving

- Every accepted citation refers to an available evidence item and contains a quote found in that item.
- A passing critique cannot override failed deterministic evidence validation.
- Every draft attempt consumes the same finite budget, including human revisions.
- A report waiting for review cannot be exported as approved.
- A rejected or blocked run cannot be exported as approved.
- Resuming a review uses the saved run state and the same checkpoint database.
- A model/service failure does not silently turn into an approved answer.

Tests should assert these visible behaviors. Avoid tests that merely duplicate the routing function's implementation.

## Add an answer-quality evaluation

Create a small versioned dataset with questions, expected source passages, and labels for whether the corpus can answer each question. Include misleading passages, conflicting documents, paraphrases, and unanswerable questions. Keep the final assessment questions separate from the examples used to tune prompts.

| Measure | Suggested definition | Limitation |
| --- | --- | --- |
| Retrieval recall at k | Fraction of labeled relevant passages present in the top k results | Depends on complete relevance labels |
| Citation validity | Fraction of citations with a real evidence ID and matching quote | Does not measure semantic support |
| Supported-claim rate | Fraction of assessed claims entailed by their cited evidence | Requires a defined human rubric or calibrated judge |
| Appropriate abstention | Fraction of unanswerable questions that do not yield an approved substantive answer | Depends on the dataset's answerability labels |
| Draft attempts | Attempts used before review/completion/blocking | Fewer attempts can also mean premature acceptance |
| End-to-end latency | Wall time for a complete machine run, excluding human waiting | Hardware and model settings matter |

Report denominators. A system that makes one easy claim is not automatically better than one that answers all parts of the question. Evaluate useful coverage alongside supported-claim rate.

Compare the same model and corpus under a single-draft baseline and the bounded loop. Keep prompts and generation settings controlled where possible, retain failed runs, and repeat trials if outputs vary. A loop is valuable only if its benefits justify additional latency and calls on the task you care about.

## Record enough to reproduce a result

Save the repository commit, dependency versions, corpus version, question set, backend and model tag, generation settings, draft budget, review policy, and scoring rubric. Label human-edited answers separately from automatically generated ones. Preserve traces for representative failures as well as successes.

For a local-model experiment, make the tested model and environment explicit. The repository's deterministic example outputs cannot stand in for that experiment.
