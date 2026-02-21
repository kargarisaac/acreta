"""Filesystem paths and layout helpers for Acreta memory.

MemoryRepository has been removed. The agent reads/writes memory files directly
via SDK tools. This module keeps standalone path helpers used by settings and CLI.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from acreta.memory.memory_record import MemoryType, memory_folder


@dataclass(frozen=True)
class MemoryPaths:
    """Resolved canonical paths for one Acreta data root."""

    data_dir: Path
    memory_dir: Path
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
        paths.workspace_dir,
        paths.index_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)


def reset_memory_root(paths: MemoryPaths) -> dict[str, list[str]]:
    """Delete memory/index/workspace trees for a root and recreate canonical layout."""
    removed: list[str] = []
    for path in (paths.memory_dir, paths.workspace_dir, paths.index_dir):
        if path.exists():
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)
            removed.append(str(path))
    ensure_memory_paths(paths)
    return {"removed": removed}


if __name__ == "__main__":
    """Run a real-path smoke test for memory path helpers."""
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        paths = build_memory_paths(root)

        # Verify path structure
        assert paths.data_dir == root
        assert paths.memory_dir == root / "memory"
        assert paths.workspace_dir == root / "workspace"
        assert paths.index_dir == root / "index"

        # Ensure creates folders
        ensure_memory_paths(paths)
        assert (paths.memory_dir / "decisions").exists()
        assert (paths.memory_dir / "learnings").exists()
        assert (paths.memory_dir / "summaries").exists()
        assert paths.workspace_dir.exists()
        assert paths.index_dir.exists()

        # Reset removes and recreates
        (paths.memory_dir / "learnings" / "test.md").write_text(
            "test", encoding="utf-8"
        )
        result = reset_memory_root(paths)
        assert str(paths.memory_dir) in result["removed"]
        assert (paths.memory_dir / "learnings").exists()
        assert not (paths.memory_dir / "learnings" / "test.md").exists()
