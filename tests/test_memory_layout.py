"""Tests for canonical memory layout creation and root reset behavior."""

from __future__ import annotations

from acreta.memory.layout import build_layout, ensure_layout, reset_data_root


def test_ensure_layout_creates_canonical_folders(tmp_path) -> None:
    layout = build_layout(tmp_path)
    ensure_layout(layout)

    assert (layout.memory_dir / "decisions").exists()
    assert (layout.memory_dir / "learnings").exists()
    assert (layout.memory_dir / "conventions").exists()
    assert (layout.memory_dir / "context").exists()
    assert (layout.meta_dir / "state").exists()
    assert (layout.meta_dir / "evidence").exists()
    assert (layout.meta_dir / "traces" / "sessions").exists()
    assert layout.index_dir.exists()


def test_reset_data_root_recreates_clean_layout(tmp_path) -> None:
    layout = build_layout(tmp_path)
    ensure_layout(layout)

    learning_path = layout.memory_dir / "learnings" / "example--l20260220abcd.md"
    learning_path.write_text("seed", encoding="utf-8")
    stale_sidecar = layout.meta_dir / "state" / "old.json"
    stale_sidecar.write_text("{}", encoding="utf-8")
    stale_index = layout.index_dir / "fts.sqlite3"
    stale_index.write_text("", encoding="utf-8")

    result = reset_data_root(layout)

    removed = set(result["removed"])
    assert str(layout.memory_dir) in removed
    assert str(layout.meta_dir) in removed
    assert str(layout.index_dir) in removed
    assert (layout.memory_dir / "learnings").exists()
    assert not learning_path.exists()
    assert not stale_sidecar.exists()
    assert not stale_index.exists()
