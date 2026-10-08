"""Render inspected state; file publication is kept outside resumable graph nodes."""

import json
import os
import tempfile
from pathlib import Path

from evidenceloop.models import Draft, Evidence


def render_report(state: dict, backend: str = "unknown") -> str:
    if state.get("status") != "approved":
        raise ValueError("Only a human-approved run can be exported as a final report.")
    draft = Draft.model_validate(state["draft"])
    evidence = {item["id"]: Evidence.model_validate(item) for item in state["evidence"]}
    lines = [
        f"# {draft.title}",
        "",
        f"**Question:** {state['question']}",
        "",
        f"**Status:** approved | **Backend:** {backend} | "
        f"**Draft attempts:** {state['draft_attempts']}/{state['max_drafts']}",
        "",
    ]
    if backend == "demo":
        lines += [
            "> Offline extractive demonstration. No language model was used. "
            "The bundled corpus contains fictional engineering notes.",
            "",
        ]
    used = {}
    for claim in draft.claims:
        labels = []
        for citation in claim.citations:
            key = (citation.evidence_id, citation.quote)
            if key not in used:
                used[key] = len(used) + 1
            labels.append(f"[{used[key]}]")
        lines.extend([f"- {claim.text} {' '.join(labels)}", ""])
    if draft.limitations:
        lines += ["## Limitations", ""]
        lines += [f"- {limitation}" for limitation in draft.limitations] + [""]
    lines += ["## Evidence ledger", ""]
    for (evidence_id, quote), index in used.items():
        source = evidence[evidence_id]
        lines.extend(
            [
                f"**[{index}] {source.source}, lines {source.start_line}–{source.end_line}** "
                f"(`{source.id}`)",
                "",
                "> " + quote.replace("\n", "\n> "),
                "",
            ]
        )
    lines += [
        "Citation validation checks source IDs and quoted text. It does not prove that "
        "a quote supports its surrounding claim or that the underlying source is true.",
        "",
    ]
    return "\n".join(lines)


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=path.parent, delete=False
        ) as file:
            temporary = Path(file.name)
            file.write(text)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def state_json(state: dict) -> str:
    # Interrupt objects are runtime values; the persistent state is JSON-compatible.
    return (
        json.dumps(
            {key: value for key, value in state.items() if key != "__interrupt__"},
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
