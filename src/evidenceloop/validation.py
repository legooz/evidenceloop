"""Deterministic citation integrity checks; these do not prove factual support."""

import re
import unicodedata

from .models import Draft, Evidence


def _normalize(text: str) -> str:
    """Normalize Unicode compatibility characters and whitespace, preserving case."""
    return " ".join(unicodedata.normalize("NFKC", text).split())


def validate_citations(draft: Draft, evidence: list[Evidence]) -> list[str]:
    """Check every claim has known sources and nontrivial, verbatim evidence quotes.

    A matching quote can still be irrelevant to its claim. Semantic support belongs
    to the critic and human reviewer, not this structural validator.
    """
    sources = {item.id: _normalize(item.text) for item in evidence}
    errors: list[str] = []
    if not draft.claims:
        errors.append("The draft has no claims to support.")

    for number, claim in enumerate(draft.claims, start=1):
        prefix = f"Claim {number}"
        if not claim.text.strip():
            errors.append(f"{prefix} is empty.")
        if not claim.citations:
            errors.append(f"{prefix} has no citations.")
        for citation in claim.citations:
            source = sources.get(citation.evidence_id)
            if source is None:
                errors.append(f"{prefix} cites unknown evidence {citation.evidence_id!r}.")
                continue
            quote = _normalize(citation.quote)
            words = re.findall(r"[^\W_]+", quote, flags=re.UNICODE)
            if len(words) < 2 or sum(map(len, words)) < 8:
                errors.append(
                    f"{prefix} has an uninformative quote for {citation.evidence_id!r}; "
                    "use at least two words and eight letters or digits."
                )
            elif quote not in source:
                errors.append(
                    f"{prefix} quote is not present in evidence {citation.evidence_id!r}."
                )
    return errors
