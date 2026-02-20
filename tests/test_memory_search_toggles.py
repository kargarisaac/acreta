"""Search mode contract tests for files-only retrieval toggles."""

from __future__ import annotations

from dataclasses import replace

from acreta.app import cli
from acreta.memory.memory_record import Learning, PrimitiveType
from acreta.memory.memory_repo import MemoryRepository
from tests.helpers import make_config


def test_disabled_backends_never_execute(monkeypatch, tmp_path) -> None:
    config = replace(
        make_config(tmp_path),
        memory_scope="global_only",
        global_data_dir=tmp_path,
        search_enable_fts=False,
        search_enable_vectors=False,
        search_enable_graph=False,
    )
    store = MemoryRepository(tmp_path / "memory", tmp_path / "meta")
    store.write(
        Learning(
            id=store.generate_id(PrimitiveType.learning),
            title="Queue lifecycle",
            body="Keep enqueue claim heartbeat complete fail lifecycle consistent.",
            primitive=PrimitiveType.learning,
            projects=["acreta"],
            tags=["queue"],
        )
    )

    monkeypatch.setattr(cli, "get_config", lambda: config)

    hits = cli.search_memory("queue lifecycle", limit=5)
    assert len(hits) == 1
    assert hits[0].title == "Queue lifecycle"
