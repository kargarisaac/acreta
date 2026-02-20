"""OpenCode session adapter for JSON session/message/part storage layout."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from acreta.adapters.base import SessionRecord, ViewerMessage, ViewerSession
from acreta.adapters.common import in_window, parse_timestamp


def default_path() -> Path | None:
    """Return the default OpenCode storage root."""
    return Path("~/.local/share/opencode/").expanduser()


def _parse_json_file(path: Path) -> dict[str, Any] | None:
    """Load a JSON object from disk; return ``None`` on invalid files."""
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _parse_timestamp_ms(value: int | float | None) -> str | None:
    """Parse millisecond epoch timestamps into ISO strings."""
    parsed = parse_timestamp(value)
    return parsed.isoformat() if parsed else None


def _resolve_storage_roots(traces_dir: Path | None = None) -> list[Path]:
    """Resolve OpenCode storage roots that contain a ``session`` directory."""
    if traces_dir:
        candidate = traces_dir.expanduser().resolve()
        if (candidate / "session").exists():
            return [candidate]
        if (candidate / "storage" / "session").exists():
            return [candidate / "storage"]
        return []

    base = default_path()
    if base is None:
        return []
    roots: list[Path] = []
    if (base / "session").exists():
        roots.append(base)

    direct = base / "storage"
    if (direct / "session").exists():
        roots.append(direct)

    project_root = base / "project"
    if project_root.exists():
        for project_dir in project_root.iterdir():
            candidate = project_dir / "storage"
            if (candidate / "session").exists():
                roots.append(candidate)

    global_root = base / "global" / "storage"
    if (global_root / "session").exists():
        roots.append(global_root)

    return roots


def count_sessions(path: Path) -> int:
    """Count unique OpenCode session JSON files under resolved roots."""
    if not path.exists():
        return 0
    seen: set[Path] = set()
    for root in _resolve_storage_roots(path):
        session_dir = root / "session"
        for file_path in session_dir.rglob("*.json"):
            if file_path.is_file():
                seen.add(file_path)
    return len(seen)


def find_session_path(session_id: str, traces_dir: Path | None = None) -> Path | None:
    """Find an OpenCode session JSON file by file stem or ``id`` field."""
    for root in _resolve_storage_roots(traces_dir):
        session_dir = root / "session"
        if not session_dir.exists():
            continue
        for path in session_dir.rglob("*.json"):
            if path.stem == session_id:
                return path
            data = _parse_json_file(path)
            if data and data.get("id") == session_id:
                return path
    return None


def _find_storage_root_for_session(session_path: Path, traces_dir: Path | None = None) -> Path | None:
    """Find the storage root that owns a given OpenCode session file."""
    for root in _resolve_storage_roots(traces_dir):
        try:
            session_path.relative_to(root / "session")
            return root
        except ValueError:
            continue
    return None


def read_session(session_path: Path, session_id: str | None = None) -> ViewerSession | None:
    """Read one OpenCode session and its related message/part files."""
    payload = _parse_json_file(session_path)
    if not payload:
        return None

    resolved_id = str(payload.get("id") or session_id or session_path.stem)
    cwd = payload.get("directory")
    version = payload.get("version")
    total_input = 0
    total_output = 0
    messages: list[ViewerMessage] = []

    storage_root = _find_storage_root_for_session(session_path)
    if storage_root is None:
        if session_path.parent.name == "session":
            storage_root = session_path.parent.parent
        else:
            return ViewerSession(session_id=resolved_id, cwd=cwd, messages=messages, meta={"version": version})

    messages_dir = storage_root / "message" / resolved_id
    if not messages_dir.exists():
        return ViewerSession(session_id=resolved_id, cwd=cwd, messages=messages, meta={"version": version})

    message_entries: list[tuple[int, dict[str, Any]]] = []
    for msg_path in messages_dir.glob("*.json"):
        msg = _parse_json_file(msg_path)
        if not msg:
            continue
        created_ms = int(((msg.get("time") or {}).get("created")) or 0)
        message_entries.append((created_ms, msg))
    message_entries.sort(key=lambda item: item[0])

    for _, msg in message_entries:
        role = str(msg.get("role") or "assistant")
        time_info = msg.get("time") or {}
        timestamp = _parse_timestamp_ms(time_info.get("created"))

        tokens = msg.get("tokens") or {}
        total_input += int(tokens.get("input") or 0)
        total_output += int(tokens.get("output") or 0)
        total_output += int(tokens.get("reasoning") or 0)

        text_parts: list[str] = []
        parts_dir = storage_root / "part" / str(msg.get("id") or "")
        if parts_dir.exists():
            for part_path in parts_dir.glob("*.json"):
                part = _parse_json_file(part_path)
                if not part:
                    continue
                part_type = part.get("type")
                if part_type == "text":
                    text = part.get("text")
                    if isinstance(text, str) and text.strip():
                        text_parts.append(text.strip())
                elif part_type == "tool":
                    tool_name = str(part.get("tool") or "tool")
                    state = part.get("state") or {}
                    messages.append(
                        ViewerMessage(
                            role="tool",
                            tool_name=tool_name,
                            tool_input=state.get("input"),
                            tool_output=state.get("output"),
                            timestamp=_parse_timestamp_ms((state.get("time") or {}).get("start")),
                        )
                    )

        content = "\n".join(text_parts).strip()
        if content:
            messages.append(
                ViewerMessage(
                    role=role,
                    content=content,
                    timestamp=timestamp,
                )
            )

    return ViewerSession(
        session_id=resolved_id,
        cwd=cwd,
        messages=messages,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        meta={"version": version},
    )


def iter_sessions(
    traces_dir: Path | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[SessionRecord]:
    """Enumerate OpenCode sessions and return summarized index records."""
    records: list[SessionRecord] = []
    for root in _resolve_storage_roots(traces_dir):
        session_dir = root / "session"
        if not session_dir.exists():
            continue
        for session_path in session_dir.rglob("*.json"):
            payload = _parse_json_file(session_path)
            if not payload:
                continue
            run_id = str(payload.get("id") or session_path.stem)
            start_ms = payload.get("createdAt") or payload.get("created_at")
            start_dt = parse_timestamp(start_ms)
            if not in_window(start_dt, start, end):
                continue

            session = read_session(session_path, session_id=run_id)
            if session is None:
                continue
            summaries: list[str] = []
            for msg in session.messages:
                if msg.role in {"user", "assistant"} and (msg.content or "").strip():
                    summaries.append((msg.content or "").strip()[:140])
                if len(summaries) >= 5:
                    break

            message_count = len([m for m in session.messages if m.role in {"user", "assistant"}])
            tool_calls = len([m for m in session.messages if m.role == "tool"])
            records.append(
                SessionRecord(
                    run_id=run_id,
                    agent_type="opencode",
                    session_path=str(session_path),
                    start_time=start_dt.isoformat() if start_dt else None,
                    repo_name=str(payload.get("directory") or "") or None,
                    message_count=message_count,
                    tool_call_count=tool_calls,
                    total_tokens=session.total_input_tokens + session.total_output_tokens,
                    summaries=summaries,
                )
            )
    return records
