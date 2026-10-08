import json
import os
import subprocess
import sys


def invoke(*args):
    return subprocess.run(
        [sys.executable, "-m", "evidenceloop.cli", *map(str, args)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        env={**os.environ, "PYTHONUTF8": "1"},
    )


def test_separate_process_review_and_export(tmp_path):
    db = tmp_path / "saved.sqlite"
    report = tmp_path / "answer.md"
    run = invoke("run", "How should retries use idempotency?", "--run-id", "portfolio", "--db", db)
    assert run.returncode == 0, run.stderr + run.stdout
    early = invoke("export", "portfolio", "--db", db, "--output", report)
    assert early.returncode == 1
    assert not report.exists()
    inspected = invoke("inspect", "portfolio", "--db", db, "--json")
    state = json.loads(inspected.stdout)
    assert state["status"] == "awaiting_review"
    assert state["draft_attempts"] == 2
    review = invoke("review", "portfolio", "--db", db, "--action", "approve")
    assert review.returncode == 0, review.stderr + review.stdout
    exported = invoke("export", "portfolio", "--db", db, "--output", report)
    assert exported.returncode == 0, exported.stderr + exported.stdout
    assert "**Status:** approved" in report.read_text(encoding="utf-8")
    assert "Evidence ledger" in report.read_text(encoding="utf-8")
    original = report.read_bytes()
    assert invoke("export", "portfolio", "--db", db, "--output", report).returncode == 0
    assert report.read_bytes() == original
    protected = invoke("export", "portfolio", "--db", db, "--output", db)
    assert protected.returncode == 1
    assert "must not replace" in protected.stdout
    assert invoke("inspect", "portfolio", "--db", db).returncode == 0
    duplicate = invoke("run", "new question", "--run-id", "portfolio", "--db", db)
    assert duplicate.returncode == 1
    repeat_review = invoke("review", "portfolio", "--db", db, "--action", "approve")
    assert repeat_review.returncode == 1


def test_unknown_run_fails_cleanly(tmp_path):
    result = invoke("inspect", "missing", "--db", tmp_path / "saved.sqlite")
    assert result.returncode == 1
    assert "Unknown run" in result.stdout
    assert "Traceback" not in result.stderr
