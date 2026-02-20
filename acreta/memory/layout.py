"""Filesystem layout helpers for Acreta memory schema and legacy cleanup."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 2


@dataclass(frozen=True)
class MemoryLayout:
    """Resolved paths for the Acreta memory, meta, and index tree."""

    data_dir: Path
    memory_dir: Path
    meta_dir: Path
    index_dir: Path
    fts_db_path: Path
    graph_db_path: Path
    vectors_dir: Path
    schema_marker_path: Path


def build_layout(data_dir: Path) -> MemoryLayout:
    """Build a concrete path layout rooted at ``data_dir``."""
    data_dir = data_dir.expanduser()
    index_dir = data_dir / "index"
    meta_dir = data_dir / "meta"
    return MemoryLayout(
        data_dir=data_dir,
        memory_dir=data_dir / "memory",
        meta_dir=meta_dir,
        index_dir=index_dir,
        fts_db_path=index_dir / "fts.sqlite3",
        graph_db_path=index_dir / "graph.sqlite3",
        vectors_dir=index_dir / "vectors.lance",
        schema_marker_path=meta_dir / "state" / "schema-version.json",
    )


def ensure_layout(layout: MemoryLayout) -> None:
    """Create required v2 memory folders if they do not exist."""
    for path in (
        layout.memory_dir / "decisions",
        layout.memory_dir / "learnings",
        layout.memory_dir / "conventions",
        layout.memory_dir / "context",
        layout.meta_dir / "evidence",
        layout.meta_dir / "state",
        layout.meta_dir / "traces" / "sessions",
        layout.index_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)


def _remove_tree(path: Path) -> None:
    """Remove a file or directory tree if it exists."""
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)


def reset_legacy_artifacts(layout: MemoryLayout) -> dict[str, list[str]]:
    """Delete known legacy v1 artifacts that conflict with v2 layout."""
    removed: list[str] = []

    # Legacy learning layout used monthly subfolders under memory/learnings/YYYY-MM.
    # Keep canonical memory/learnings itself because it is valid in Memory V2.
    legacy_learnings_root = layout.memory_dir / "learnings"
    if legacy_learnings_root.exists() and legacy_learnings_root.is_dir():
        month_dir_re = re.compile(r"^\d{4}-\d{2}$")
        for child in legacy_learnings_root.iterdir():
            if child.is_dir() and month_dir_re.match(child.name):
                _remove_tree(child)
                removed.append(str(child))
            elif child.is_file() and child.suffix == ".md" and child.name.startswith("lrn-"):
                _remove_tree(child)
                removed.append(str(child))

    for path in (
        layout.memory_dir / "graph",
        layout.memory_dir / "traces",
        layout.index_dir / "memory.sqlite3",
        layout.index_dir / "memory.sqlite3-shm",
        layout.index_dir / "memory.sqlite3-wal",
        layout.index_dir / "vector-meta.json",
        layout.index_dir / "embedding-cache",
        layout.vectors_dir,
    ):
        if path.exists():
            _remove_tree(path)
            removed.append(str(path))
    return {"removed": removed}


def ensure_schema(layout: MemoryLayout, *, hard_reset_legacy: bool) -> dict[str, object]:
    """Ensure schema marker exists and optionally run one-time legacy cleanup."""
    ensure_layout(layout)
    marker_path = layout.schema_marker_path
    if marker_path.exists():
        try:
            payload = json.loads(marker_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        if int(payload.get("schema_version") or 0) >= SCHEMA_VERSION:
            return {"schema_version": SCHEMA_VERSION, "reset_applied": bool(payload.get("reset_applied"))}

    reset_payload: dict[str, object] = {"removed": []}
    if hard_reset_legacy:
        reset_payload = reset_legacy_artifacts(layout)

    marker = {
        "schema_version": SCHEMA_VERSION,
        "reset_applied": bool(hard_reset_legacy),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "removed": reset_payload.get("removed") or [],
    }
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.write_text(json.dumps(marker, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    ensure_layout(layout)
    return marker


if __name__ == "__main__":
    """Run a real-path smoke test for layout creation and schema marker write."""
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as tmp_dir:
        layout = build_layout(Path(tmp_dir))
        ensure_layout(layout)
        marker = ensure_schema(layout, hard_reset_legacy=False)
        assert (layout.memory_dir / "learnings").exists()
        assert layout.schema_marker_path.exists()
        assert marker["schema_version"] == SCHEMA_VERSION
