"""Maintenance operations for postprocess, dedupe, decay, and consolidation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from acreta.config.settings import get_config
from acreta.memory.memory_record import Learning, LifecycleState
from acreta.memory.memory_repo import MemoryRepository


@dataclass(frozen=True)
class LearningRecord:
    """Learning with its source markdown path for maintenance operations."""

    learning: Learning
    path: Path


def _rank_key(learning: Learning) -> tuple[float, int, datetime, str]:
    """Return deterministic ranking key for selecting canonical duplicates."""
    return (
        learning.confidence,
        learning.useful_count,
        learning.updated,
        learning.id,
    )


def _learning_path(store: MemoryRepository, learning: Learning) -> Path:
    """Return canonical markdown path for a learning in this store."""
    return store.memory_dir / learning.primitive_dirname() / learning.filename()


def postprocess_learnings(
    store: MemoryRepository,
    learning_ids: list[str],
    session_id: str,
    session_doc: dict | None = None,
) -> int:
    """Enrich newly written learnings with session/project/agent defaults."""
    project_name = (session_doc or {}).get("repo_name") or ""
    project_path = (session_doc or {}).get("repo_path") or ""
    agent_type = (session_doc or {}).get("agent_type") or ""

    updated = 0
    for learning_id in learning_ids:
        learning = store.read(learning_id)
        if not learning:
            continue
        changed = False
        if not learning.source_sessions and session_id:
            learning.source_sessions = [session_id]
            changed = True
        if not learning.projects:
            projects = [value for value in (project_name, project_path) if value]
            if projects:
                learning.projects = projects
                changed = True
        if not learning.agent_types and agent_type:
            learning.agent_types = [agent_type]
            changed = True
        if not learning.evidence:
            if learning.confidence > 0.6:
                learning.confidence = 0.6
                changed = True
            if learning.lifecycle_state != LifecycleState.candidate:
                learning.lifecycle_state = LifecycleState.candidate
                changed = True
        new_hash = learning.compute_content_hash()
        if learning.content_hash != new_hash:
            learning.content_hash = new_hash
            changed = True
        if changed:
            store.update(learning)
            updated += 1
    return updated


def cleanup_learnings(
    memory_dir: Path,
    report_path: Path | None = None,
    dry_run: bool = False,
) -> dict[str, object]:
    """Remove hash duplicates, re-ID collisions, and optionally emit a report."""
    store = MemoryRepository(memory_dir)
    records: list[LearningRecord] = []
    for path in store.iter_files():
        try:
            text = path.read_text(encoding="utf-8")
            learning = Learning.from_markdown(text)
        except (OSError, ValueError, KeyError):
            continue
        learning.ensure_content_hash()
        records.append(LearningRecord(learning=learning, path=path))

    by_hash: dict[str, list[LearningRecord]] = {}
    for record in records:
        key = record.learning.content_hash or ""
        by_hash.setdefault(key, []).append(record)

    duplicate_paths: set[Path] = set()
    for key, group in by_hash.items():
        if not key:
            continue
        canonical = max(group, key=lambda rec: _rank_key(rec.learning))
        for record in group:
            if record.path != canonical.path:
                duplicate_paths.add(record.path)

    re_ided: list[dict[str, str]] = []
    kept: list[dict[str, str]] = []
    deleted: list[dict[str, str]] = []

    by_id: dict[str, list[LearningRecord]] = {}
    for record in records:
        by_id.setdefault(record.learning.id, []).append(record)
    for group in by_id.values():
        survivors = [record for record in group if record.path not in duplicate_paths]
        if len(survivors) < 2:
            continue
        canonical = max(survivors, key=lambda rec: _rank_key(rec.learning))
        for record in survivors:
            if record.path == canonical.path:
                continue
            old_id = record.learning.id
            record.learning.id = store.generate_id()
            record.learning.content_hash = record.learning.compute_content_hash()
            new_path = _learning_path(store, record.learning)
            if not dry_run:
                new_path = store.write(record.learning)
                record.path.unlink(missing_ok=True)
            re_ided.append(
                {
                    "old_id": old_id,
                    "new_id": record.learning.id,
                    "old_path": str(record.path),
                    "new_path": str(new_path),
                }
            )

    for path in duplicate_paths:
        record = next((rec for rec in records if rec.path == path), None)
        if record:
            deleted.append(
                {
                    "id": record.learning.id,
                    "path": str(record.path),
                    "content_hash": record.learning.content_hash or "",
                }
            )
        if not dry_run:
            path.unlink(missing_ok=True)

    for record in records:
        if record.path in duplicate_paths:
            continue
        kept.append(
            {
                "id": record.learning.id,
                "path": str(record.path),
                "content_hash": record.learning.content_hash or "",
            }
        )

    report = {
        "summary": {
            "total_files": len(records),
            "kept": len(kept),
            "deleted": len(deleted),
            "re_ided": len(re_ided),
            "dry_run": dry_run,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "kept": kept,
        "deleted": deleted,
        "re_ided": re_ided,
    }
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def apply_decay() -> None:
    """Apply confidence decay and lifecycle transitions by staleness."""
    config = get_config()
    store = MemoryRepository(config.memory_dir)
    learnings = store.list_all()
    now = datetime.now(timezone.utc)
    for learning in learnings:
        age_days = max((now - learning.updated).days, 0)
        decay = 0.0
        if age_days > 90:
            decay = 0.15
        elif age_days > 30:
            decay = 0.05
        if learning.useful_count <= 0 and decay:
            learning.confidence = max(0.0, learning.confidence - decay)
        if learning.confidence < 0.2:
            learning.lifecycle_state = LifecycleState.archived
        elif learning.confidence < 0.4:
            learning.lifecycle_state = LifecycleState.stale
        store.update(learning)


def consolidate_learnings() -> None:
    """Merge duplicate learnings by content hash into one primary record."""
    config = get_config()
    store = MemoryRepository(config.memory_dir)
    learnings = store.list_all()
    by_hash: dict[str, list[Learning]] = {}
    for learning in learnings:
        by_hash.setdefault(learning.ensure_content_hash(), []).append(learning)

    for group in by_hash.values():
        if len(group) < 2:
            continue
        primary = max(group, key=_rank_key)
        for dup in group:
            if dup.id == primary.id or dup.version_of == primary.id:
                continue
            primary.occurrences += dup.occurrences
            primary.source_sessions = list(set(primary.source_sessions + dup.source_sessions))
            primary.tags = list(set(primary.tags + dup.tags))
            primary.projects = list(set(primary.projects + dup.projects))
            primary.agent_types = list(set(primary.agent_types + dup.agent_types))
            primary.evidence.extend(dup.evidence)
            if dup.id not in primary.supersedes:
                primary.supersedes.append(dup.id)
            dup.lifecycle_state = LifecycleState.archived
            dup.version_of = primary.id
            store.update(dup)
        store.update(primary)


if __name__ == "__main__":
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        store = MemoryRepository(root)
        first = Learning(id=store.generate_id(), title="Queue lifecycle", body="Keep queue states consistent.")
        second = Learning(id=store.generate_id(), title="Queue lifecycle", body="Keep queue states consistent.")
        store.write(first)
        store.write(second)
        report = cleanup_learnings(root, dry_run=True)
        assert report["summary"]["total_files"] == 2
        assert report["summary"]["deleted"] == 1
