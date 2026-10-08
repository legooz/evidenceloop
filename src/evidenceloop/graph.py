"""An explicit, bounded LangGraph workflow with durable human review."""

import operator
import re
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send, interrupt
from pydantic import ValidationError

from .models import Backend, BackendError, Critique, Draft, Evidence, ReviewDecision
from .validation import validate_citations


def merge_evidence(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge retrieval branches by stable ID, keeping the highest-scoring match."""
    merged: dict[str, dict[str, Any]] = {}
    for item in [*left, *right]:
        previous = merged.get(item["id"])
        if previous is None or item.get("score", 0) > previous.get("score", 0):
            merged[item["id"]] = item
    return sorted(merged.values(), key=lambda item: (-item.get("score", 0), item["id"]))


class ResearchState(TypedDict):
    question: str
    queries: list[str]
    evidence: Annotated[list[dict[str, Any]], merge_evidence]
    draft: dict[str, Any] | None
    critique: dict[str, Any] | None
    validation_errors: list[str]
    feedback: list[str]
    draft_attempts: int
    max_drafts: int
    require_review: bool
    status: str
    error: str | None
    review_error: str | None
    events: Annotated[list[dict[str, Any]], operator.add]


class RetrievalInput(TypedDict):
    query: str


def initial_state(question: str, max_drafts: int = 3, require_review: bool = True) -> ResearchState:
    """Create a fresh run. Draft limits include the first draft and human revisions."""
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Question must be a nonempty string.")
    if type(max_drafts) is not int or not 1 <= max_drafts <= 8:
        raise ValueError("max_drafts must be an integer between 1 and 8.")
    if type(require_review) is not bool:
        raise ValueError("require_review must be a boolean.")
    return {
        "question": question.strip(),
        "queries": [],
        "evidence": [],
        "draft": None,
        "critique": None,
        "validation_errors": [],
        "feedback": [],
        "draft_attempts": 0,
        "max_drafts": max_drafts,
        "require_review": require_review,
        "status": "running",
        "error": None,
        "review_error": None,
        "events": [],
    }


def _event(node: str, attempt: int, detail: str) -> list[dict[str, Any]]:
    return [{"node": node, "attempt": attempt, "detail": detail}]


def _evidence(state: ResearchState) -> list[Evidence]:
    return [Evidence.model_validate(item) for item in state["evidence"]]


def build_graph(backend: Backend, retriever: Any, checkpointer: Any) -> Any:
    """Compile the workflow; pass a checkpointer and stable thread_id for review.

    The retriever supplies ``search(query, limit=4) -> list[Evidence]``. Retrieval
    branches merge before drafting; all evidence text remains in checkpoint state.
    Nodes never write reports or perform actions on behalf of a reviewer.
    """

    def plan(state: ResearchState) -> dict[str, Any]:
        # Keep the original question. Only add substantial question-derived clauses,
        # avoiding generic, invented queries that would retrieve unrelated evidence.
        queries = [state["question"]]
        seen = {state["question"].casefold()}
        for clause in re.split(r"\?|\band\b", state["question"], flags=re.IGNORECASE):
            clause = clause.strip(" .?\n\t")
            if len(clause.split()) >= 3 and clause.casefold() not in seen:
                queries.append(clause)
                seen.add(clause.casefold())
            if len(queries) == 4:
                break
        return {
            "queries": queries,
            "events": _event("plan", 0, f"Prepared {len(queries)} retrieval queries."),
        }

    def fan_out(state: ResearchState) -> list[Send]:
        return [Send("retrieve", {"query": query}) for query in state["queries"]]

    def retrieve(state: RetrievalInput) -> dict[str, Any]:
        results = retriever.search(state["query"], limit=4)
        evidence = [Evidence.model_validate(item).model_dump(mode="json") for item in results]
        return {
            "evidence": evidence,
            "events": _event(
                "retrieve", 0, f"Retrieved {len(evidence)} passages for: {state['query']}"
            ),
        }

    def draft(state: ResearchState) -> dict[str, Any]:
        if not state["evidence"]:
            return {
                "status": "insufficient_evidence",
                "error": "No matching evidence was found; no answer was generated.",
                "events": _event("draft", 0, "Abstained because retrieval returned no evidence."),
            }
        if state["draft_attempts"] >= state["max_drafts"]:
            return exhausted(state)
        attempt = state["draft_attempts"] + 1
        try:
            result = Draft.model_validate(
                backend.draft(state["question"], _evidence(state), state["feedback"], attempt)
            )
        except (BackendError, ValidationError):
            return {
                "status": "failed",
                "draft_attempts": attempt,
                "error": "The draft backend failed or returned an invalid response.",
                "events": _event("draft", attempt, "Backend failure; stopped without approval."),
            }
        return {
            "draft": result.model_dump(mode="json"),
            "draft_attempts": attempt,
            "critique": None,
            "validation_errors": [],
            "status": "running",
            "error": None,
            "events": _event("draft", attempt, f"Generated draft {attempt}."),
        }

    def after_draft(state: ResearchState) -> str:
        return "validate" if state["status"] == "running" else END

    def validate(state: ResearchState) -> dict[str, Any]:
        errors = validate_citations(Draft.model_validate(state["draft"]), _evidence(state))
        return {
            "validation_errors": errors,
            "feedback": [*state["feedback"], *errors],
            "events": _event(
                "validate",
                state["draft_attempts"],
                f"Citation integrity failed: {len(errors)} issues."
                if errors
                else "All citation integrity checks passed (semantic support is separate).",
            ),
        }

    def after_validate(state: ResearchState) -> str:
        if not state["validation_errors"]:
            return "critique"
        return "draft" if state["draft_attempts"] < state["max_drafts"] else "exhausted"

    def critique(state: ResearchState) -> dict[str, Any]:
        try:
            result = Critique.model_validate(
                backend.critique(
                    state["question"], _evidence(state), Draft.model_validate(state["draft"])
                )
            )
        except (BackendError, ValidationError):
            return {
                "status": "failed",
                "error": "The critique backend failed or returned an invalid response.",
                "events": _event(
                    "critique",
                    state["draft_attempts"],
                    "Backend failure; stopped without approval.",
                ),
            }
        feedback = result.feedback
        if not result.passed and not feedback:
            feedback = ["The critic rejected the draft. Recheck support and answer completeness."]
        return {
            "critique": result.model_dump(mode="json"),
            "feedback": [*state["feedback"], *feedback],
            "events": _event(
                "critique",
                state["draft_attempts"],
                "Passed." if result.passed else "Revision needed.",
            ),
        }

    def after_critique(state: ResearchState) -> str:
        if state["status"] == "failed":
            return END
        if state["critique"] and state["critique"]["passed"]:
            return "prepare_review" if state["require_review"] else "ready"
        return "draft" if state["draft_attempts"] < state["max_drafts"] else "exhausted"

    def exhausted(state: ResearchState) -> dict[str, Any]:
        return {
            "status": "exhausted",
            "error": "The total draft budget was exhausted before an acceptable result was reached.",
            "events": _event("exhausted", state["draft_attempts"], "Stopped at the draft budget."),
        }

    def ready(state: ResearchState) -> dict[str, Any]:
        return {
            "status": "ready",
            "events": _event(
                "ready", state["draft_attempts"], "Checks passed; human review was disabled."
            ),
        }

    def prepare_review(state: ResearchState) -> dict[str, Any]:
        return {
            "status": "awaiting_review",
            "review_error": None,
            "events": _event(
                "prepare_review", state["draft_attempts"], "Waiting for human review."
            ),
        }

    def review(state: ResearchState) -> dict[str, Any]:
        # LangGraph re-executes this node on resume. No calls or writes precede the
        # interrupt, and it must stay outside the ValidationError handler below.
        response = interrupt(
            {
                "kind": "review",
                "question": state["question"],
                "draft": state["draft"],
                "evidence": state["evidence"],
                "draft_attempts": state["draft_attempts"],
                "remaining_drafts": state["max_drafts"] - state["draft_attempts"],
                "actions": ["approve", "revise", "reject"],
                "error": state["review_error"],
            }
        )
        try:
            decision = ReviewDecision.model_validate(response, strict=True)
        except ValidationError:
            return {
                "status": "awaiting_review",
                "review_error": (
                    "Provide an object with action 'approve', 'revise', or 'reject' "
                    "and optional string feedback."
                ),
                "events": _event("review", state["draft_attempts"], "Invalid review decision."),
            }
        update: dict[str, Any] = {
            "review_error": None,
            "events": _event("review", state["draft_attempts"], f"Human chose {decision.action}."),
        }
        if decision.action == "approve":
            update["status"] = "approved"
        elif decision.action == "reject":
            update["status"] = "rejected"
        elif state["draft_attempts"] >= state["max_drafts"]:
            update.update(
                status="exhausted",
                error="No draft budget remains for the requested human revision.",
            )
        else:
            update.update(
                status="running",
                feedback=[
                    *state["feedback"],
                    f"Human revision request: {decision.feedback.strip() or 'Improve the draft.'}",
                ],
            )
        return update

    def after_review(state: ResearchState) -> str:
        if state["status"] == "awaiting_review":
            return "review"
        if state["status"] == "running":
            return "draft"
        return END

    builder = StateGraph(ResearchState)
    builder.add_node("plan", plan)
    builder.add_node("retrieve", retrieve)
    builder.add_node("draft", draft)
    builder.add_node("validate", validate)
    builder.add_node("critique", critique)
    builder.add_node("exhausted", exhausted)
    builder.add_node("ready", ready)
    builder.add_node("prepare_review", prepare_review)
    builder.add_node("review", review)
    builder.add_edge(START, "plan")
    builder.add_conditional_edges("plan", fan_out, ["retrieve"])
    builder.add_edge("retrieve", "draft")
    builder.add_conditional_edges("draft", after_draft, ["validate", END])
    builder.add_conditional_edges("validate", after_validate, ["critique", "draft", "exhausted"])
    builder.add_conditional_edges(
        "critique", after_critique, ["prepare_review", "ready", "draft", "exhausted", END]
    )
    builder.add_edge("prepare_review", "review")
    builder.add_conditional_edges("review", after_review, ["review", "draft", END])
    builder.add_edge("exhausted", END)
    builder.add_edge("ready", END)
    # The explicit draft budget is the normal stop condition. This independent
    # circuit breaker leaves enough supersteps for all eight allowed attempts.
    return builder.compile(checkpointer=checkpointer).with_config({"recursion_limit": 64})
