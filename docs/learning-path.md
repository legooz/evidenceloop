# Make the project yours

This repository is an AI-assisted starting point. A public repository shows the code that exists; your experiments, explanations, and review history show your understanding. Use the milestones below to produce that evidence without overstating what you have done.

Keep short experiment notes in the repository: question, predicted outcome, command, observed trace, explanation, and next change. Commit your own modifications in small steps with messages explaining the behavior changed.

## 1. Explain one complete run

Run the `repair` scenario from the README. Before approving it, read the state and find the first failed citation check, feedback, next draft, and review interruption.

**Deliverable:** a short walkthrough linking to the relevant functions and a trace from your run.

You should be able to explain:

- What data is shared between nodes, and which node owns each update?
- Why does a missing citation cause another draft?
- Why is quote membership insufficient to establish truth?
- What happens if the draft budget is one?

Do not describe the scripted demo as a model repairing its own reasoning.

## 2. Learn the graph by breaking a reducer

On a local branch, change how parallel retrieval outputs combine. Try ordinary replacement where the current graph merges results. Run a question with multiple retrieval queries and inspect the behavior. Revert the experiment when finished.

**Deliverable:** an explanation of the failure and a regression test that would catch the same mistake.

Explain why shared state needs an explicit merge rule when several workers update a key. Then contrast accumulated evidence with draft-specific validation findings, which should describe the current attempt.

## 3. Prove durable review

Start a clean run and let it pause. Close the terminal. Open a new terminal, activate the same environment, inspect the run, and request a revision. Finally approve or reject it.

**Deliverable:** a transcript showing that the run resumed from the same SQLite database, plus a diagram marking the interruption boundary.

Explain why calling the graph with a fresh question is different from resuming an interrupt. Identify any operation that would be unsafe to repeat before the interruption.

## 4. Test evidence that looks convincing

Create a tiny corpus containing two incompatible claims with clear source dates. Add a candidate answer whose quote exists verbatim but does not support its claim. Observe what the existing validator can and cannot detect.

**Deliverable:** a failing semantic example, its expected outcome, and a written proposal for improving the check.

If you add an entailment model, label examples yourself first. Keep a test set aside. Compare the new system against the original on supported, contradicted, and irrelevant quotes. Include false acceptances and false rejections in the report.

## 5. Add a retrieval loop with a budget

Implement query reformulation when the retrieved evidence is insufficient. Keep separate limits for retrieval rounds and draft attempts. Decide which evidence carries forward and which feedback triggers a new search.

**Deliverable:** a pull request with an updated graph, routing tests, and an experiment showing when the extra retrieval helps or hurts.

Before coding, answer: what evidence will establish that another search is worthwhile? What prevents oscillation? What happens when the corpus simply cannot answer the question?

## 6. Evaluate a real model

Run a local Ollama model against a small set of questions with independently written expected evidence. Record the model tag, hardware, settings, corpus version, questions, failures, and elapsed times. Run more than one trial when output variability matters.

**Deliverable:** an evaluation report comparing a single draft with the bounded revision loop under the same conditions.

Measure citation validity and human-rated support separately. Track unanswered questions as well as successful reports. Never combine deterministic fixture pass rates with model answer-quality scores.

## A portfolio walkthrough

When you can reproduce the behavior and explain your own extension, a concise demonstration can follow this sequence:

1. State the failure you wanted to address: research prose can contain unsupported claims.
2. Show the graph and explain one state reducer and one routing decision.
3. Run a repair case and a case that correctly stops without approval.
4. Resume human review from a separate process.
5. Present your own change, its measured result, and a remaining limitation.

Use an accurate description such as: “I extended an AI-assisted LangGraph research workflow with [your change]. I tested [specific behavior] and found [measured result].” Only fill those brackets after doing the work.

Useful foundations: [LangGraph graph API](https://docs.langchain.com/oss/python/langgraph/graph-api), [interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts), and [persistence](https://docs.langchain.com/oss/python/langgraph/persistence).
