"""test daemon hot cold paths."""

from __future__ import annotations

from acreta.app import daemon
from acreta.app.arg_utils import parse_agent_filter, parse_csv, parse_duration_to_seconds
from acreta.config.settings import reload_config
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
    session_path = tmp_path / "sessions" / "run-hot-1.jsonl"
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_text('{"role":"assistant","content":"ok"}\n', encoding="utf-8")
    catalog.index_session_for_fts(
        run_id="run-hot-1",
        agent_type="codex",
        content="session content",
        session_path=str(session_path),
    )

    monkeypatch.setattr(
        "acreta.runtime.agent.AcretaAgent.run",
        lambda *_args, **_kwargs: {
            "counts": {"add": 1, "update": 0, "no_op": 0},
        },
    )

    code, summary = daemon.run_sync_once(
        run_id="run-hot-1",
        agent_filter=None,
        no_extract=False,
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
        force=False,
        dry_run=False,
        parse_duration_to_seconds=parse_duration_to_seconds,
        parse_csv=parse_csv,
        parse_agent_filter=parse_agent_filter,
    )

    assert code == daemon.EXIT_OK
    assert payload["partial"] is False
    assert calls == ["consolidate", "decay", "report"]
