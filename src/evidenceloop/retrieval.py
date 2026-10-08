"""Small, deterministic BM25 retrieval over bounded local Markdown/text corpora.

Use ``LocalRetriever.bundled()`` for the original synthetic learning fixtures, or
``LocalRetriever.from_directory(path)`` for a directory you trust and own. This
retriever does not fetch URLs, execute documents, or follow symbolic links.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
from collections import Counter
from pathlib import Path

from .models import Evidence

MAX_FILES = 200
MAX_FILE_BYTES = 1_048_576
MAX_CORPUS_BYTES = 8_388_608
MAX_CHUNK_CHARS = 2_000
MAX_CHUNKS = 10_000
_STOPWORDS = frozenset(
    "a an and are as at be been but by can could do does for from had has have how "
    "i if in into is it its may my of on or our should so than that the their then "
    "there these they this to was we were what when where which who why will with "
    "would you your".split()
)
_ALIASES = {
    "retries": "retry",
    "retried": "retry",
    "retrying": "retry",
    "checkpoints": "checkpoint",
    "checkpointing": "checkpoint",
    "budgets": "budget",
    "loops": "loop",
    "claims": "claim",
    "citations": "citation",
    "evaluations": "evaluation",
    "failures": "failure",
    "nodes": "node",
    "crashes": "crash",
}


def _tokens(text: str) -> list[str]:
    return [
        _ALIASES.get(word, word)
        for word in re.findall(r"[a-z0-9]+", text.lower())
        if word not in _STOPWORDS
    ]


def _linked(path: Path) -> bool:
    # Junctions can escape a Windows corpus just as symbolic links can.
    return path.is_symlink() or getattr(path, "is_junction", lambda: False)()


def _chunks(text: str, source: str) -> list[Evidence]:
    """Split on blank lines and a character bound; retain original line numbers."""
    chunks: list[Evidence] = []
    pending: list[str] = []
    first_line = 1
    last_line = 1

    def flush() -> None:
        if not pending:
            return
        body = "\n".join(pending)
        # Location participates in identity so identical paragraphs stay distinct.
        identity = f"{source}\0{first_line}\0{last_line}\0{len(chunks)}\0{body}"
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
        chunks.append(
            Evidence(
                id=f"ev-{digest}",
                source=source,
                start_line=first_line,
                end_line=last_line,
                text=body,
            )
        )
        pending.clear()

    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            flush()
            continue
        # Huge single lines are split into bounded excerpts on that same line.
        for offset in range(0, len(line), MAX_CHUNK_CHARS):
            part = line[offset : offset + MAX_CHUNK_CHARS]
            if pending and sum(map(len, pending)) + len(pending) + len(part) > MAX_CHUNK_CHARS:
                flush()
            if not pending:
                first_line = number
            last_line = number
            pending.append(part)
    flush()
    return chunks


class LocalRetriever:
    """BM25 retrieval whose ties sort by relative source, line, and content ID."""

    def __init__(self, evidence: list[Evidence]):
        self._evidence = tuple(item.model_copy(deep=True) for item in evidence)
        self._counts = [Counter(_tokens(item.text)) for item in self._evidence]
        self._lengths = [sum(counts.values()) for counts in self._counts]
        self._average_length = sum(self._lengths) / max(len(self._lengths), 1) or 1.0
        self._document_frequency: Counter[str] = Counter()
        for counts in self._counts:
            self._document_frequency.update(counts.keys())

    @classmethod
    def bundled(cls) -> LocalRetriever:
        """Load six original, explicitly synthetic project learning notes."""
        return cls.from_directory(Path(__file__).parent / "data" / "corpus")

    @classmethod
    def from_directory(cls, directory: str | Path) -> LocalRetriever:
        root = Path(directory).expanduser()
        if _linked(root) or not root.is_dir():
            raise ValueError("Corpus must be a local directory, not a symbolic link or junction.")
        root = root.resolve()
        paths: list[Path] = []
        directories_seen = 0
        for current, directories, names in os.walk(root, followlinks=False):
            directories_seen += 1
            if directories_seen > 1_000:
                raise ValueError("Corpus exceeds the 1,000-directory scanning limit.")
            directories[:] = sorted(
                name
                for name in directories
                if not name.startswith(".")
                and name not in {"node_modules", "__pycache__"}
                and not _linked(Path(current) / name)
            )
            for name in sorted(names):
                path = Path(current) / name
                if path.suffix.lower() not in {".md", ".txt"} or _linked(path):
                    continue
                if not path.is_file():
                    continue
                if not path.resolve().is_relative_to(root):
                    raise ValueError("A corpus file resolves outside the selected directory.")
                paths.append(path)
                if len(paths) > MAX_FILES:
                    raise ValueError(f"Corpus exceeds the {MAX_FILES}-file limit.")

        evidence: list[Evidence] = []
        total_bytes = 0
        for path in sorted(paths, key=lambda item: item.relative_to(root).as_posix()):
            with path.open("rb") as handle:
                raw = handle.read(MAX_FILE_BYTES + 1)
            if len(raw) > MAX_FILE_BYTES:
                raise ValueError("A corpus file exceeds the 1 MiB file limit.")
            total_bytes += len(raw)
            if total_bytes > MAX_CORPUS_BYTES:
                raise ValueError("Corpus exceeds the 8 MiB total size limit.")
            try:
                text = raw.decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise ValueError("Corpus text files must be UTF-8 encoded.") from exc
            evidence.extend(_chunks(text, path.relative_to(root).as_posix()))
            if len(evidence) > MAX_CHUNKS:
                raise ValueError(f"Corpus exceeds the {MAX_CHUNKS:,}-chunk limit.")
        return cls(evidence)

    def search(self, query: str, limit: int = 4) -> list[Evidence]:
        """Return up to ``limit`` matching excerpts; lexical non-matches stay empty.

        Scores are BM25 ranking values, never calibrated confidence estimates.
        """
        if not 1 <= limit <= 20:
            raise ValueError("Retrieval limit must be between 1 and 20.")
        terms = set(_tokens(query))
        ranked: list[Evidence] = []
        population = len(self._evidence)
        for item, counts, length in zip(self._evidence, self._counts, self._lengths, strict=True):
            score = 0.0
            for term in sorted(terms):
                frequency = counts.get(term, 0)
                if not frequency:
                    continue
                df = self._document_frequency[term]
                inverse_frequency = math.log(1 + (population - df + 0.5) / (df + 0.5))
                denominator = frequency + 1.5 * (0.25 + 0.75 * length / self._average_length)
                score += inverse_frequency * frequency * 2.5 / denominator
            if score > 0:
                ranked.append(item.model_copy(update={"score": round(score, 8)}, deep=True))
        return sorted(
            ranked, key=lambda item: (-item.score, item.source, item.start_line, item.id)
        )[:limit]
