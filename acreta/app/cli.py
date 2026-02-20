"""Command-line interface for Acreta runtime, memory, and service operations."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from acreta import __version__
from acreta.adapters.registry import (
    KNOWN_PLATFORMS,
    connect_platform,
    get_connected_agents,
    list_platforms,
    load_platforms,
    remove_platform,
)
from acreta.app.arg_utils import (
    parse_agent_filter,
    parse_csv,
    parse_duration_to_seconds,
)
from acreta.app.dashboard import run_dashboard_server
from acreta.app.daemon import resolve_window_bounds, run_maintain_once, run_sync_once
from acreta.app.daemon import run_daemon_forever, run_daemon_once
from acreta.config.project_scope import resolve_data_dirs
from acreta.config.logging import configure_logging
from acreta.config.settings import get_config
from acreta.memory.memory_repo import build_memory_paths, reset_memory_root
from acreta.memory.memory_record import Learning, LearningType, PrimitiveType
from acreta.memory.memory_repo import MemoryRepository
from acreta.runtime.agent import AcretaAgent
from acreta.sessions.catalog import count_fts_indexed, count_session_jobs_by_status, latest_service_run


def _emit(message: object = "", *, file: Any | None = None) -> None:
    """Write one CLI output line to stdout or a provided file-like target."""
    target = file if file is not None else sys.stdout
    target.write(f"{message}\n")


def _hoist_global_json_flag(raw: list[str]) -> list[str]:
    """Allow ``--json`` before or after subcommands by normalizing argv order."""
    if "--json" not in raw:
        return raw
    return ["--json"] + [item for item in raw if item != "--json"]


def _format_learning(learning: Learning) -> str:
    """Render one compact human-readable learning summary line."""
    return (
        f"{learning.id} [{learning.primitive.value}] "
        f"conf={learning.confidence:.2f} "
        f"title={learning.title}"
    )


def _memory_store() -> MemoryRepository:
    """Create the canonical file-backed memory store instance."""
    config = get_config()
    return MemoryRepository(config.memory_dir, config.memory_dir.parent / "meta")


def _load_context_docs_for_chat(
    *,
    question: str,
    memory_hit_count: int,
    result_limit: int,
    project: str | None,
) -> list[dict[str, Any]]:
    """Load optional context docs for chat prompts (disabled in this build)."""
    _ = (question, memory_hit_count, result_limit, project)
    return []


def search_memory(
    question: str,
    project_filter: str | None = None,
    limit: int = 20,
) -> list[Learning]:
    """Search memory by keyword tokens with stable list-all fallback."""
    store = _memory_store()
    learnings = store.list_all(project=project_filter)
    if not question.strip():
        return learnings[:limit]
    tokens = [token.lower() for token in question.split() if token.strip()]
    hits: list[Learning] = []
    for learning in learnings:
        haystack = " ".join([learning.title, learning.body, " ".join(learning.tags), " ".join(learning.related)]).lower()
        if any(token in haystack for token in tokens):
            hits.append(learning)
    return (hits or learnings)[:limit]


def _build_chat_prompt(question: str, hits: list[Learning], context_docs: list[dict[str, Any]]) -> str:
    """Build the final agent prompt with memory/context evidence blocks."""
    context_lines = [
        (
            f"- {learning.id} [{learning.primitive.value}] conf={learning.confidence:.2f}: "
            f"{learning.title} :: {(learning.body or '').strip()[:260]}"
        )
        for learning in hits
    ]
    context_block = "\n".join(context_lines) or "(no relevant memories)"

    context_doc_lines = []
    for row in context_docs:
        doc_id = str(row.get("doc_id") or "")
        title = str(row.get("title") or "")
        body = str(row.get("body") or "").strip()
        snippet = " ".join(body.split())[:260]
        context_doc_lines.append(f"- {doc_id}: {title} :: {snippet}")
    context_doc_block = "\n".join(context_doc_lines) if context_doc_lines else "(no context docs loaded)"

    return (
        "Answer the user question using the memory evidence below.\n"
        "Retrieval contract:\n"
        "- Lead handles retrieval strategy.\n"
        "- Delegate parallel read-only Task explorers with dynamic fan-out.\n"
        "- Search project-first, then global fallback.\n"
        "- Return evidence with file paths and line refs.\n"
        "- Use explicit ids/slugs only in related references (no wikilink syntax).\n"
        "If memory is missing or uncertain, say that clearly.\n"
        "Cite learning ids and context doc ids you used.\n\n"
        f"Question:\n{question}\n\n"
        f"Memory evidence:\n{context_block}\n"
        f"\nContext docs (loaded only if needed):\n{context_doc_block}\n"
    )


def _cmd_connect(args: argparse.Namespace) -> int:
    """Handle ``acreta connect`` actions (list/auto/remove/connect)."""
    config = get_config()
    platforms_path = config.platforms_path
    action = getattr(args, "platform_name", None)

    if action == "list" or action is None:
        entries = list_platforms(platforms_path)
        if not entries:
            _emit("No platforms connected.")
            return 0
        _emit(f"Connected platforms: {len(entries)}")
        for entry in entries:
            status = "ok" if entry["exists"] else "missing"
            _emit(f"- {entry['name']}: {entry['path']} ({entry['session_count']} sessions, {status})")
        return 0

    if action == "auto":
        connected = 0
        for name in KNOWN_PLATFORMS:
            result = connect_platform(platforms_path, name, custom_path=None)
            if result.get("status") == "connected":
                connected += 1
        _emit(f"Auto connected: {connected}")
        return 0

    if action == "remove":
        name = getattr(args, "extra_arg", None)
        if not name:
            _emit("Usage: acreta connect remove <platform>", file=sys.stderr)
            return 2
        removed = remove_platform(platforms_path, name)
        _emit(f"Removed: {name}" if removed else f"Platform not connected: {name}")
        return 0

    name = action
    if name not in KNOWN_PLATFORMS:
        _emit(f"Unknown platform: {name}", file=sys.stderr)
        _emit(f"Known platforms: {', '.join(KNOWN_PLATFORMS)}", file=sys.stderr)
        return 2

    existing = load_platforms(platforms_path)
    existing_path = (existing.get("platforms", {}).get(name) or {}).get("path")
    result = connect_platform(platforms_path, name, custom_path=getattr(args, "path", None))
    status = str(result.get("status") or "")
    if status == "path_not_found":
        _emit(f"Path not found: {result.get('path')}", file=sys.stderr)
        return 1
    if status == "unknown_platform":
        _emit(f"Unknown platform: {name}", file=sys.stderr)
        return 1

    _emit(f"Connected: {name}")
    _emit(f"- Path: {result.get('path')}")
    _emit(f"- Sessions: {result.get('session_count')}")
    if existing_path and existing_path == result.get("path"):
        _emit("- Path unchanged, no initial reindex trigger.")
    return 0


def _cmd_sync(args: argparse.Namespace) -> int:
    """Run one sync command invocation and print summary output."""
    try:
        window_start, window_end = resolve_window_bounds(
            window=args.window,
            since_raw=args.since,
            until_raw=args.until,
            parse_duration_to_seconds=parse_duration_to_seconds,
        )
    except ValueError as exc:
        _emit(str(exc), file=sys.stderr)
        return 2

    code, summary = run_sync_once(
        run_id=args.run_id,
        agent_filter=parse_agent_filter(args.agent),
        no_extract=args.no_extract,
        force=args.force,
        max_sessions=args.max_sessions,
        dry_run=args.dry_run,
        ignore_lock=args.ignore_lock,
        trigger="manual",
        window_start=window_start,
        window_end=window_end,
    )
    payload = asdict(summary)
    if args.json:
        _emit(json.dumps(payload, indent=2, ensure_ascii=True))
    else:
        _emit("Sync summary:")
        for key, value in payload.items():
            _emit(f"- {key}: {value}")
    return code


def _cmd_maintain(args: argparse.Namespace) -> int:
    """Run one maintain command invocation and print summary output."""
    code, payload = run_maintain_once(
        window=args.window,
        since_raw=args.since,
        until_raw=args.until,
        steps_raw=args.steps,
        agent_raw=args.agent,
        force=args.force,
        dry_run=args.dry_run,
        parse_duration_to_seconds=parse_duration_to_seconds,
        parse_csv=parse_csv,
        parse_agent_filter=parse_agent_filter,
    )
    if args.json:
        _emit(json.dumps(payload, indent=2, ensure_ascii=True))
    else:
        _emit("Maintain summary:")
        for key, value in payload.items():
            _emit(f"- {key}: {value}")
    return code


def _cmd_daemon(args: argparse.Namespace) -> int:
    """Handle daemon commands for one-shot or continuous execution."""
    if args.once:
        payload = run_daemon_once()
        if args.json:
            _emit(json.dumps(payload, indent=2, ensure_ascii=True))
        else:
            _emit("Daemon once result:")
            for key, value in payload.items():
                _emit(f"- {key}: {value}")
        return 0
    run_daemon_forever(poll_seconds=args.poll_seconds)
    return 0


def _cmd_dashboard(args: argparse.Namespace) -> int:
    """Run the dashboard server with provided host/port args."""
    return run_dashboard_server(host=args.host, port=args.port)


def _cmd_memory_search(args: argparse.Namespace) -> int:
    """Search stored memories and print list or JSON output."""
    hits = search_memory(args.query, limit=args.limit, project_filter=args.project)
    if args.json:
        _emit(json.dumps([item.model_dump(mode="json") for item in hits], indent=2, ensure_ascii=True))
        return 0
    if not hits:
        _emit("No matching memories.")
        return 0
    for learning in hits:
        _emit(_format_learning(learning))
    return 0


def _cmd_memory_list(args: argparse.Namespace) -> int:
    """List recent memories, optionally filtered by project."""
    store = _memory_store()
    learnings = store.list_all(project=args.project)
    learnings = sorted(learnings, key=lambda item: item.updated, reverse=True)[: args.limit]
    if args.json:
        _emit(json.dumps([item.model_dump(mode="json") for item in learnings], indent=2, ensure_ascii=True))
        return 0
    for learning in learnings:
        _emit(_format_learning(learning))
    return 0


def _cmd_memory_add(args: argparse.Namespace) -> int:
    """Add one memory item from CLI flags."""
    store = _memory_store()
    primitive = PrimitiveType(str(args.primitive or "learning"))
    learning_type = LearningType(str(args.learning_type or "insight"))
    kind = str(args.kind or learning_type.value or "insight")
    learning = Learning(
        id=store.generate_id(primitive),
        title=args.title,
        body=args.body,
        primitive=primitive,
        learning_type=learning_type,
        kind=kind,
        status=str(args.status or "active"),
        decided_by=str(args.decided_by or "agent"),
        confidence=args.confidence,
        projects=parse_csv(args.project),
        tags=parse_csv(args.tags),
        related=parse_csv(args.related),
        agent_types=parse_csv(args.agent),
        source_sessions=parse_csv(args.session),
        signal_sources=["user_agent"],
    )
    store.write(learning)
    _emit(f"Added memory: {learning.id}")
    return 0


def _cmd_memory_feedback(args: argparse.Namespace) -> int:
    """Update useful/not-useful counters for one memory."""
    store = _memory_store()
    learning = store.read(args.learning_id)
    if learning is None:
        _emit(f"Learning not found: {args.learning_id}", file=sys.stderr)
        return 1
    if args.useful:
        learning.useful_count += 1
    if args.not_useful:
        learning.not_useful_count += 1
    store.update(learning)
    _emit(f"Updated feedback for: {learning.id}")
    return 0


def _cmd_memory_export(args: argparse.Namespace) -> int:
    """Export memories as Markdown or JSON to stdout or a file."""
    store = _memory_store()
    learnings = store.list_all(project=args.project)
    if args.format == "json":
        payload = [item.model_dump(mode="json") for item in learnings]
        output = json.dumps(payload, indent=2, ensure_ascii=True)
    else:
        lines = ["# Acreta Memory Export", ""]
        for learning in learnings:
            lines.append(f"## {learning.title} ({learning.id})")
            lines.append(f"- primitive: {learning.primitive.value}")
            lines.append(f"- confidence: {learning.confidence:.2f}")
            lines.append(learning.body.strip())
            lines.append("")
        output = "\n".join(lines)
    if args.output:
        path = Path(args.output).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(output + ("\n" if not output.endswith("\n") else ""), encoding="utf-8")
        _emit(f"Exported: {path}")
    else:
        _emit(output)
    return 0


def _cmd_chat(args: argparse.Namespace) -> int:
    """Run one chat query against the runtime agent."""
    hits: list[Learning] = []
    context_docs = _load_context_docs_for_chat(
        question=args.question,
        memory_hit_count=len(hits),
        result_limit=args.limit,
        project=args.project,
    )
    prompt = _build_chat_prompt(args.question, hits, context_docs)
    agent = AcretaAgent(
        skills=["acreta"],
    )
    response, session_id = agent.run_sync(prompt, cwd=str(Path.cwd()))
    if _looks_like_auth_error(response):
        _emit(response, file=sys.stderr)
        return 1
    if args.json:
        _emit(
            json.dumps(
                {
                    "response": response,
                    "agent_session_id": session_id,
                    "memory_ids": [learning.id for learning in hits],
                    "context_doc_ids": [str(row.get("doc_id")) for row in context_docs if row.get("doc_id")],
                    "fallback_used": False,
                },
                indent=2,
                ensure_ascii=True,
            )
        )
    else:
        _emit(response)
    return 0


def _looks_like_auth_error(response: str) -> bool:
    """Return whether the response text indicates auth configuration failure."""
    text = str(response or "").lower()
    return (
        "failed to authenticate" in text
        or "authentication_error" in text
        or "oauth token has expired" in text
        or "invalid api key" in text
        or "unauthorized" in text
    )


def _cmd_memory_reset(args: argparse.Namespace) -> int:
    """Reset memory/meta/index trees for project/global roots."""
    if not args.yes:
        _emit("Refusing to reset without --yes", file=sys.stderr)
        return 2
    config = get_config()
    resolved = resolve_data_dirs(
        scope=config.memory_scope,
        project_dir_name=config.memory_project_dir_name,
        global_data_dir=config.global_data_dir or config.data_dir,
        repo_path=Path.cwd(),
    )
    targets: list[Path] = []
    selected_scope = str(args.scope or "both")
    if selected_scope in {"project", "both"} and resolved.project_data_dir:
        targets.append(resolved.project_data_dir)
    if selected_scope in {"global", "both"}:
        targets.append(resolved.global_data_dir)

    seen: set[Path] = set()
    summaries: list[dict[str, Any]] = []
    for data_root in targets:
        root = data_root.resolve()
        if root in seen:
            continue
        seen.add(root)
        layout = build_memory_paths(root)
        result = reset_memory_root(layout)
        summaries.append({"data_dir": str(root), "removed": result.get("removed") or []})

    if args.json:
        _emit(json.dumps({"reset": summaries}, indent=2, ensure_ascii=True))
    else:
        _emit("Memory reset completed:")
        for item in summaries:
            _emit(f"- {item['data_dir']}: removed={len(item['removed'])}")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    """Print runtime status summary across memory, queue, and services."""
    config = get_config()
    memory_count = len(_memory_store().list_all())
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "connected_agents": get_connected_agents(config.platforms_path),
        "platforms": list_platforms(config.platforms_path),
        "memory_count": memory_count,
        "sessions_indexed_count": count_fts_indexed(),
        "queue": count_session_jobs_by_status(),
        "latest_sync": latest_service_run("sync"),
        "latest_maintain": latest_service_run("maintain"),
    }
    if args.json:
        _emit(json.dumps(payload, indent=2, ensure_ascii=True))
    else:
        _emit("Acreta status:")
        _emit(f"- connected_agents: {len(payload['connected_agents'])}")
        _emit(f"- memory_count: {payload['memory_count']}")
        _emit(f"- sessions_indexed_count: {payload['sessions_indexed_count']}")
        _emit(f"- queue: {payload['queue']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Construct the canonical Acreta command-line parser."""
    parser = argparse.ArgumentParser(prog="acreta", description="Acreta minimal core CLI")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--json", action="store_true", help="Output JSON when supported")
    sub = parser.add_subparsers(dest="command")

    connect = sub.add_parser("connect", help="Manage connected agent platforms")
    connect.add_argument("platform_name", nargs="?", help="Platform name, 'list', 'auto', or 'remove'")
    connect.add_argument("extra_arg", nargs="?", help="Extra argument for connect sub-actions")
    connect.add_argument("--path", help="Custom platform path")
    connect.set_defaults(func=_cmd_connect)

    sync = sub.add_parser("sync", help="Run hot-path indexing + extraction")
    sync.add_argument("--run-id")
    sync.add_argument("--agent", help="Comma-separated agent filter")
    sync.add_argument("--window", default="30d")
    sync.add_argument("--since")
    sync.add_argument("--until")
    sync.add_argument("--max-sessions", type=int, default=50)
    sync.add_argument("--no-extract", action="store_true")
    sync.add_argument("--force", action="store_true")
    sync.add_argument("--dry-run", action="store_true")
    sync.add_argument("--ignore-lock", action="store_true")
    sync.set_defaults(func=_cmd_sync)

    maintain = sub.add_parser("maintain", help="Run cold-path maintenance")
    maintain.add_argument("--window", default="30d")
    maintain.add_argument("--since")
    maintain.add_argument("--until")
    maintain.add_argument("--steps", help="Comma-separated maintenance steps")
    maintain.add_argument("--agent", help="Comma-separated agent filter")
    maintain.add_argument("--force", action="store_true")
    maintain.add_argument("--dry-run", action="store_true")
    maintain.set_defaults(func=_cmd_maintain)

    daemon = sub.add_parser("daemon", help="Run recurring sync + maintain loop")
    daemon.add_argument("--once", action="store_true")
    daemon.add_argument("--poll-seconds", type=int)
    daemon.set_defaults(func=_cmd_daemon)

    dashboard = sub.add_parser("dashboard", help="Run local dashboard server")
    dashboard.add_argument("--host")
    dashboard.add_argument("--port", type=int)
    dashboard.set_defaults(func=_cmd_dashboard)

    memory = sub.add_parser("memory", help="Memory store operations")
    memory_sub = memory.add_subparsers(dest="memory_command")

    memory_search = memory_sub.add_parser("search", help="Search memory")
    memory_search.add_argument("query")
    memory_search.add_argument("--project")
    memory_search.add_argument("--limit", type=int, default=20)
    memory_search.set_defaults(func=_cmd_memory_search)

    memory_list = memory_sub.add_parser("list", help="List memory items")
    memory_list.add_argument("--project")
    memory_list.add_argument("--limit", type=int, default=50)
    memory_list.set_defaults(func=_cmd_memory_list)

    memory_add = memory_sub.add_parser("add", help="Add a memory item")
    memory_add.add_argument("--title", required=True)
    memory_add.add_argument("--body", required=True)
    memory_add.add_argument(
        "--primitive",
        default="learning",
        choices=[item.value for item in PrimitiveType],
        help="Primitive type to create",
    )
    memory_add.add_argument(
        "--learning-type",
        default="insight",
        choices=[item.value for item in LearningType],
        help="Learning subtype for learning memories",
    )
    memory_add.add_argument("--kind", help="Learning kind")
    memory_add.add_argument("--status", help="Decision status")
    memory_add.add_argument("--decided-by", help="Decision owner: user|agent|both")
    memory_add.add_argument("--confidence", type=float, default=0.7)
    memory_add.add_argument("--project")
    memory_add.add_argument("--tags")
    memory_add.add_argument("--related", help="Comma-separated related ids or slugs")
    memory_add.add_argument("--agent")
    memory_add.add_argument("--session")
    memory_add.set_defaults(func=_cmd_memory_add)

    memory_feedback = memory_sub.add_parser("feedback", help="Adjust feedback counters")
    memory_feedback.add_argument("learning_id")
    memory_feedback.add_argument("--useful", action="store_true")
    memory_feedback.add_argument("--not-useful", action="store_true")
    memory_feedback.set_defaults(func=_cmd_memory_feedback)

    memory_export = memory_sub.add_parser("export", help="Export memories")
    memory_export.add_argument("--project")
    memory_export.add_argument("--format", choices=["json", "markdown"], default="markdown")
    memory_export.add_argument("--output")
    memory_export.set_defaults(func=_cmd_memory_export)

    memory_reset = memory_sub.add_parser("reset", help="Destructive reset of memory data for selected scope")
    memory_reset.add_argument("--scope", choices=["project", "global", "both"], default="both")
    memory_reset.add_argument("--yes", action="store_true", help="Confirm destructive reset")
    memory_reset.set_defaults(func=_cmd_memory_reset)

    chat = sub.add_parser("chat", help="Ask the central agent with memory context")
    chat.add_argument("question")
    chat.add_argument("--project")
    chat.add_argument("--limit", type=int, default=12)
    chat.set_defaults(func=_cmd_chat)

    status = sub.add_parser("status", help="Show core runtime status")
    status.set_defaults(func=_cmd_status)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Entrypoint for CLI invocation with global flags and dispatch."""
    configure_logging()
    parser = build_parser()
    args = parser.parse_args(_hoist_global_json_flag(list(argv or sys.argv[1:])))

    if not getattr(args, "command", None):
        parser.print_help()
        return 0

    if args.command == "memory" and not getattr(args, "memory_command", None):
        parser.parse_args([args.command, "--help"])
        return 0

    handler = getattr(args, "func", None)
    if handler is None:
        parser.print_help()
        return 2
    return int(handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
