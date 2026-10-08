"""A local CLI with persistent runs and explicit human approval."""

import argparse
import json
import re
import sqlite3
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from rich.console import Console
from rich.table import Table

from evidenceloop.backends import DemoBackend, OllamaBackend
from evidenceloop.graph import build_graph, initial_state
from evidenceloop.reporting import atomic_write, render_report, state_json
from evidenceloop.retrieval import LocalRetriever

DEFAULT_DB = ".evidenceloop/checkpoints.sqlite"
console = Console(highlight=False)


@contextmanager
def database(path: str):
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(destination, check_same_thread=False)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS evidenceloop_runs "
        "(run_id TEXT PRIMARY KEY, settings TEXT NOT NULL)"
    )
    connection.commit()
    try:
        yield connection, SqliteSaver(connection)
    finally:
        connection.close()


def configuration(run_id: str) -> dict:
    return {"configurable": {"thread_id": run_id}, "recursion_limit": 80}


def settings_for(connection, run_id: str) -> dict:
    row = connection.execute(
        "SELECT settings FROM evidenceloop_runs WHERE run_id = ?", (run_id,)
    ).fetchone()
    if not row:
        raise ValueError(f"Unknown run '{run_id}'. Check --db and the run ID.")
    return json.loads(row[0])


def backend_for(settings: dict):
    if settings["backend"] == "demo":
        return DemoBackend(scenario=settings["scenario"])
    return OllamaBackend(model=settings["model"])


def show_state(run_id: str, state: dict) -> None:
    console.print(f"Run: {run_id} | Status: {state.get('status', 'unknown')}", markup=False)
    console.print(
        f"Drafts: {state.get('draft_attempts', 0)}/{state.get('max_drafts', 0)} | "
        f"Evidence passages: {len(state.get('evidence', []))}",
        markup=False,
    )
    table = Table("Node", "Attempt", "Decision / detail")
    for event in state.get("events", []):
        table.add_row(
            str(event.get("node", "")),
            str(event.get("attempt", "")),
            str(event.get("detail", "")),
        )
    console.print(table)
    if state.get("draft"):
        console.print("\nCurrent draft (not a final export):", style="bold")
        for claim in state["draft"]["claims"]:
            ids = ", ".join(citation["evidence_id"] for citation in claim["citations"])
            console.print(f"• {claim['text']} [{ids or 'UNCITED'}]", markup=False)
    for key in ("error", "review_error"):
        if state.get(key):
            console.print(str(state[key]), style="red", markup=False)
    if state.get("status") == "awaiting_review":
        console.print(
            f"\nReview with: evidenceloop review {run_id} --action approve\n"
            "Use --action revise --feedback '...' or --action reject as needed. "
            "Pass the same --db if you used a custom database.",
            markup=False,
        )


def run_command(args) -> int:
    run_id = args.run_id or uuid.uuid4().hex[:12]
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", run_id):
        raise ValueError("Run IDs must use 1–80 letters, digits, underscores, or dashes.")
    state = initial_state(args.question, args.max_drafts, not args.no_review)
    retriever = (
        LocalRetriever.from_directory(Path(args.corpus))
        if args.corpus
        else LocalRetriever.bundled()
    )
    settings = {"backend": args.backend, "scenario": args.scenario, "model": args.model}
    with database(args.db) as (connection, saver):
        if connection.execute(
            "SELECT 1 FROM evidenceloop_runs WHERE run_id = ?", (run_id,)
        ).fetchone():
            raise ValueError("That run ID already exists. Inspect/review it or use a new run ID.")
        backend = backend_for(settings)
        connection.execute(
            "INSERT INTO evidenceloop_runs VALUES (?, ?)", (run_id, json.dumps(settings))
        )
        connection.commit()
        graph = build_graph(backend, retriever, saver)
        graph.invoke(state, configuration(run_id))
        saved = dict(graph.get_state(configuration(run_id)).values)
    show_state(run_id, saved)
    return 2 if saved["status"] in {"failed", "exhausted", "insufficient_evidence"} else 0


def existing_command(args) -> int:
    with database(args.db) as (connection, saver):
        settings = settings_for(connection, args.run_id)
        # Retrieval is not repeated on review: evidence comes from the checkpoint.
        backend = backend_for(settings) if args.command == "review" else DemoBackend()
        graph = build_graph(backend, LocalRetriever.bundled(), saver)
        config = configuration(args.run_id)
        snapshot = graph.get_state(config)
        if not snapshot.values:
            raise ValueError("Run metadata exists but no checkpoint was saved.")
        if args.command == "review":
            if not snapshot.interrupts:
                raise ValueError("This run is not waiting for review. Inspect it for its status.")
            graph.invoke(Command(resume={"action": args.action, "feedback": args.feedback}), config)
            snapshot = graph.get_state(config)
        state = dict(snapshot.values)
    if args.command == "export":
        output = Path(args.output).resolve()
        database_path = Path(args.db).resolve()
        reserved = {
            database_path,
            *(Path(str(database_path) + suffix) for suffix in ("-wal", "-shm", "-journal")),
        }
        if output in reserved or (output.exists() and output.samefile(database_path)):
            raise ValueError(
                "Report output must not replace the checkpoint database or its sidecars."
            )
        atomic_write(Path(args.output), render_report(state, settings["backend"]))
        console.print(f"Exported approved report to {args.output}", markup=False)
    elif args.command == "inspect" and args.json:
        sys.stdout.write(state_json(state))
    else:
        show_state(args.run_id, state)
    return 2 if state["status"] in {"failed", "exhausted", "insufficient_evidence"} else 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="EvidenceLoop: a bounded research and review graph.")
    subcommands = root.add_subparsers(dest="command", required=True)
    run = subcommands.add_parser("run", help="Start a new research run (offline demo by default).")
    run.add_argument("question")
    run.add_argument("--corpus", help="Folder of local Markdown/text evidence.")
    run.add_argument("--backend", choices=["demo", "ollama"], default="demo")
    run.add_argument("--scenario", choices=["clean", "repair", "reject"], default="repair")
    run.add_argument("--model", default="llama3.2", help="An already installed Ollama model.")
    run.add_argument("--max-drafts", type=int, default=3)
    run.add_argument(
        "--no-review", action="store_true", help="Stop at 'ready'; cannot export as approved."
    )
    run.add_argument("--run-id")
    run.add_argument("--db", default=DEFAULT_DB)
    for name in ("review", "inspect", "export"):
        command = subcommands.add_parser(name)
        command.add_argument("run_id")
        command.add_argument("--db", default=DEFAULT_DB)
        if name == "review":
            command.add_argument("--action", required=True, choices=["approve", "revise", "reject"])
            command.add_argument("--feedback", default="")
        if name == "inspect":
            command.add_argument(
                "--json", action="store_true", help="Print the state and event trace as JSON."
            )
        if name == "export":
            command.add_argument("--output", required=True)
    subcommands.add_parser("graph", help="Print the compiled graph as Mermaid.")
    evaluate = subcommands.add_parser(
        "evaluate", help="Run the deterministic control-flow evaluation."
    )
    evaluate.add_argument("--output")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "run":
            return run_command(args)
        if args.command in {"review", "inspect", "export"}:
            return existing_command(args)
        if args.command == "graph":
            from langgraph.checkpoint.memory import InMemorySaver

            graph = build_graph(DemoBackend(), LocalRetriever.bundled(), InMemorySaver())
            print(graph.get_graph().draw_mermaid())
            return 0
        if args.command == "evaluate":
            from evidenceloop.evaluation import evaluate

            result = evaluate()
            serialized = json.dumps(result, indent=2) + "\n"
            if args.output:
                atomic_write(Path(args.output), serialized)
            print(serialized)
            return 0 if result["passed"] == result["total"] else 1
    except (ValueError, OSError, sqlite3.Error) as error:
        console.print(f"Error: {error}", style="red", markup=False)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
