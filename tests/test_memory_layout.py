"""test memory layout."""

from __future__ import annotations

import json

from acreta.memory.layout import build_layout, ensure_layout, ensure_schema, reset_legacy_artifacts


def test_reset_legacy_artifacts_keeps_canonical_learning_folder(tmp_path) -> None:
    layout = build_layout(tmp_path)
    ensure_layout(layout)

    legacy_month = layout.memory_dir / "learnings" / "2026-01"
    legacy_month.mkdir(parents=True)
    (legacy_month / "lrn-20260101-abcd.md").write_text("legacy", encoding="utf-8")

    legacy_root_file = layout.memory_dir / "learnings" / "lrn-20260217-abcd.md"
    legacy_root_file.write_text("legacy-root", encoding="utf-8")

    canonical_learning = layout.memory_dir / "learnings" / "modern-learning--l20260217abcd.md"
    canonical_learning.write_text("modern", encoding="utf-8")

    result = reset_legacy_artifacts(layout)

    removed = set(result["removed"])
    assert str(legacy_month) in removed
    assert str(legacy_root_file) in removed
    assert (layout.memory_dir / "learnings").exists()
    assert canonical_learning.exists()


def test_ensure_schema_writes_marker_and_preserves_layout(tmp_path) -> None:
    layout = build_layout(tmp_path)
    ensure_layout(layout)
    marker = ensure_schema(layout, hard_reset_legacy=True)

    assert marker["schema_version"] == 2
    assert marker["reset_applied"] is True
    assert (layout.memory_dir / "learnings").exists()
    assert layout.schema_marker_path.exists()

    payload = json.loads(layout.schema_marker_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 2
