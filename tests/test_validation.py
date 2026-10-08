"""Boundary tests for structural checks and merging concurrent retrieval results."""

from copy import deepcopy
from itertools import permutations

import pytest
from pydantic import ValidationError

from evidenceloop.graph import merge_evidence
from evidenceloop.models import Citation, Claim, Draft, Evidence
from evidenceloop.validation import validate_citations


def evidence(text="Use exponential backoff and jitter.", *, identifier="ev-one", score=1):
    return Evidence(
        id=identifier, source="notes.md", start_line=1, end_line=1, text=text, score=score
    )


def draft(quote="Use exponential backoff", *, identifier="ev-one", claim="Back off on retries."):
    return Draft(
        title="Retry policy",
        claims=[Claim(text=claim, citations=[Citation(evidence_id=identifier, quote=quote)])],
    )


def test_valid_quote_normalizes_unicode_and_whitespace():
    source = evidence("Use\n exponential\tbackoff and a ﬁxed retry budget.")
    assert validate_citations(draft("Use exponential backoff"), [source]) == []
    assert validate_citations(draft("a fixed retry budget"), [source]) == []


@pytest.mark.parametrize("quote", ["... --", "backoff", "four cat", "   \t\n"])
def test_uninformative_quotes_fail_even_when_present_in_source(quote):
    errors = validate_citations(draft(quote), [evidence(f"Some text {quote} additional text.")])
    assert any("uninformative" in error for error in errors)


def test_quote_minimum_accepts_exactly_two_words_and_eight_characters():
    assert validate_citations(draft("four word"), [evidence("four word")]) == []


@pytest.mark.parametrize("quote", ["use exponential backoff", "Invented retry policy"])
def test_quotes_must_match_source_case_and_content(quote):
    errors = validate_citations(draft(quote), [evidence()])
    assert any("not present" in error for error in errors)


def test_a_real_quote_cannot_reference_an_unknown_source():
    errors = validate_citations(draft(identifier="ev-missing"), [evidence()])
    assert any("unknown evidence" in error for error in errors)


def test_every_claim_needs_a_citation():
    answer = draft()
    answer.claims.append(Claim(text="Another claim without support."))
    errors = validate_citations(answer, [evidence()])
    assert errors == ["Claim 2 has no citations."]


def test_every_citation_is_checked_even_when_another_one_is_valid():
    answer = draft()
    answer.claims[0].citations.append(Citation(evidence_id="ev-one", quote="Fabricated quote"))
    errors = validate_citations(answer, [evidence()])
    assert len(errors) == 1 and "not present" in errors[0]


def test_empty_draft_and_whitespace_claim_fail():
    assert validate_citations(Draft(title="No answer"), [evidence()])
    assert "Claim 1 is empty." in validate_citations(draft(claim="  \n "), [evidence()])


def test_citation_integrity_explicitly_does_not_establish_semantic_support():
    # A real quote cannot mechanically disprove this unrelated assertion. Keeping
    # this test makes the validator's boundary visible to future contributors.
    answer = draft(claim="The system guarantees zero failures forever.")
    assert validate_citations(answer, [evidence()]) == []


@pytest.mark.parametrize("field", ["claims", "limitations"])
def test_structured_draft_limits_collection_sizes(field):
    payload = draft().model_dump()
    payload[field] = [payload["claims"][0]] * 9 if field == "claims" else ["Limit"] * 9
    with pytest.raises(ValidationError):
        Draft.model_validate(payload)


def test_reducer_keeps_highest_score_and_stably_orders_ties_without_mutation():
    left = [
        evidence(identifier="ev-b", score=2).model_dump(),
        evidence(identifier="ev-a", score=1).model_dump(),
    ]
    right = [
        evidence(identifier="ev-a", score=3).model_dump(),
        evidence(identifier="ev-c", score=2).model_dump(),
    ]
    original = deepcopy((left, right))
    merged = merge_evidence(left, right)
    assert [(item["id"], item["score"]) for item in merged] == [
        ("ev-a", 3),
        ("ev-b", 2),
        ("ev-c", 2),
    ]
    assert (left, right) == original


def test_reducer_is_associative_idempotent_and_independent_of_branch_order():
    # IDs denote the same immutable passage across branches; only scores vary.
    branches = [
        [evidence(identifier="ev-a", score=1).model_dump()],
        [evidence(identifier="ev-b", score=3).model_dump()],
        [evidence(identifier="ev-a", score=4).model_dump()],
    ]
    expected = merge_evidence(merge_evidence(branches[0], branches[1]), branches[2])
    assert expected == merge_evidence(branches[0], merge_evidence(branches[1], branches[2]))
    assert merge_evidence(expected, expected) == expected
    for ordered in permutations(branches):
        merged = []
        for branch in ordered:
            merged = merge_evidence(merged, branch)
        assert merged == expected


def test_reducer_empty_identity_preserves_every_distinct_passage():
    passages = [
        evidence(identifier="ev-one", score=2).model_dump(),
        evidence(identifier="ev-two", score=1).model_dump(),
    ]
    assert merge_evidence([], []) == []
    assert merge_evidence(passages, []) == passages
    assert merge_evidence([], passages) == passages
