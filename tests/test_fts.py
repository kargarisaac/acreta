"""test fts."""

from __future__ import annotations

import os
from pathlib import Path

from acreta.config.settings import reload_config
from acreta.sessions import catalog


def _setup_env(tmp_path: Path) -> None:
    os.environ["ACRETA_DATA_DIR"] = str(tmp_path)
    os.environ["ACRETA_INDEX_DIR"] = str(tmp_path / "index")
    os.environ["ACRETA_SESSIONS_DB"] = str(tmp_path / "index" / "sessions.sqlite3")
    reload_config()


def test_index_and_count_sessions(tmp_path: Path) -> None:
    _setup_env(tmp_path)
    catalog.init_sessions_db()

    ok = catalog.index_session_for_fts(
        run_id="run-1",
        agent_type="codex",
        content="fix parser crash and rerun tests",
        repo_name="repo-a",
        start_time="2026-02-14T00:00:00+00:00",
        summaries='["fixed parser"]',
    )
    assert ok is True
    assert catalog.count_fts_indexed() == 1

    row = catalog.fetch_session_doc("run-1")
    assert row is not None
    assert row["agent_type"] == "codex"
    assert row["repo_name"] == "repo-a"


def test_update_session_extract_fields(tmp_path: Path) -> None:
    _setup_env(tmp_path)
    catalog.init_sessions_db()
    catalog.index_session_for_fts(
        run_id="run-2",
        agent_type="claude",
        content="implement queue retry",
        repo_name="repo-b",
        start_time="2026-02-14T00:00:00+00:00",
    )

    updated = catalog.update_session_extract_fields(
        "run-2",
        summary_text="implemented queue retry",
        tags='["queue","retry"]',
        outcome="fully_achieved",
    )
    assert updated is True

    row = catalog.fetch_session_doc("run-2")
    assert row is not None
    assert row["summary_text"] == "implemented queue retry"
    assert row["outcome"] == "fully_achieved"
