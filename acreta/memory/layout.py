"""Filesystem layout helpers for Acreta Memory V2 folders and reset."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MemoryLayout:
    """Resolved canonical paths for the Acreta data tree."""

    data_dir: Path
    memory_dir: Path
    meta_dir: Path
    index_dir: Path
    fts_db_path: Path
    graph_db_path: Path
    vectors_dir: Path


def build_layout(data_dir: Path) -> MemoryLayout:
    """Build concrete canonical paths rooted at ``data_dir``."""
    data_dir = data_dir.expanduser()
    index_dir = data_dir / "index"
    return MemoryLayout(
        data_dir=data_dir,
        memory_dir=data_dir / "memory",
        meta_dir=data_dir / "meta",
        index_dir=index_dir,
        fts_db_path=index_dir / "fts.sqlite3",
        graph_db_path=index_dir / "graph.sqlite3",
        vectors_dir=index_dir / "vectors.lance",
    )


def ensure_layout(layout: MemoryLayout) -> None:
    """Create required Memory V2 folders when missing."""
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
    """Remove a file or directory tree when it exists."""
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
        return
    path.unlink(missing_ok=True)


def reset_data_root(layout: MemoryLayout) -> dict[str, list[str]]:
    """Delete memory/meta/index trees for one root, then recreate canonical folders."""
    removed: list[str] = []
    for path in (layout.memory_dir, layout.meta_dir, layout.index_dir):
        if path.exists():
            _remove_tree(path)
            removed.append(str(path))
    ensure_layout(layout)
    return {"removed": removed}


if __name__ == "__main__":
    """Run a real-path smoke test for layout creation and full root reset."""
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as tmp_dir:
        layout = build_layout(Path(tmp_dir))
        ensure_layout(layout)
        (layout.memory_dir / "learnings" / "seed.md").write_text("seed", encoding="utf-8")
        result = reset_data_root(layout)
        assert str(layout.memory_dir) in result["removed"]
        assert (layout.memory_dir / "learnings").exists()
