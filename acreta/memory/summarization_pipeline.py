"""Trace summarization pipeline that outputs markdown-frontmatter-ready metadata + summary."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import dspy
from pydantic import BaseModel, Field

from acreta.memory.utils import configure_dspy_lm, env_positive_int
from acreta.sessions import catalog as session_db


class TraceSummaryCandidate(BaseModel):
    """Structured trace summary payload used to build markdown frontmatter later."""

    title: str = Field(description="Short trace title for markdown frontmatter.")
    description: str = Field(description="One-line description of what the session achieved.")
    summary: str = Field(description="Natural-language summary with at most 300 words.")
    date: str = Field(description="Session date in YYYY-MM-DD.")
    time: str = Field(description="Session time in HH:MM:SS.")
    coding_agent: str = Field(description="Coding agent label like codex, claude code, cursor, or windsurf.")
    raw_trace_path: str = Field(description="Absolute path to the original raw trace file.")
    run_id: str | None = Field(default=None, description="Session run id when available.")
    repo_name: str | None = Field(default=None, description="Repository short name when available.")


class TraceSummarySignature(dspy.Signature):
    """Summarize a raw session trace into markdown-ready metadata plus summary text.

    Rules:
    - Keep summary factual and grounded in trace evidence.
    - Keep summary length <= 300 words.
    - Keep title and description concise and specific.
    """

    transcript: str = dspy.InputField(desc="Raw transcript text")
    metadata: dict[str, Any] = dspy.InputField(desc="Session metadata")
    metrics: dict[str, Any] = dspy.InputField(desc="Deterministic metrics")
    summary_payload: TraceSummaryCandidate = dspy.OutputField(
        desc="Structured summary payload with title/description/date/time/agent/path fields"
    )


def _summarize_trace_with_rlm(
    transcript: str,
    *,
    metadata: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
    session_file_path: Path,
) -> dict[str, Any]:
    """Run DSPy RLM summarization and return schema-validated summary metadata payload."""
    if not transcript.strip():
        raise RuntimeError("session_trace_empty")
    max_iterations = env_positive_int("ACRETA_DSPY_RLM_MAX_ITERATIONS", 24)
    max_llm_calls = env_positive_int("ACRETA_DSPY_RLM_MAX_LLM_CALLS", 24)
    configure_dspy_lm()
    rlm = dspy.RLM(
        TraceSummarySignature,
        max_iterations=max_iterations,
        max_llm_calls=max_llm_calls,
        verbose=True,
    )
    result = rlm(
        transcript=transcript,
        metadata=metadata or {},
        metrics=metrics or {},
    )
    payload = getattr(result, "summary_payload", None)
    if isinstance(payload, TraceSummaryCandidate):
        candidate = payload
    elif isinstance(payload, dict):
        candidate = TraceSummaryCandidate.model_validate(payload)
    else:
        raise RuntimeError("dspy summary_payload must be TraceSummaryCandidate or dict")
    return candidate.model_dump(mode="json", exclude_none=True)


def summarize_trace_from_session_file(
    session_file_path: Path,
    *,
    metadata: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Summarize one session trace file into markdown-ready metadata + <=300 word summary."""
    if not session_file_path.exists() or not session_file_path.is_file():
        raise FileNotFoundError(f"session_file_missing:{session_file_path}")
    transcript = session_file_path.read_text(encoding="utf-8")
    session_metadata = {**(metadata or {}), "raw_trace_path": str(session_file_path)}
    return _summarize_trace_with_rlm(
        transcript,
        metadata=session_metadata,
        metrics=metrics,
        session_file_path=session_file_path,
    )


def summarize_session_trace(
    run_id: str,
) -> dict[str, Any]:
    """Resolve run id, summarize its trace, and return summary metadata payload."""
    session = session_db.fetch_session_doc(run_id)
    if session is None:
        session_db.index_new_sessions()
        session = session_db.fetch_session_doc(run_id)
    if session is None:
        return {"run_id": run_id, "status": "missing"}

    source_path_raw = str(session.get("session_path") or "").strip()
    if not source_path_raw:
        return {"run_id": run_id, "status": "session_path_missing"}

    session_file_path = Path(source_path_raw).expanduser()
    if not session_file_path.exists() or not session_file_path.is_file():
        return {"run_id": run_id, "status": "session_path_missing"}

    metadata = {**session, "run_id": run_id, "raw_trace_path": str(session_file_path)}
    summary_payload = summarize_trace_from_session_file(
        session_file_path,
        metadata=metadata,
        metrics={},
    )

    return {
        "run_id": run_id,
        "status": "completed",
        "summary": summary_payload,
        "metadata": metadata,
        "session_path": str(session_file_path),
    }


if __name__ == "__main__":
    """Run a real smoke test for trace summarization without model mocking."""
    import os
    from tempfile import TemporaryDirectory

    from acreta.config.settings import reload_config

    with TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        os.environ["ACRETA_DATA_DIR"] = str(tmp_path)
        os.environ["ACRETA_MEMORY_DIR"] = str(tmp_path / "memory")
        os.environ["ACRETA_INDEX_DIR"] = str(tmp_path / "index")
        os.environ["ACRETA_SESSIONS_DB"] = str(tmp_path / "index" / "sessions.sqlite3")
        os.environ["ACRETA_MEMORY_SCOPE"] = "global_only"
        reload_config()
        session_db.init_sessions_db()

        run_id = "summary-self-test-1"
        session_path = tmp_path / "sessions" / f"{run_id}.jsonl"
        session_path.parent.mkdir(parents=True, exist_ok=True)
        session_path.write_text(
            '{"role":"user","content":"Fix queue heartbeat drift and duplicate claims."}\n'
            '{"role":"assistant","content":"Implemented heartbeat every 15 seconds and bounded retries."}\n',
            encoding="utf-8",
        )
        session_db.index_session_for_fts(
            run_id=run_id,
            agent_type="codex",
            repo_name="acreta",
            content="queue heartbeat fix",
            session_path=str(session_path),
        )
        result = summarize_session_trace(run_id)

    assert result["status"] == "completed"
    summary = result["summary"]
    assert isinstance(summary, dict)
    assert summary["title"]
    assert summary["description"]
    assert summary["coding_agent"] == "codex"
    assert summary["raw_trace_path"].endswith(f"{run_id}.jsonl")
    assert len(summary["summary"].split()) <= 300
