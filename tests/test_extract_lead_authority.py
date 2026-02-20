"""test extract lead authority."""

from __future__ import annotations

from acreta.config.settings import reload_config
from acreta.extract import pipeline
from acreta.sessions import catalog


def _setup_env(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ACRETA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ACRETA_MEMORY_DIR", str(tmp_path / "memory"))
    monkeypatch.setenv("ACRETA_INDEX_DIR", str(tmp_path / "index"))
    monkeypatch.setenv("ACRETA_SESSIONS_DB", str(tmp_path / "index" / "sessions.sqlite3"))
    monkeypatch.setenv("ACRETA_MEMORY_SCOPE", "global_only")
    reload_config()
    catalog.init_sessions_db()


def _index_session(tmp_path, run_id: str) -> None:
    session_path = tmp_path / "sessions" / f"{run_id}.jsonl"
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_text('{"role":"assistant","content":"ok"}\n', encoding="utf-8")
    catalog.index_session_for_fts(
        run_id=run_id,
        agent_type="cursor",
        repo_name="acreta",
        content="session content",
        session_path=str(session_path),
    )


def test_extract_session_memories_returns_candidates(tmp_path, monkeypatch) -> None:
    _setup_env(tmp_path, monkeypatch)
    run_id = "run-extract-1"
    _index_session(tmp_path, run_id)

    monkeypatch.setattr(
        pipeline,
        "extract_memories_from_session_file",
        lambda *_args, **_kwargs: [
            {
                "primitive": "learning",
                "title": "Queue retries",
                "body": "Use bounded retries with heartbeat and dead-letter routing.",
                "confidence": 0.9,
            },
            {
                "primitive": "learning",
                "title": "Cursor checks",
                "body": "Validate cursor session metadata before enqueueing jobs.",
                "confidence": 0.8,
            },
        ],
    )

    result = pipeline.extract_session_memories(run_id, no_llm=False)

    assert result["status"] == "completed"
    assert len(result["candidates"]) == 2
    assert "agent:cursor" in result["tags"]
    assert "repo:acreta" in result["tags"]


def test_extract_session_memories_no_llm_skips_extraction(tmp_path, monkeypatch) -> None:
    _setup_env(tmp_path, monkeypatch)
    run_id = "run-extract-2"
    _index_session(tmp_path, run_id)

    monkeypatch.setattr(
        pipeline,
        "extract_memories_from_session_file",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not be called when no_llm=True")),
    )

    result = pipeline.extract_session_memories(run_id, no_llm=True)

    assert result["status"] == "completed"
    assert result["candidates"] == []
