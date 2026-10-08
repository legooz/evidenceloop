from pathlib import Path

import pytest

from evidenceloop.retrieval import MAX_CHUNK_CHARS, MAX_FILE_BYTES, LocalRetriever


def test_retrieval_returns_exact_lines_and_stable_portable_ids(tmp_path: Path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    content = "# Note\n\nRetry transient failures.\nUse an attempt budget.\n\nUnrelated apples.\n"
    for directory in (first, second):
        (directory / "note.md").write_text(content, encoding="utf-8")
    matches = LocalRetriever.from_directory(first).search("retry budget")
    assert len(matches) == 1
    match = matches[0]
    assert (match.source, match.start_line, match.end_line) == ("note.md", 3, 4)
    assert match.text == "\n".join(content.splitlines()[2:4])
    assert match.id == LocalRetriever.from_directory(second).search("retry budget")[0].id
    (second / "note.md").write_text(content.replace("transient", "temporary"), encoding="utf-8")
    assert match.id != LocalRetriever.from_directory(second).search("retry budget")[0].id


def test_unknown_and_stopword_only_queries_do_not_fabricate_evidence():
    retriever = LocalRetriever.bundled()
    assert retriever.search("orbital marmalade quantumgardening") == []
    assert retriever.search("how should we do it") == []
    assert retriever.search("") == []


def test_ranking_is_deterministic_and_results_are_detached(tmp_path: Path):
    for name in ("b.md", "a.md"):
        (tmp_path / name).write_text("Retry transient failures.", encoding="utf-8")
    retriever = LocalRetriever.from_directory(tmp_path)
    results = retriever.search("retries", limit=2)
    assert [item.source for item in results] == ["a.md", "b.md"]
    results[0].text = "tampered"
    assert retriever.search("retries")[0].text == "Retry transient failures."


def test_long_lines_stay_bounded(tmp_path: Path):
    (tmp_path / "long.txt").write_text("retry " * 900, encoding="utf-8")
    results = LocalRetriever.from_directory(tmp_path).search("retry", limit=20)
    assert len(results) == 3
    assert len({item.id for item in results}) == 3
    assert all(len(item.text) <= MAX_CHUNK_CHARS for item in results)
    assert all(item.start_line == item.end_line == 1 for item in results)


def test_file_size_is_enforced_before_decode(tmp_path: Path):
    (tmp_path / "large.md").write_bytes(b"x" * (MAX_FILE_BYTES + 1))
    with pytest.raises(ValueError, match="1 MiB"):
        LocalRetriever.from_directory(tmp_path)


def test_symlinked_files_and_directories_are_not_read(tmp_path: Path):
    corpus = tmp_path / "corpus"
    outside = tmp_path / "outside"
    corpus.mkdir()
    outside.mkdir()
    (outside / "secret.md").write_text("sensitive canary", encoding="utf-8")
    (corpus / "local.md").write_text("ordinary material", encoding="utf-8")
    try:
        (corpus / "linked.md").symlink_to(outside / "secret.md")
        (corpus / "linked_dir").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Host does not permit creating test symlinks")
    assert LocalRetriever.from_directory(corpus).search("canary") == []


def test_file_count_limit_and_unsupported_files(tmp_path: Path):
    (tmp_path / "ignore.py").write_text("retrieval canary", encoding="utf-8")
    assert LocalRetriever.from_directory(tmp_path).search("canary") == []
    for number in range(201):
        (tmp_path / f"{number}.md").write_text("small", encoding="utf-8")
    with pytest.raises(ValueError, match="200-file"):
        LocalRetriever.from_directory(tmp_path)


@pytest.mark.parametrize("limit", [0, -1, 21])
def test_retrieval_limit_is_bounded(limit: int):
    with pytest.raises(ValueError, match="between 1 and 20"):
        LocalRetriever.bundled().search("retry", limit=limit)
