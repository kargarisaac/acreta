"""Filesystem paths and repository operations for Acreta memory."""

from __future__ import annotations

import re
import secrets
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from acreta.memory.meta_store import MetaStore
from acreta.memory.memory_record import Learning, LearningType, LifecycleState, MemoryType, PrimitiveType, memory_folder


_MEMORY_GLOB = tuple(memory_folder(item) for item in MemoryType)


@dataclass(frozen=True)
class MemoryPaths:
    """Resolved canonical paths for one Acreta data root."""

    data_dir: Path
    memory_dir: Path
    meta_dir: Path
    workspace_dir: Path
    index_dir: Path
    fts_db_path: Path
    graph_db_path: Path
    vectors_dir: Path


def build_memory_paths(data_dir: Path) -> MemoryPaths:
    """Build canonical path set rooted at ``data_dir``."""
    data_dir = data_dir.expanduser()
    index_dir = data_dir / "index"
    return MemoryPaths(
        data_dir=data_dir,
        memory_dir=data_dir / "memory",
        meta_dir=data_dir / "meta",
        workspace_dir=data_dir / "workspace",
        index_dir=index_dir,
        fts_db_path=index_dir / "fts.sqlite3",
        graph_db_path=index_dir / "graph.sqlite3",
        vectors_dir=index_dir / "vectors.lance",
    )


def ensure_memory_paths(paths: MemoryPaths) -> None:
    """Create required canonical memory folders when missing."""
    memory_paths = tuple(paths.memory_dir / memory_folder(item) for item in MemoryType)
    for path in (
        *memory_paths,
        paths.meta_dir / "evidence",
        paths.meta_dir / "state",
        paths.meta_dir / "traces" / "sessions",
        paths.workspace_dir,
        paths.index_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)


def reset_memory_root(paths: MemoryPaths) -> dict[str, list[str]]:
    """Delete memory/meta/index/workspace trees for a root and recreate canonical layout."""
    removed: list[str] = []
    for path in (paths.memory_dir, paths.meta_dir, paths.workspace_dir, paths.index_dir):
        if path.exists():
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)
            removed.append(str(path))
    ensure_memory_paths(paths)
    return {"removed": removed}


class MemoryRepository:
    """Read/write API for memory markdown files and sidecar metadata."""

    def __init__(self, memory_dir: Path, meta_dir: Path | None = None) -> None:
        """Create a store rooted at ``memory_dir`` with optional ``meta_dir``."""
        self.memory_dir = memory_dir
        self.meta_dir = meta_dir or (memory_dir.parent / "meta")
        self.meta_store = MetaStore(self.meta_dir)
        for folder in _MEMORY_GLOB:
            (self.memory_dir / folder).mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _primitive_prefix(primitive: PrimitiveType) -> str:
        """Return deterministic ID prefix for each primitive type."""
        return {
            PrimitiveType.decision: "d",
            PrimitiveType.learning: "l",
            PrimitiveType.summary: "s",
        }[primitive]

    def _ensure_unique_id(self, learning: Learning) -> None:
        """Rewrite ``learning.id`` if the current one already exists on disk."""
        if not self.find_path(learning.id):
            return
        original_id = learning.id
        while self.find_path(learning.id):
            learning.id = self.generate_id(learning.primitive)
        if learning.id != original_id:
            learning.updated = datetime.now(timezone.utc)

    def generate_id(self, primitive: PrimitiveType = PrimitiveType.learning) -> str:
        """Generate a compact time-based memory identifier."""
        date_part = datetime.now(timezone.utc).strftime("%Y%m%d")
        hex_part = secrets.token_hex(2)
        return f"{self._primitive_prefix(primitive)}{date_part}{hex_part}"

    def _path_for(self, learning: Learning) -> Path:
        """Resolve destination markdown path for a learning item."""
        folder = self.memory_dir / learning.primitive_dirname()
        folder.mkdir(parents=True, exist_ok=True)
        return folder / learning.filename()

    def write(self, learning: Learning) -> Path:
        """Create a new learning markdown file and matching sidecar metadata."""
        if not learning.id:
            learning.id = self.generate_id(learning.primitive)
        self._ensure_unique_id(learning)
        path = self._path_for(learning)
        self._atomic_write(path, learning.to_markdown())
        self.meta_store.write_from_learning(learning)
        return path

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        """Write text atomically via a temporary sibling file."""
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(content, encoding="utf-8")
        tmp_path.replace(path)

    @staticmethod
    def _id_from_filename(path: Path) -> str | None:
        """Extract a canonical memory ID from a markdown filename stem."""
        match = re.match(r"^.+--([a-z]\d{8}[0-9a-f]{4})$", path.stem)
        if match:
            return match.group(1)
        return None

    def find_path(self, learning_id: str) -> Path | None:
        """Find on-disk markdown path for a memory ID."""
        for path in self.iter_files():
            fid = self._id_from_filename(path)
            if fid == learning_id or path.stem == learning_id:
                return path
            try:
                if f"id: {learning_id}" in path.read_text(encoding="utf-8").split("---", 2)[1]:
                    return path
            except (OSError, IndexError):
                continue
        return None

    def read(self, learning_id: str) -> Learning | None:
        """Load one learning by ID, including sidecar-enriched fields."""
        path = self.find_path(learning_id)
        if path is None:
            return None
        try:
            text = path.read_text(encoding="utf-8")
            learning = Learning.from_markdown(text)
        except (OSError, ValueError, KeyError):
            return None
        return self.meta_store.load_into_learning(learning)

    def list_all(
        self,
        project: str | None = None,
        learning_type: LearningType | None = None,
        lifecycle_state: LifecycleState | None = None,
        min_confidence: float | None = None,
    ) -> list[Learning]:
        """List learnings with optional project/type/state/confidence filters."""
        results: list[Learning] = []
        for path in self.iter_files():
            try:
                learning = Learning.from_markdown(path.read_text(encoding="utf-8"))
            except (ValueError, KeyError, OSError):
                continue
            learning = self.meta_store.load_into_learning(learning)
            if project and project not in learning.projects:
                continue
            if learning_type and learning.learning_type != learning_type:
                continue
            if lifecycle_state and learning.lifecycle_state != lifecycle_state:
                continue
            if min_confidence is not None and learning.confidence < min_confidence:
                continue
            results.append(learning)
        return results

    def update(self, learning: Learning) -> Path:
        """Update a learning in place and keep metadata sidecars synchronized."""
        old_path = self.find_path(learning.id)
        learning.updated = datetime.now(timezone.utc)
        new_path = self._path_for(learning)
        self._atomic_write(new_path, learning.to_markdown())
        self.meta_store.write_from_learning(learning)
        if old_path and old_path != new_path:
            old_path.unlink(missing_ok=True)
        return new_path

    def remove(self, learning_id: str) -> bool:
        """Delete a learning and its sidecar metadata by ID."""
        path = self.find_path(learning_id)
        if path is None:
            return False
        path.unlink(missing_ok=True)
        self.meta_store.delete(learning_id)
        return True

    def iter_files(self) -> Iterator[Path]:
        """Iterate all memory markdown files in canonical primitive folders."""
        if not self.memory_dir.exists():
            return iter(())
        paths: list[Path] = []
        for folder in _MEMORY_GLOB:
            base = self.memory_dir / folder
            if base.exists():
                paths.extend(sorted(base.glob("*.md")))
        return iter(paths)

    def normalize_all(self, dry_run: bool = False) -> list[Path]:
        """Normalize markdown serialization for every learning file."""
        updated: list[Path] = []
        for path in self.iter_files():
            try:
                original = path.read_text(encoding="utf-8")
                learning = Learning.from_markdown(original)
            except (OSError, ValueError, KeyError):
                continue
            normalized = learning.to_markdown()
            if original.endswith("\n") and not normalized.endswith("\n"):
                normalized += "\n"
            if original == normalized:
                continue
            updated.append(path)
            if not dry_run:
                path.write_text(normalized, encoding="utf-8")
        return updated


if __name__ == "__main__":
    """Run a real-path smoke test for memory write/read/update/remove flow."""
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        store = MemoryRepository(root / "memory", root / "meta")
        learning = Learning(
            id=store.generate_id(PrimitiveType.learning),
            title="Store smoke test",
            body="Verify MemoryRepository round-trip behavior.",
            primitive=PrimitiveType.learning,
        )
        created_path = store.write(learning)
        assert created_path.exists()

        loaded = store.read(learning.id)
        assert loaded is not None
        assert loaded.title == "Store smoke test"

        loaded.body = "Updated body"
        store.update(loaded)
        updated = store.read(learning.id)
        assert updated is not None and updated.body == "Updated body"

        assert store.remove(learning.id) is True
        assert store.read(learning.id) is None
