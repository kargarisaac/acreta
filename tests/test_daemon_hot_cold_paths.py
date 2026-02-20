"""test daemon hot cold paths."""

from __future__ import annotations

from acreta.app import daemon
from acreta.app.arg_utils import parse_agent_filter, parse_csv, parse_duration_to_seconds
from acreta.config.settings import reload_config
from acreta.memory import extract_pipeline as pipeline
from acreta.sessions import catalog


def _setup(tmp_path, monkeypatch, *, enable_vectors: bool = False) -> None:
    monkeypatch.setenv("ACRETA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ACRETA_MEMORY_DIR", str(tmp_path / "memory"))
    monkeypatch.setenv("ACRETA_INDEX_DIR", str(tmp_path / "index"))
    monkeypatch.setenv("ACRETA_SESSIONS_DB", str(tmp_path / "index" / "sessions.sqlite3"))
    monkeypatch.setenv("ACRETA_SEARCH_ENABLE_GRAPH", "1")
    monkeypatch.setenv("ACRETA_SEARCH_ENABLE_VECTORS", "1" if enable_vectors else "0")
    reload_config()
    catalog.init_sessions_db()


def test_sync_hot_path_does_not_run_vector_rebuild(monkeypatch, tmp_path) -> None:
    _setup(tmp_path, monkeypatch, enable_vectors=True)
    catalog.index_session_for_fts(
        run_id="run-hot-1",
        agent_type="codex",
        content="session content",
        session_path="/tmp/run-hot-1.jsonl",
    )

    monkeypatch.setattr(
        pipeline,
        "extract_session_memories",
        lambda *_args, **_kwargs: {
            "status": "completed",
            "learnings_new": 1,
            "learnings_updated": 0,
        },
    )

    code, summary = daemon.run_sync_once(
        run_id="run-hot-1",
        agent_filter=None,
        no_extract=False,
        no_llm=True,
        force=False,
        max_sessions=1,
        dry_run=False,
        ignore_lock=True,
        trigger="test",
        window_start=None,
        window_end=None,
    )

    latest = catalog.latest_service_run("sync")
    assert code == daemon.EXIT_OK
    assert summary.extracted_sessions == 1
    assert latest is not None
    assert "vectors_updated" not in latest["details"]
    assert "vectors_error" not in latest["details"]


def test_maintain_cold_path_runs_requested_steps(monkeypatch, tmp_path) -> None:
    _setup(tmp_path, monkeypatch, enable_vectors=True)
    calls: list[str] = []

    def _capture_step(step: str, **_kwargs):
        calls.append(step)
        return None

    monkeypatch.setattr(daemon, "_run_maintain_step", _capture_step)

    code, payload = daemon.run_maintain_once(
        window="30d",
        since_raw=None,
        until_raw=None,
        steps_raw=None,
        agent_raw=None,
        no_llm=True,
        force=False,
        dry_run=False,
        parse_duration_to_seconds=parse_duration_to_seconds,
        parse_csv=parse_csv,
        parse_agent_filter=parse_agent_filter,
    )

    assert code == daemon.EXIT_OK
    assert payload["partial"] is False
    assert calls == ["consolidate", "decay", "report"]
