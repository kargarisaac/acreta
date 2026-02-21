"""Cursor adapter for reading session traces from Cursor state SQLite DBs."""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from acreta.adapters.base import SessionRecord, ViewerMessage, ViewerSession
from acreta.adapters.common import in_window, parse_timestamp


def default_path() -> Path | None:
    """Return platform-specific default Cursor storage path."""
    if sys.platform == "darwin":
        return Path(
            "~/Library/Application Support/Cursor/User/globalStorage/"
        ).expanduser()
    if sys.platform.startswith("linux"):
        return Path("~/.config/Cursor/User/globalStorage/").expanduser()
    return Path("~/Library/Application Support/Cursor/User/globalStorage/").expanduser()


def _resolve_db_paths(root: Path) -> list[Path]:
    """Resolve candidate ``state.vscdb`` files from a root path."""
    if root.is_file():
        return [root]
    if (root / "state.vscdb").exists():
        return [root / "state.vscdb"]
    return [p for p in root.glob("*/state.vscdb") if p.is_file()]


def _count_cursor_db(db_path: Path) -> int:
    """Count Cursor conversation keys in one SQLite database file."""
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA query_only=ON")
        row = conn.execute(
            "SELECT COUNT(1) FROM cursorDiskKV WHERE key LIKE 'composerData:%' OR key LIKE 'bubbleId:%'"
        ).fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return 0
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def count_sessions(path: Path) -> int:
    """Count Cursor sessions from one file or a storage directory tree."""
    if not path.exists():
        return 0
    if path.is_file():
        return _count_cursor_db(path)
    db_path = path / "state.vscdb"
    if db_path.exists():
        return _count_cursor_db(db_path)
    return sum(_count_cursor_db(db) for db in path.glob("*/state.vscdb"))


def _parse_json_value(raw: str) -> Any | None:
    """Parse possibly double-encoded JSON values stored in Cursor DB rows."""
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _extract_text(value: Any) -> str:
    """Extract readable text from nested Cursor message payload values."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("text", "content", "message", "value"):
            if key in value:
                return _extract_text(value[key])
    if isinstance(value, list):
        parts = [p for p in (_extract_text(v) for v in value) if p]
        return "\n".join(parts)
    return str(value)


def _normalize_role(value: Any) -> str:
    """Normalize Cursor role aliases into user/assistant/tool."""
    role = str(value or "").lower()
    if role in {"user", "human", "human_user"}:
        return "user"
    if role in {"assistant", "ai", "bot", "model"}:
        return "assistant"
    if role in {"tool", "function"}:
        return "tool"
    return "assistant"


def _extract_message_records(payload: Any) -> list[dict]:
    """Return a flat list of message-like records from Cursor payload data."""
    if not isinstance(payload, dict):
        return []
    for key in ("chunks", "messages", "conversation", "items"):
        records = payload.get(key)
        if isinstance(records, list):
            return [r for r in records if isinstance(r, dict)]
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("chunks", "messages", "conversation", "items"):
            records = data.get(key)
            if isinstance(records, list):
                return [r for r in records if isinstance(r, dict)]
    return []


def _parse_messages(payload: Any) -> list[tuple[str, str, datetime | None]]:
    """Parse normalized (role, text, timestamp) tuples from Cursor payloads."""
    records = _extract_message_records(payload)
    messages: list[tuple[str, str, datetime | None]] = []
    for record in records:
        role = _normalize_role(
            record.get("role") or record.get("author") or record.get("sender")
        )
        if "type" in record and isinstance(record.get("type"), int):
            role = "user" if record.get("type") == 1 else "assistant"
        text = _extract_text(
            record.get("text")
            or record.get("content")
            or record.get("message")
            or record
        )
        if not text.strip():
            continue
        ts = parse_timestamp(
            record.get("timestamp")
            or record.get("createdAt")
            or record.get("created_at")
            or record.get("time")
        )
        messages.append((role, text, ts))
    return messages


def _extract_session_id(key: str) -> str | None:
    """Extract session ID from Cursor key prefixes."""
    if "composerData:" in key:
        return key.split("composerData:", 1)[1]
    if "bubbleId:" in key:
        return key.split("bubbleId:", 1)[1]
    return None


def _cursor_rows(db_path: Path) -> list[tuple[str, str]]:
    """Load raw Cursor key/value rows relevant to composer sessions."""
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT key, value FROM cursorDiskKV WHERE key LIKE 'composerData:%' OR key LIKE 'bubbleId:%'"
        ).fetchall()
        return [(str(row[0]), str(row[1])) for row in rows]
    except sqlite3.Error:
        return []
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def find_session_path(session_id: str, traces_dir: Path | None = None) -> Path | None:
    """Find which Cursor DB file contains a session key."""
    root = traces_dir or default_path()
    if root is None or not root.exists():
        return None
    target = session_id.strip()
    if not target:
        return None
    for db_path in _resolve_db_paths(root):
        conn: sqlite3.Connection | None = None
        try:
            conn = sqlite3.connect(db_path)
            for prefix in ("composerData:", "bubbleId:"):
                row = conn.execute(
                    "SELECT key FROM cursorDiskKV WHERE key = ? LIMIT 1",
                    (f"{prefix}{target}",),
                ).fetchone()
                if row:
                    return db_path
            row = conn.execute(
                "SELECT key FROM cursorDiskKV WHERE key LIKE ? LIMIT 1",
                (f"%{target}%",),
            ).fetchone()
            if row and ("composerData:" in row[0] or "bubbleId:" in row[0]):
                return db_path
        except sqlite3.Error:
            continue
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
    return None


def read_session(
    session_path: Path, session_id: str | None = None
) -> ViewerSession | None:
    """Read one Cursor session from SQLite and normalize it for viewing."""
    db_path = session_path if session_path.is_file() else session_path / "state.vscdb"
    if not db_path.exists() or not session_id:
        return None
    conn: sqlite3.Connection | None = None
    row: tuple[str, str] | None = None
    try:
        conn = sqlite3.connect(db_path)
        for prefix in ("composerData:", "bubbleId:"):
            found = conn.execute(
                "SELECT key, value FROM cursorDiskKV WHERE key = ? LIMIT 1",
                (f"{prefix}{session_id}",),
            ).fetchone()
            if found:
                row = (str(found[0]), str(found[1]))
                break
        if row is None:
            found = conn.execute(
                "SELECT key, value FROM cursorDiskKV WHERE key LIKE ? LIMIT 1",
                (f"%{session_id}%",),
            ).fetchone()
            if found:
                row = (str(found[0]), str(found[1]))
    except sqlite3.Error:
        return None
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    if row is None:
        return None

    payload = _parse_json_value(row[1])
    if not isinstance(payload, dict):
        return None
    messages_data = _parse_messages(payload)
    messages = [
        ViewerMessage(role=role, content=text, timestamp=ts.isoformat() if ts else None)
        for role, text, ts in messages_data
    ]
    return ViewerSession(session_id=session_id, messages=messages)


def iter_sessions(
    traces_dir: Path | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    known_run_ids: set[str] | None = None,
) -> list[SessionRecord]:
    """Enumerate Cursor sessions and build compact session summaries."""
    root = traces_dir or default_path()
    if root is None or not root.exists():
        return []

    records: list[SessionRecord] = []
    for db_path in _resolve_db_paths(root):
        for key, raw_value in _cursor_rows(db_path):
            run_id = _extract_session_id(key)
            if not run_id:
                continue
            if known_run_ids and run_id in known_run_ids:
                continue
            payload = _parse_json_value(raw_value)
            if not isinstance(payload, dict):
                continue
            messages = _parse_messages(payload)
            start_candidates = [ts for _, _, ts in messages if ts]
            started_at = min(start_candidates) if start_candidates else None
            if not in_window(started_at, start, end):
                continue
            summaries: list[str] = []
            for _, text, _ in messages:
                cleaned = text.strip()
                if cleaned:
                    summaries.append(cleaned[:140])
                if len(summaries) >= 5:
                    break
            message_count = len(
                [1 for role, _, _ in messages if role in {"user", "assistant"}]
            )
            tool_calls = len([1 for role, _, _ in messages if role == "tool"])
            records.append(
                SessionRecord(
                    run_id=run_id,
                    agent_type="cursor",
                    session_path=str(db_path),
                    start_time=started_at.isoformat() if started_at else None,
                    message_count=message_count,
                    tool_call_count=tool_calls,
                    summaries=summaries,
                )
            )
    return records
