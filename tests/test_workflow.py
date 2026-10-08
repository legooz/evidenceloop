import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from evidenceloop.backends import DemoBackend
from evidenceloop.evaluation import QUESTION, evaluate
from evidenceloop.graph import build_graph, initial_state
from evidenceloop.models import BackendError
from evidenceloop.reporting import render_report
from evidenceloop.retrieval import LocalRetriever


def setup_graph(backend=None):
    return build_graph(
        backend or DemoBackend(scenario="clean"), LocalRetriever.bundled(), InMemorySaver()
    )


def config(name="test"):
    return {"configurable": {"thread_id": name}, "recursion_limit": 80}


def test_evaluation_contract():
    results = evaluate()
    assert results["passed"] == results["total"], results


@pytest.mark.parametrize(
    "payload", [True, "approve", {"action": "yes"}, {"action": "approve", "extra": True}]
)
def test_malformed_human_decisions_do_not_approve(payload):
    graph = setup_graph()
    graph.invoke(initial_state(QUESTION), config())
    graph.invoke(Command(resume=payload), config())
    state = graph.get_state(config())
    assert state.values["status"] == "awaiting_review"
    assert state.interrupts
    assert state.values["draft_attempts"] == 1
    graph.invoke(Command(resume={"action": "approve"}), config())
    assert graph.get_state(config()).values["status"] == "approved"


def test_human_revisions_cannot_reset_budget():
    graph = setup_graph()
    graph.invoke(initial_state(QUESTION, max_drafts=2), config())
    graph.invoke(Command(resume={"action": "revise", "feedback": "Use direct quotes"}), config())
    assert graph.get_state(config()).values["draft_attempts"] == 2
    graph.invoke(Command(resume={"action": "revise", "feedback": "Try again"}), config())
    state = graph.get_state(config())
    assert state.values["status"] == "exhausted"
    assert state.values["draft_attempts"] == 2
    assert not state.interrupts


def test_independent_threads_do_not_mix_evidence_or_decisions():
    graph = setup_graph()
    graph.invoke(initial_state(QUESTION), config("first"))
    graph.invoke(initial_state("How are checkpoints restored?"), config("second"))
    graph.invoke(Command(resume={"action": "approve"}), config("first"))
    assert graph.get_state(config("first")).values["status"] == "approved"
    assert graph.get_state(config("second")).values["status"] == "awaiting_review"
    assert graph.get_state(config("second")).values["question"] != QUESTION


def test_skipping_review_is_ready_and_cannot_export():
    graph = setup_graph()
    graph.invoke(initial_state(QUESTION, require_review=False), config())
    state = graph.get_state(config()).values
    assert state["status"] == "ready"
    with pytest.raises(ValueError, match="human-approved"):
        render_report(state, "demo")


def test_provider_failure_is_terminal_and_not_a_fake_demo_success():
    class BrokenBackend(DemoBackend):
        def draft(self, *args, **kwargs):
            raise BackendError("Service unavailable")

    graph = setup_graph(BrokenBackend())
    graph.invoke(initial_state(QUESTION), config())
    snapshot = graph.get_state(config())
    assert snapshot.values["status"] == "failed"
    assert not snapshot.interrupts


def test_all_search_branches_merge_before_drafting():
    graph = setup_graph()
    graph.invoke(initial_state(QUESTION, require_review=False), config())
    state = graph.get_state(config()).values
    assert len(state["queries"]) >= 2
    assert len({item["id"] for item in state["evidence"]}) == len(state["evidence"])
    assert state["draft_attempts"] == 1


@pytest.mark.parametrize("budget", [0, -1, 9, True])
def test_invalid_budgets_rejected(budget):
    with pytest.raises(ValueError):
        initial_state(QUESTION, max_drafts=budget)
