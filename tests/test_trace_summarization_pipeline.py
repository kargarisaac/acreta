"""test trace summarization pipeline."""

from __future__ import annotations

from pathlib import Path

import pytest

from acreta.config.settings import reload_config
from acreta.memory import summarization_pipeline as pipeline
from acreta.sessions import catalog


def _setup_env(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ACRETA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ACRETA_MEMORY_DIR", str(tmp_path / "memory"))
    monkeypatch.setenv("ACRETA_INDEX_DIR", str(tmp_path / "index"))
    monkeypatch.setenv("ACRETA_SESSIONS_DB", str(tmp_path / "index" / "sessions.sqlite3"))
    monkeypatch.setenv("ACRETA_MEMORY_SCOPE", "global_only")
    reload_config()
    catalog.init_sessions_db()


def _index_session(tmp_path, run_id: str) -> Path:
    session_path = tmp_path / "sessions" / f"{run_id}.jsonl"
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_text(
        '{"role":"user","content":"Fix queue retries and heartbeat drift."}\n'
        '{"role":"assistant","content":"Implemented bounded retries and dead-letter fallback."}\n',
        encoding="utf-8",
    )
    catalog.index_session_for_fts(
        run_id=run_id,
        agent_type="cursor",
        repo_name="acreta",
        content="queue retry and heartbeat fix",
        session_path=str(session_path),
    )
    return session_path


def test_summarize_session_trace_returns_frontmatter_fields(tmp_path, monkeypatch) -> None:
    _setup_env(tmp_path, monkeypatch)
    run_id = "run-summary-1"
    session_path = _index_session(tmp_path, run_id)

    monkeypatch.setattr(
        pipeline,
        "_summarize_trace_with_rlm",
        lambda *_args, **_kwargs: {
            "title": "Queue stability summary",
            "description": "Session addressed duplicate queue claims.",
            "summary": "The run identified a race condition and applied atomic claim checks with retry policy updates.",
            "date": "2026-02-20",
            "time": "08:10:00",
            "coding_agent": "cursor",
            "raw_trace_path": str(session_path),
            "run_id": run_id,
            "repo_name": "acreta",
        },
    )
    result = pipeline.summarize_session_trace(run_id)

    assert result["status"] == "completed"
    summary = result["summary"]
    assert summary["title"]
    assert summary["description"]
    assert summary["date"]
    assert summary["time"]
    assert summary["coding_agent"] == "cursor"
    assert summary["raw_trace_path"] == str(session_path)
    assert len(summary["summary"].split()) <= 300


def test_summarize_trace_from_session_file_raises_on_missing_file(tmp_path) -> None:
    missing_path = tmp_path / "missing.jsonl"
    with pytest.raises(FileNotFoundError):
        pipeline.summarize_trace_from_session_file(missing_path, metadata={}, metrics={})


def test_summarization_pipeline_module_is_memory_boundary() -> None:
    source = Path(pipeline.__file__).read_text(encoding="utf-8")
    assert "dspy.RLM" in source
    assert "FileStore" not in source
    assert "search_memory" not in source
    assert "AcretaAgent" not in source
