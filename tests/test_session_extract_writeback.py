"""test session extract writeback."""

from __future__ import annotations

import json
import os

from acreta.config.settings import reload_config
from acreta.sessions import catalog


def _setup_env(tmp_path):
    os.environ["ACRETA_DATA_DIR"] = str(tmp_path)
    os.environ["ACRETA_SESSIONS_DB"] = str(tmp_path / "index" / "sessions.sqlite3")
    os.environ["ACRETA_MEMORY_SCOPE"] = "global_only"
    reload_config()
    catalog.init_sessions_db()


def test_update_session_writeback_fields(tmp_path):
    _setup_env(tmp_path)
    catalog.index_session_for_fts(
        run_id="run-1",
        agent_type="codex",
        content="initial content",
    )

    ok = catalog.update_session_extract_fields(
        "run-1",
        summary_text="short summary",
        tags='["fix-bug","queue"]',
        outcome="mostly_achieved",
    )
    assert ok is True

    row = catalog.fetch_session_doc("run-1")
    assert row is not None
    assert row["summary_text"] == "short summary"
    assert row["tags"] == '["fix-bug","queue"]'
    assert row["outcome"] == "mostly_achieved"


def test_session_extract_writeback_accepts_tag_updates(tmp_path):
    _setup_env(tmp_path)
    run_id = "run-tags-1"
    catalog.index_session_for_fts(
        run_id=run_id,
        agent_type="codex",
        repo_name="acreta",
        content="initial content",
        summary_text="brief",
    )

    ok = catalog.update_session_extract_fields(
        run_id,
        tags='["agent:codex","repo:acreta"]',
        outcome="completed",
    )
    assert ok is True

    row = catalog.fetch_session_doc(run_id)
    assert row is not None
    tags = json.loads(row["tags"] or "[]")
    assert "agent:codex" in tags
    assert "repo:acreta" in tags
