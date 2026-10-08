"""Reproducible graph-behavior checks, not a benchmark of LLM intelligence."""

import sqlite3
import tempfile
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from evidenceloop.backends import DemoBackend
from evidenceloop.graph import build_graph, initial_state
from evidenceloop.models import Citation, Critique, Draft, Evidence
from evidenceloop.retrieval import LocalRetriever
from evidenceloop.validation import validate_citations

QUESTION = "How should retries use idempotency and a bounded retry budget?"


class EmptyRetriever:
    def search(self, query: str, limit: int = 4) -> list[Evidence]:
        return []


class CorruptBackend(DemoBackend):
    def __init__(self, fault: str):
        super().__init__(scenario="clean")
        self.fault = fault

    def draft(self, question, evidence, feedback, attempt):
        draft = super().draft(question, evidence, feedback, attempt)
        if self.fault == "unknown_source":
            draft.claims[0].citations = [Citation(evidence_id="not-retrieved", quote="Invented")]
        elif self.fault == "fabricated_quote":
            draft.claims[0].citations[0].quote = "This sentence does not exist in the source."
        return draft

    def critique(self, question, evidence, draft):
        # Even a permissive model critic must not bypass deterministic validation.
        return Critique(passed=True, feedback=[])


def evaluate() -> dict:
    cases = []

    def record(name, check):
        try:
            detail = check()
            cases.append({"name": name, "passed": True, **detail})
        except Exception as error:
            cases.append({"name": name, "passed": False, "error": str(error)})

    def run_case(scenario, expected, attempts, retriever=None, backend=None):
        graph = build_graph(
            backend or DemoBackend(scenario=scenario),
            retriever if retriever is not None else LocalRetriever.bundled(),
            InMemorySaver(),
        )
        config = {"configurable": {"thread_id": "eval"}, "recursion_limit": 80}
        graph.invoke(initial_state(QUESTION, max_drafts=3), config)
        snapshot = graph.get_state(config)
        state = dict(snapshot.values)
        assert state["status"] == expected, f"Expected {expected}, got {state['status']}"
        assert state["draft_attempts"] == attempts, "Unexpected draft budget use"
        if expected == "awaiting_review":
            assert snapshot.interrupts, "Review must be a real LangGraph interrupt"
            draft = Draft.model_validate(state["draft"])
            evidence = [Evidence.model_validate(item) for item in state["evidence"]]
            assert not validate_citations(draft, evidence), "Citations failed integrity checks"
        return graph, config, state

    def basic(scenario, expected, attempts, **kwargs):
        _, _, state = run_case(scenario, expected, attempts, **kwargs)
        return {"status": state["status"], "draft_attempts": state["draft_attempts"]}

    record("clean_draft_pauses_for_review", lambda: basic("clean", "awaiting_review", 1))
    record(
        "missing_citation_repairs_on_second_draft", lambda: basic("repair", "awaiting_review", 2)
    )
    record("repeated_critique_stops_at_budget", lambda: basic("reject", "exhausted", 3))
    record(
        "no_evidence_abstains_without_drafting",
        lambda: basic("clean", "insufficient_evidence", 0, retriever=EmptyRetriever()),
    )
    for fault in ("unknown_source", "fabricated_quote"):
        record(
            f"{fault}_cannot_be_approved",
            lambda fault=fault: basic("clean", "exhausted", 3, backend=CorruptBackend(fault)),
        )

    def review(action, expected):
        graph, config, _ = run_case("clean", "awaiting_review", 1)
        graph.invoke(Command(resume={"action": action, "feedback": "Keep source quotes."}), config)
        state = graph.get_state(config).values
        assert state["status"] == expected
        if action == "revise":
            assert state["draft_attempts"] == 2
        return {"status": state["status"], "draft_attempts": state["draft_attempts"]}

    record("explicit_approval_finalizes", lambda: review("approve", "approved"))
    record("human_rejection_stops", lambda: review("reject", "rejected"))
    record("human_revision_consumes_same_budget", lambda: review("revise", "awaiting_review"))

    def restart():
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "checkpoints.sqlite"
            config = {"configurable": {"thread_id": "restart"}, "recursion_limit": 80}
            connection = sqlite3.connect(path, check_same_thread=False)
            try:
                graph = build_graph(
                    DemoBackend(scenario="repair"),
                    LocalRetriever.bundled(),
                    SqliteSaver(connection),
                )
                graph.invoke(initial_state(QUESTION), config)
                previous = dict(graph.get_state(config).values)
                assert previous["status"] == "awaiting_review"
            finally:
                connection.close()
            connection = sqlite3.connect(path, check_same_thread=False)
            try:
                # Rebuilt dependencies have no evidence. Resume must use the snapshot.
                graph = build_graph(
                    DemoBackend(scenario="repair"), EmptyRetriever(), SqliteSaver(connection)
                )
                graph.invoke(Command(resume={"action": "approve"}), config)
                state = graph.get_state(config).values
                assert state["status"] == "approved"
                assert state["evidence"] == previous["evidence"]
                assert state["draft_attempts"] == previous["draft_attempts"]
            finally:
                connection.close()
        return {"status": "approved", "evidence_snapshot_preserved": True}

    record("sqlite_resume_with_rebuilt_graph", restart)
    return {
        "suite": "deterministic-control-flow-v1",
        "scope": "Synthetic fixtures and offline extractive backend; no LLM quality measurement.",
        "passed": sum(case["passed"] for case in cases),
        "total": len(cases),
        "cases": cases,
    }
