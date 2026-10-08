"""Serializable contracts at the boundaries of retrieval, models, and the graph."""

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Evidence(StrictModel):
    id: str
    source: str
    start_line: int
    end_line: int
    text: str
    score: float = 0


class Citation(StrictModel):
    evidence_id: str
    quote: str = Field(min_length=1)


class Claim(StrictModel):
    text: str = Field(min_length=1)
    citations: list[Citation] = Field(default_factory=list)


class Draft(StrictModel):
    title: str = Field(min_length=1)
    claims: list[Claim] = Field(default_factory=list, max_length=8)
    limitations: list[str] = Field(default_factory=list, max_length=8)


class Critique(StrictModel):
    passed: bool
    feedback: list[str] = Field(default_factory=list, max_length=10)


class ReviewDecision(StrictModel):
    action: Literal["approve", "revise", "reject"]
    feedback: str = Field(default="", max_length=4000)


class BackendError(RuntimeError):
    """An expected model/service failure, safe to report without raw prompts."""


class Backend(Protocol):
    name: str

    def draft(
        self, question: str, evidence: list[Evidence], feedback: list[str], attempt: int
    ) -> Draft: ...

    def critique(self, question: str, evidence: list[Evidence], draft: Draft) -> Critique: ...
